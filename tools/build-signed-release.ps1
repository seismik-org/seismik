<#
.SYNOPSIS
    Compila y firma la distribución Android de Seismik sin exponer la clave.

.DESCRIPTION
    La contraseña del keystore se guarda como blob DPAPI (salida de
    ConvertFrom-SecureString) y sólo puede descifrarla la cuenta de Windows que
    la creó. Este script la descifra en memoria, la entrega a Gradle mediante
    variables de entorno del proceso y la borra al terminar. La contraseña nunca
    se imprime, ni se escribe en disco, ni queda en el historial del shell.

    Al terminar publica la huella SHA-256 del artefacto y del certificado
    firmante: ambos son datos públicos y sirven como evidencia de la entrega.

.EXAMPLE
    .\tools\build-signed-release.ps1 `
        -Keystore ..\..\work\secrets\seismik-upload.jks `
        -PasswordFile ..\..\work\secrets\seismik-upload-password.dpapi `
        -Alias seismik-upload `
        -ApiBaseUrl https://api.seismik.org
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Keystore,
    [Parameter(Mandatory = $true)][string]$PasswordFile,
    [Parameter(Mandatory = $true)][string]$Alias,
    [Parameter(Mandatory = $true)][string]$ApiBaseUrl,

    # El alias y la clave privada suelen compartir contraseña en un keystore de
    # subida. Usa -KeyPasswordFile sólo si en este keystore difieren.
    [string]$KeyPasswordFile,

    [ValidateSet('apk', 'appbundle', 'both')]
    [string]$Artifact = 'both',

    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$mobileRoot = Join-Path $repoRoot 'mobile_app'

function Resolve-RequiredPath([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label no existe: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Read-ProtectedSecret([string]$Path) {
    # ConvertTo-SecureString sobre el blob DPAPI falla si lo ejecuta otra cuenta
    # de Windows, que es exactamente la protección que se busca.
    $blob = (Get-Content -LiteralPath $Path -Raw).Trim()
    try {
        return ConvertTo-SecureString -String $blob
    } catch {
        throw ("No se pudo descifrar $Path con esta cuenta de Windows. " +
               "El blob DPAPI pertenece a la cuenta que lo creó.")
    }
}

function Use-PlainSecret([System.Security.SecureString]$Secret, [scriptblock]$Action) {
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)
        $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        & $Action $plain
    } finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

$keystorePath = Resolve-RequiredPath $Keystore 'El keystore'
$passwordPath = Resolve-RequiredPath $PasswordFile 'El archivo de contraseña'
$keyPasswordPath = if ($KeyPasswordFile) {
    Resolve-RequiredPath $KeyPasswordFile 'La contraseña de la clave'
} else {
    $passwordPath
}

$storeSecret = Read-ProtectedSecret $passwordPath
$keySecret = if ($keyPasswordPath -eq $passwordPath) {
    $storeSecret
} else {
    Read-ProtectedSecret $keyPasswordPath
}

Push-Location $mobileRoot
try {
    if (-not $SkipTests) {
        Write-Host 'Analizando y probando la app antes de firmar...'
        & flutter analyze
        if ($LASTEXITCODE -ne 0) { throw 'flutter analyze falló; no se firma nada.' }
        & flutter test
        if ($LASTEXITCODE -ne 0) { throw 'flutter test falló; no se firma nada.' }
    }

    $targets = switch ($Artifact) {
        'apk'        { @('apk') }
        'appbundle'  { @('appbundle') }
        default      { @('apk', 'appbundle') }
    }

    Use-PlainSecret $storeSecret {
        param($storePlain)
        Use-PlainSecret $keySecret {
            param($keyPlain)
            $env:SEISMIK_KEYSTORE = $keystorePath
            $env:SEISMIK_KEYSTORE_PASSWORD = $storePlain
            $env:SEISMIK_KEY_ALIAS = $Alias
            $env:SEISMIK_KEY_PASSWORD = $keyPlain
            try {
                foreach ($target in $targets) {
                    Write-Host "Compilando $target de release firmado..."
                        & flutter build $target --release `
                        "--dart-define=SEISMIK_API_BASE_URL=$ApiBaseUrl" `
                        "--dart-define=SEISMIK_INTEGRITY_REQUIRED=true"
                    if ($LASTEXITCODE -ne 0) { throw "flutter build $target falló." }
                }
            } finally {
                # El proceso puede sobrevivir al script; las credenciales no.
                Remove-Item Env:SEISMIK_KEYSTORE_PASSWORD -ErrorAction SilentlyContinue
                Remove-Item Env:SEISMIK_KEY_PASSWORD -ErrorAction SilentlyContinue
                Remove-Item Env:SEISMIK_KEYSTORE -ErrorAction SilentlyContinue
                Remove-Item Env:SEISMIK_KEY_ALIAS -ErrorAction SilentlyContinue
            }
        }
    }

    Write-Host ''
    Write-Host 'Evidencia de la distribución firmada:'
    $artifacts = @(
        'build\app\outputs\flutter-apk\app-release.apk',
        'build\app\outputs\bundle\release\app-release.aab'
    ) | Where-Object { Test-Path -LiteralPath $_ }

    foreach ($path in $artifacts) {
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        $size = [math]::Round((Get-Item -LiteralPath $path).Length / 1MB, 1)
        Write-Host "  $path  ${size} MB  SHA-256 $hash"
    }

    $apk = $artifacts | Where-Object { $_.EndsWith('.apk') } | Select-Object -First 1
    if ($apk) {
        $apksigner = Get-ChildItem -Path "$env:LOCALAPPDATA\Android\Sdk\build-tools" `
            -Filter 'apksigner.bat' -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1
        if ($apksigner) {
            Write-Host ''
            Write-Host 'Certificado firmante (verifica que no sea la clave de depuración):'
            & $apksigner.FullName verify --print-certs $apk |
                Select-String -Pattern 'SHA-256 digest|Signer #1 certificate DN'
        } else {
            Write-Host 'apksigner no encontrado; verifica la firma manualmente antes de publicar.'
        }
    }
} finally {
    Pop-Location
}
