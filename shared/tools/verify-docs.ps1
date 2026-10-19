param([Parameter(Mandatory)][string]$SourceDirectory,
      [Parameter(Mandatory)][string]$OutputDirectory,
      [Parameter(Mandatory)][int]$ExpectedCount,
      [string[]]$SpotTerms = @())
$ErrorActionPreference = 'Stop'
$sourceDir = (Resolve-Path -LiteralPath $SourceDirectory).Path
$outputDir = (Resolve-Path -LiteralPath $OutputDirectory).Path
$manifestPath = Join-Path $outputDir "manifest.csv"
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Run the owning tools/convert-docs.ps1 first." }

$pdfs = @(Get-ChildItem -LiteralPath $sourceDir -File -Recurse -Filter "*.pdf" | Sort-Object Name)
$texts = @(Get-ChildItem -LiteralPath $outputDir -File -Recurse -Filter "*.txt" | Sort-Object Name)
$manifest = @(Import-Csv -LiteralPath $manifestPath)
if ($pdfs.Count -ne $ExpectedCount) { throw "Expected $ExpectedCount source PDFs, found $($pdfs.Count)." }
if ($texts.Count -ne $pdfs.Count -or $manifest.Count -ne $pdfs.Count) { throw "The source, text, and manifest inventories differ." }

foreach ($pdf in $pdfs) {
    $relative = [IO.Path]::GetRelativePath($sourceDir, $pdf.FullName).Replace('\', '/')
    $textName = [IO.Path]::ChangeExtension($relative, '.txt')
    $matchingText = @($texts | Where-Object { [IO.Path]::GetRelativePath($outputDir, $_.FullName).Replace('\', '/') -eq $textName })
    $matchingManifest = @($manifest | Where-Object File -eq $relative)
    if ($matchingText.Count -ne 1 -or $matchingManifest.Count -ne 1) { throw "The manual inventory does not match." }
    if ((Get-FileHash -LiteralPath $pdf.FullName -Algorithm SHA256).Hash -ne $matchingManifest[0].Sha256) { throw "$($pdf.Name) does not match its recorded hash." }
    $content = [IO.File]::ReadAllText($matchingText[0].FullName)
    if (-not $content.Trim()) { throw "$($matchingText[0].Name) is empty." }
    $pageMarkers = [regex]::Matches($content, '(?m)^===== Page \d+ =====\r?$').Count
    if ($pageMarkers -ne [int]$matchingManifest[0].Pages) { throw "$($matchingText[0].Name) has $pageMarkers page markers, expected $($matchingManifest[0].Pages)." }
}

$allText = ($texts | ForEach-Object { [IO.File]::ReadAllText($_.FullName) }) -join "`n"
foreach ($term in $SpotTerms) {
    if ($allText -notmatch [regex]::Escape($term)) { throw "The searchable manuals do not contain the spot-check term '$term'." }
}

"Searchable manual validation passed for all $ExpectedCount PDFs."
