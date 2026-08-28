param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [ValidateSet('All', 'Master', 'Plan', 'Control', 'ScientificReview')]
    [string]$Document = 'All'
)

$ErrorActionPreference = 'Stop'
$docsDir = Join-Path $ProjectRoot 'docs\project-management'
$documents = @(
    @{ Key = 'Master'; Source = 'SEISMIK_DOCUMENTO_MAESTRO_v0.1.md'; Target = 'SEISMIK_DOCUMENTO_MAESTRO_v0.1.docx'; ShortTitle = 'Documento Maestro'; Version = '0.1' },
    @{ Key = 'Plan'; Source = 'SEISMIK_PLAN_SCRUM_MVP_v0.1.md'; Target = 'SEISMIK_PLAN_SCRUM_MVP_v0.1.docx'; ShortTitle = 'Plan Scrum MVP'; Version = '0.1' },
    @{ Key = 'Control'; Source = 'SEISMIK_CONTROL_AVANCE_v0.1.md'; Target = 'SEISMIK_CONTROL_AVANCE_v0.1.docx'; ShortTitle = 'Control de Avance'; Version = '0.1.5' },
    @{ Key = 'ScientificReview'; Source = 'PAQUETE_REVISION_SISMOLOGICA_v0.1.md'; Target = 'PAQUETE_REVISION_SISMOLOGICA_v0.1.docx'; ShortTitle = 'Revision Sismologica'; Version = '0.1' }
)
if ($Document -ne 'All') {
    $documents = @($documents | Where-Object { $_.Key -eq $Document })
}

function Clean-MarkdownText {
    param([string]$Text)
    return ($Text -replace '\*\*', '' -replace '`', '')
}

function Add-WordParagraph {
    param(
        [object]$Document,
        [string]$Text,
        [int]$Style = -1,
        [switch]$Italic,
        [switch]$Code
    )
    $end = $Document.Content.End - 1
    $range = $Document.Range($end, $end)
    $range.Text = (Clean-MarkdownText $Text)
    $range.InsertParagraphAfter()
    $paragraphRange = $Document.Range($end, $Document.Content.End - 1)
    try { $paragraphRange.Style = $Style } catch { $paragraphRange.Style = -1 }
    if ($Italic) { $paragraphRange.Font.Italic = 1 }
    if ($Code) {
        $paragraphRange.Font.Name = 'Consolas'
        $paragraphRange.Font.Size = 8.5
        $paragraphRange.Shading.BackgroundPatternColor = 15987699
    }
}

function Add-WordTable {
    param(
        [object]$Document,
        [object[]]$Rows
    )
    if ($Rows.Count -eq 0) { return }
    $columnCount = ($Rows | ForEach-Object { $_.Count } | Measure-Object -Maximum).Maximum
    $end = $Document.Content.End - 1
    $range = $Document.Range($end, $end)
    $table = $Document.Tables.Add($range, $Rows.Count, $columnCount)
    $table.Borders.Enable = 1
    $table.AllowAutoFit = $true
    try { $table.AutoFitBehavior(1) } catch {}
    for ($r = 0; $r -lt $Rows.Count; $r++) {
        for ($c = 0; $c -lt $columnCount; $c++) {
            $value = if ($c -lt $Rows[$r].Count) { Clean-MarkdownText ([string]$Rows[$r][$c]) } else { '' }
            $cellRange = $table.Cell($r + 1, $c + 1).Range
            $cellRange.Text = $value
            $cellRange.Font.Name = 'Aptos'
            $cellRange.Font.Size = 8.5
        }
    }
    $header = $table.Rows.Item(1).Range
    $header.Font.Bold = 1
    $header.Font.Color = 16777215
    $header.Shading.BackgroundPatternColor = 9127187
    $table.Rows.Item(1).HeadingFormat = -1
    $after = $Document.Range($table.Range.End, $table.Range.End)
    $after.InsertParagraphAfter()
}

