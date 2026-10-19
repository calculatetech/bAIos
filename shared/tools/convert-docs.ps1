param([Parameter(Mandatory)][string]$SourceDirectory,
      [Parameter(Mandatory)][string]$OutputDirectory,
      [Parameter(Mandatory)][string]$TemporaryDirectory)
$ErrorActionPreference = 'Stop'
$sourceDir = (Resolve-Path -LiteralPath $SourceDirectory).Path
$outputDir = [IO.Path]::GetFullPath($OutputDirectory)
$tempDir = [IO.Path]::GetFullPath($TemporaryDirectory)

function Find-Executable([string]$Name, [string[]]$Fallbacks) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($path in $Fallbacks) {
        if ($path -and (Test-Path -LiteralPath $path)) { return $path }
    }
    throw "$Name is required. Install Poppler and Tesseract, then run this script again."
}

$wingetPackages = Join-Path $env:LOCALAPPDATA "Microsoft/WinGet/Packages"
$popplerBin = if (Test-Path -LiteralPath $wingetPackages) {
    Get-ChildItem -LiteralPath $wingetPackages -Directory -Filter "oschwartz10612.Poppler*" |
        Get-ChildItem -Directory -Filter "poppler-*" |
        ForEach-Object { Join-Path $_.FullName "Library/bin" } |
        Select-Object -First 1
}
$pdfinfo = Find-Executable "pdfinfo" @($(if ($popplerBin) { Join-Path $popplerBin "pdfinfo.exe" }))
$pdftotext = Find-Executable "pdftotext" @($(if ($popplerBin) { Join-Path $popplerBin "pdftotext.exe" }))
$pdftoppm = Find-Executable "pdftoppm" @($(if ($popplerBin) { Join-Path $popplerBin "pdftoppm.exe" }))
$tesseract = Find-Executable "tesseract" @("C:/Program Files/Tesseract-OCR/tesseract.exe")

[IO.Directory]::CreateDirectory($outputDir) | Out-Null
[IO.Directory]::CreateDirectory($tempDir) | Out-Null
$utf8 = [Text.UTF8Encoding]::new($false)
$manifest = @()

foreach ($pdf in Get-ChildItem -LiteralPath $sourceDir -File -Recurse -Filter "*.pdf" | Sort-Object Name) {
    $relative = [IO.Path]::GetRelativePath($sourceDir, $pdf.FullName).Replace('\', '/')
    $before = (Get-FileHash -LiteralPath $pdf.FullName -Algorithm SHA256).Hash
    $info = & $pdfinfo $pdf.FullName 2>&1
    if ($LASTEXITCODE) { throw "pdfinfo failed for $($pdf.Name)." }
    $pageLine = $info | Where-Object { $_ -match '^Pages:\s+(\d+)' } | Select-Object -First 1
    if (-not $pageLine) { throw "Cannot read the page count for $($pdf.Name)." }
    $pages = [int]$Matches[1]
    $parts = [Collections.Generic.List[string]]::new()
    $ocrPages = 0

    for ($page = 1; $page -le $pages; $page++) {
        $textPath = Join-Path $tempDir "page.txt"
        & $pdftotext -f $page -l $page -layout -enc UTF-8 $pdf.FullName $textPath
        if ($LASTEXITCODE) { throw "pdftotext failed for $($pdf.Name), page $page." }
        $text = [IO.File]::ReadAllText($textPath).Replace("`f", "").Trim()
        if (($text -replace '\s', '').Length -lt 20) {
            $prefix = Join-Path $tempDir "page"
            & $pdftoppm -f $page -l $page -r 300 -singlefile -png $pdf.FullName $prefix | Out-Null
            if ($LASTEXITCODE) { throw "pdftoppm failed for $($pdf.Name), page $page." }
            $ocrText = Join-Path $tempDir "ocr.txt"
            $ocrError = Join-Path $tempDir "ocr.err"
            $quotedImage = '"' + $prefix + '.png"'
            $ocr = Start-Process -FilePath $tesseract -ArgumentList @($quotedImage, "stdout", "--dpi", "300", "-l", "eng") -RedirectStandardOutput $ocrText -RedirectStandardError $ocrError -WindowStyle Hidden -Wait -PassThru
            if ($ocr.ExitCode) { throw "Tesseract failed for $($pdf.Name), page $page." }
            $text = [IO.File]::ReadAllText($ocrText).Trim()
            $ocrPages++
        }
        if (-not $text) { $text = "[No text detected on this page.]" }
        $parts.Add("===== Page $page =====`r`n$text")
    }

    $output = Join-Path $outputDir ([IO.Path]::ChangeExtension($relative, ".txt"))
    [IO.Directory]::CreateDirectory((Split-Path -Parent $output)) | Out-Null
    [IO.File]::WriteAllText($output, ($parts -join "`r`n`r`n") + "`r`n", $utf8)
    $after = (Get-FileHash -LiteralPath $pdf.FullName -Algorithm SHA256).Hash
    if ($after -ne $before) { throw "$($pdf.Name) changed during conversion." }
    $manifest += [pscustomobject]@{ File = $relative; Pages = $pages; Sha256 = $before; OcrPages = $ocrPages }
    Write-Host "$($pdf.Name): $pages pages, $ocrPages OCR pages"
}

$manifest | Export-Csv -LiteralPath (Join-Path $outputDir "manifest.csv") -NoTypeInformation -Encoding utf8
"Created $($manifest.Count) searchable manuals in $outputDir."
