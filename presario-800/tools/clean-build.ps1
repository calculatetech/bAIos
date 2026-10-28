# Preview with -WhatIf. Obsolete generated output is purged, not archived.
[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
$portRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path (Split-Path -Parent $portRoot) 'shared/tools/build-cleanup.ps1')
$build = Join-Path $portRoot 'build'
Initialize-BuildCleanup $build $PSCmdlet
if (-not (Test-Path -LiteralPath $build)) { return }
if (Test-Path -LiteralPath (Join-Path $build 'presario800-card.vhd')) {
    throw 'Move the retained DOS image to root reference/media/dos/test-card.vhd before cleanup.'
}

# The root is the approved build; pending features use one directory per pair.
$keep = @('baios-presario800.bin','baios-presario800-system.rom','baios-presario800-system.lst','baios-presario800-vga50.bin','baios-presario800-vga60.bin','rom-manifest.json','diagnostics','tests','research','review','releases','LATEST.txt','LATEST.json','build-info.json','tmp')
$keep += @(Get-LatestCandidateFiles $build)
foreach ($item in (Get-ChildItem -LiteralPath $build -Force | Where-Object Name -NotIn $keep)) {
    Remove-Generated $item.FullName
}


$tmp = Join-Path $build "tmp"
if (Test-Path -LiteralPath $tmp) {
    Assert-OwnedPath $tmp $build | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $tmp -Force) { Remove-Generated $item.FullName }
}

# Keep current ROM wrappers; discard the consumed default VM.
$assets = Join-Path $build 'tests/86box'
if (Test-Path -LiteralPath $assets) {
    foreach ($item in Get-ChildItem -LiteralPath $assets -Force | Where-Object Name -NotIn @('roms','vga50','vga60','.retain-diagnosis')) {
        if (Test-Path -LiteralPath (Join-Path $assets '.retain-diagnosis')) { continue }
        Remove-Generated $item.FullName
    }
}
foreach ($review in @('review/chipset','review/chipset/vga50','review/apm','review/cd-review')) {
    $path = Join-Path $build $review
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $preview = Join-Path $path 'preview.pid'
    if (Test-Path -LiteralPath $preview) { Remove-Generated $preview }
    foreach ($item in Get-ChildItem -LiteralPath $path -Directory) {
        if ((Test-Path -LiteralPath (Join-Path $item.FullName '86box.cfg')) -and
            -not (Test-Path -LiteralPath (Join-Path $item.FullName '.retain-diagnosis'))) { Remove-Generated $item.FullName }
    }
}
