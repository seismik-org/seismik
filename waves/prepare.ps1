$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$gcloud = Join-Path $taskRoot 'work/tools/gcloud-581/google-cloud-sdk/bin/gcloud.cmd'
$manifestPath = Join-Path $taskRoot 'work/storage-migration-2026-10-10/manifest.json'
if (Test-Path -LiteralPath $manifestPath) {
    $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
} else {
    $manifest = (& $gcloud storage cat gs://seismik-15bbb-scientific-archive/imports/local-2026-10-10/manifest.json --project=seismik-15bbb) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read the private archive manifest' }
}
$records = @($manifest.entries | Where-Object path -like '*.mseed' | ForEach-Object {
    [ordered]@{id=$_.sha256.Substring(0,24); name=$_.path; bytes=$_.bytes; sha256=$_.sha256;
    category=$_.path.Split('/')[0]; format='MiniSEED'; live=$false;
    validation_status='research_not_validated'; redistribution='requires_source_review'}
})
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'catalog.json'), (@{files=$manifest.files; bytes=$manifest.bytes; records=$records} | ConvertTo-Json -Depth 6), $utf8)
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../web/assets/seismik_logo.webp') -Destination (Join-Path $PSScriptRoot 'static/seismik_logo.webp')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../web/assets/favicon-32.png') -Destination (Join-Path $PSScriptRoot 'static/favicon-32.png')
Write-Output "Prepared historical catalogue: $($records.Count) recordings."