function Convert-MarkdownToWord {
    param(
        [object]$Word,
        [string]$SourcePath,
        [string]$TargetPath,
        [string]$ShortTitle,
        [string]$Version
    )

    $document = $Word.Documents.Add()
    try {
        $document.PageSetup.TopMargin = $Word.CentimetersToPoints(1.8)
        $document.PageSetup.BottomMargin = $Word.CentimetersToPoints(1.8)
        $document.PageSetup.LeftMargin = $Word.CentimetersToPoints(2.0)
        $document.PageSetup.RightMargin = $Word.CentimetersToPoints(2.0)

        $normal = $document.Styles.Item(-1)
        $normal.Font.Name = 'Aptos'
        $normal.Font.Size = 10
        $normal.ParagraphFormat.SpaceAfter = 6
        $normal.ParagraphFormat.LineSpacingRule = 0

        foreach ($styleId in @(-2, -3, -4)) {
            $style = $document.Styles.Item($styleId)
            $style.Font.Name = 'Aptos Display'
            $style.Font.Color = 9127187
        }
        $document.Styles.Item(-63).Font.Name = 'Aptos Display'
        $document.Styles.Item(-63).Font.Color = 9127187

        $header = $document.Sections.Item(1).Headers.Item(1).Range
        $header.Text = "Seismik | $ShortTitle | v$Version"
        $header.Font.Name = 'Aptos'
        $header.Font.Size = 8
        $header.Font.Color = 8421504

        $footer = $document.Sections.Item(1).Footers.Item(1).Range
        $footer.Text = 'Seismik — Proyecto abierto | Página '
        $footer.Font.Name = 'Aptos'
        $footer.Font.Size = 8
        $footer.Collapse(0)
        $null = $footer.Fields.Add($footer, 33)

        $lines = Get-Content -LiteralPath $SourcePath -Encoding UTF8
        $inCode = $false
        $codeLines = [System.Collections.Generic.List[string]]::new()
        $index = 0
        while ($index -lt $lines.Count) {
            $line = [string]$lines[$index]

            if ($line.Trim().StartsWith('```')) {
                if ($inCode) {
                    Add-WordParagraph -Document $document -Text ($codeLines -join "`r`n") -Code
                    $codeLines.Clear()
                    $inCode = $false
                } else {
                    $inCode = $true
                }
                $index++
                continue
            }
            if ($inCode) {
                $codeLines.Add($line)
                $index++
                continue
            }

            if ($line.TrimStart().StartsWith('|')) {
                $rawTable = [System.Collections.Generic.List[string]]::new()
                while ($index -lt $lines.Count -and ([string]$lines[$index]).TrimStart().StartsWith('|')) {
                    $rawTable.Add([string]$lines[$index])
                    $index++
                }
                $rows = @()
                foreach ($tableLine in $rawTable) {
                    $trimmed = $tableLine.Trim().Trim('|')
                    if ($trimmed -match '^\s*:?-{3,}') { continue }
                    $cells = @($trimmed.Split('|') | ForEach-Object { $_.Trim() })
                    $rows += ,$cells
                }
                Add-WordTable -Document $document -Rows $rows
                continue
            }

            if ([string]::IsNullOrWhiteSpace($line)) {
                $index++
                continue
            }
            if ($line -match '^#\s+(.+)$') {
                Add-WordParagraph -Document $document -Text $Matches[1] -Style -63
            } elseif ($line -match '^##\s+(.+)$') {
                Add-WordParagraph -Document $document -Text $Matches[1] -Style -2
            } elseif ($line -match '^###\s+(.+)$') {
                Add-WordParagraph -Document $document -Text $Matches[1] -Style -3
            } elseif ($line -match '^####\s+(.+)$') {
                Add-WordParagraph -Document $document -Text $Matches[1] -Style -4
            } elseif ($line -match '^[-*]\s+(.+)$') {
                Add-WordParagraph -Document $document -Text $Matches[1] -Style -49
            } elseif ($line -match '^\d+\.\s+(.+)$') {
                Add-WordParagraph -Document $document -Text $Matches[1] -Style -50
            } elseif ($line -match '^>\s*(.+)$') {
                Add-WordParagraph -Document $document -Text $Matches[1] -Italic
            } else {
                Add-WordParagraph -Document $document -Text $line
            }
            $index++
        }

        $document.Fields.Update() | Out-Null
        if (Test-Path -LiteralPath $TargetPath) {
            Remove-Item -LiteralPath $TargetPath -Force
        }
        $document.SaveAs2($TargetPath, 16)
    } finally {
        $document.Close($false)
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($document)
    }
}

$word = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    foreach ($item in $documents) {
        $source = Join-Path $docsDir $item.Source
        $target = Join-Path $docsDir $item.Target
        Convert-MarkdownToWord -Word $word -SourcePath $source -TargetPath $target -ShortTitle $item.ShortTitle -Version $item.Version
        Write-Output $target
    }
} finally {
    if ($word) {
        $word.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
