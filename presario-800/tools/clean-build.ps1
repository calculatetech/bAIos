# Preview with -WhatIf. Obsolete generated output is purged, not archived.
[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
$portRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path (Split-Path -Parent $portRoot) 'shared/tools/build-cleanup.ps1')
$build = Join-Path $portRoot 'build'
Initialize-BuildCleanup $build $PSCmdlet
if (-not (Test-Path -LiteralPath $build)) { return }

# The root is the approved build; pending features use one directory per pair.
$keep = @('86box', 'tmp', 'diagnostics', 'chipset-review', 'apm-review', 'cd-review', 'review',
          'baios-presario800.bin', 'baios-presario800-system.rom', 'baios-presario800-system.lst',
          'baios-presario800-vga50.bin', 'baios-presario800-vga60.bin', 'rom-manifest.json',
          'VGACHECK.COM', 'L1OFF.COM', 'APMDRIVER.COM', 'APMPROBE.COM', 'boot-test.bin', 'fault-test.bin', 'keyboard-test.bin',
          'vga-register-test.bin', 'presario800-card.vhd', 'card-boot.png')
foreach ($item in (Get-ChildItem -LiteralPath $build -Force | Where-Object Name -NotIn $keep)) {
    Remove-Generated $item.FullName
}

# Shared dependencies live at repository root. Private wrappers survive.
$emulatorAssets = Join-Path $build '86box'
if (Test-Path -LiteralPath $emulatorAssets) {
    foreach ($item in (Get-ChildItem -LiteralPath $emulatorAssets -Force |
        Where-Object Name -NotIn @('roms', 'vga50', 'vga60'))) {
        Remove-Generated $item.FullName
    }
}

# Scratch and synthetic disks can be regenerated. Original card media is retained.
foreach ($name in @('tmp', 'legacy-fixtures')) {
    $path = Join-Path $build $name
    if (-not (Test-Path -LiteralPath $path)) { continue }
    if ($name -eq 'tmp') {
        Assert-OwnedPath $path $build | Out-Null
        foreach ($item in Get-ChildItem -LiteralPath $path -Force) { Remove-Generated $item.FullName }
    } else { Remove-Generated $path }
}
# Keep the current diagnostic readers and observations; purge consumed copies.
$mouseWork = Join-Path $build 'diagnostics/cdboot/si8'
if (Test-Path -LiteralPath $mouseWork) {
    foreach ($item in (Get-ChildItem -LiteralPath $mouseWork -Force |
        Where-Object Name -NotIn @('native.py', 'observe.asm', 'check-default.py',
            'vga-now.asm', 'vga-observe.asm', 'default-50.bin', 'default-60.bin',
            'si8-events.bin', 'si8-selection.bin', 'windows-default87-trace.bin',
            'si8-power-before.bin', 'si8-power-after.bin',
            'win-input.py', 'win-input-observe.asm', 'windows-input-before.bin',
            'windows-input-c2.bin', 'windows-input-diag.bin', 'results.txt'))) {
        Remove-Generated $item.FullName
    }
}
foreach ($review in @('cd-review', 'review/cd-review')) {
    $path = Join-Path $build $review
    if (-not (Test-Path -LiteralPath $path)) { continue }
    foreach ($item in (Get-ChildItem -LiteralPath $path -Directory)) {
        if (Test-Path -LiteralPath (Join-Path $item.FullName '86box.cfg')) {
            Remove-Generated $item.FullName
        }
    }
    Remove-Generated (Join-Path $path 'preview.pid')
}
foreach ($label in @('probe', 'driver-dos', 'driver-emm386')) {
    Remove-Generated (Join-Path $build "apm-review/$label")
}

# Current review screenshots/results are already stored beside disposable VMs.
foreach ($review in @('chipset-review', 'chipset-review/vga50', 'apm-review')) {
    $path = Join-Path $build $review
    if (-not (Test-Path -LiteralPath $path)) { continue }
    foreach ($item in (Get-ChildItem -LiteralPath $path -Directory)) {
        if (Test-Path -LiteralPath (Join-Path $item.FullName '86box.cfg')) {
            Remove-Generated $item.FullName
        }
    }
}
