param(
    [Parameter(Mandatory)][string]$ImagePath,
    [switch]$NegativeControl,
    [switch]$KeypadDelete,
    [switch]$ProductionRom,
    [ValidateSet('Default', 'On', 'Off')][string]$BootNumLock = 'Default'
)

$ErrorActionPreference = 'Stop'
if ($NegativeControl -and $ProductionRom) { throw 'NegativeControl requires the instrumented ROM.' }
$root = Split-Path -Parent $PSScriptRoot
$build = Join-Path $root $(if ($env:BAIOS_BUILD_DIRECTORY) { $env:BAIOS_BUILD_DIRECTORY } else { 'build' })
$build = [IO.Path]::GetFullPath($build)
$buildPrefix = [IO.Path]::GetFullPath((Join-Path $root 'build')).TrimEnd('\') + '\'
if (-not ($build + '\').StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Build directory is outside the system build tree.' }
$scratch = Join-Path $build 'tmp/emm-reset'
[IO.Directory]::CreateDirectory($scratch) | Out-Null
$disk = Join-Path $scratch 'test.vhd'
if (Test-Path -LiteralPath $disk) { throw "Previous test image still exists: $disk" }
$nasm = Join-Path $env:LOCALAPPDATA 'bin/NASM/nasm.exe'
$wrapper = Join-Path $build '86box/roms/machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
$physical = Join-Path $build 'baios-presario800.bin'
$guest = Join-Path $scratch 'reset.com'
$defines = if ($KeypadDelete) { @('-D', 'KEYPAD_DELETE') } else { @() }
if ($BootNumLock -ne 'Default') { $defines += @('-D', "EXPECTED_NUMLOCK=$([int]($BootNumLock -eq 'On'))") }
& $nasm @defines -f bin -o $guest (Join-Path $root 'tests/emm-reset-test.asm')
if ($LASTEXITCODE) { throw 'Reset guest assembly failed.' }
try {
    if (-not $ProductionRom) {
        $source = [IO.File]::ReadAllText((Join-Path $root 'src/bios.asm'))
        if ($NegativeControl) {
            $irqSource = [IO.File]::ReadAllText((Join-Path $root '../shared/src/pc/keyboard-irq.inc'))
            $pattern = 'stc\s+mov ah, 0x4F\s+int 0x15\s+jnc \.scan_consumed'
            if ([regex]::Matches($irqSource, $pattern).Count -ne 1) { throw 'Keyboard hook not uniquely found.' }
            $irqPath = Join-Path $scratch 'negative-keyboard-irq.inc'
            [IO.File]::WriteAllText($irqPath, [regex]::Replace($irqSource, $pattern, ''))
            $source = $source.Replace('%include "../../shared/src/pc/keyboard-irq.inc"', '%include "' + $irqPath.Replace('\', '/') + '"')
        }
        $sourcePath = Join-Path $scratch 'bios.asm'
        $system = Join-Path $scratch 'system.rom'
        [IO.File]::WriteAllText($sourcePath, $source)
        & $nasm -D VGA_BIOS_141 -D EMULATOR_TEST -D EMULATOR_EMM_RESET_TEST -f bin -I ((Join-Path $root 'src') + '/') -o $system $sourcePath
        if ($LASTEXITCODE) { throw 'Reset-test ROM assembly failed.' }
        $bytes = [IO.File]::ReadAllBytes($system)
        if ($bytes.Length -ne 65536) { throw 'Reset-test ROM size is invalid.' }
        $sum = 0
        for ($i = 0; $i -lt 65535; $i++) { $sum = ($sum + $bytes[$i]) -band 255 }
        $bytes[65535] = (256 - $sum) -band 255
        $image = [IO.File]::ReadAllBytes($physical)
        if ($image.Length -ne 131072) { throw 'Physical ROM size is invalid.' }
        [Array]::Copy($bytes, 0, $image, 65536, 65536)
        [IO.File]::WriteAllBytes($wrapper, $image)
    } else {
        Copy-Item -LiteralPath $physical -Destination $wrapper
    }
    & python -B (Join-Path $PSScriptRoot 'memory-fixture.py') $ImagePath --output $disk --guest $guest
    if ($LASTEXITCODE) { throw 'Disposable EMM386 fixture creation failed.' }
    $expected = if ($NegativeControl) { 0x68 } else { 0x67 }
    & (Join-Path $PSScriptRoot 'run-card-vhd.ps1') -ImagePath $disk -MemoryKiB 8192 -ExpectedExitCode $expected -TimeoutSeconds 90 -BootNumLock $BootNumLock
    # Generated sources and test binaries are reproducible. Keep the build
    # directory clear after success; retain them on failure for diagnosis.
    foreach ($name in @('bios.asm', 'system.rom', 'reset.com', 'negative-keyboard-irq.inc')) {
        $artifact = Join-Path $scratch $name
        if (Test-Path -LiteralPath $artifact) { Remove-Item -LiteralPath $artifact }
    }
} finally {
    Copy-Item -LiteralPath $physical -Destination $wrapper
    $resolved = [IO.Path]::GetFullPath($disk)
    $prefix = [IO.Path]::GetFullPath($scratch).TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test cleanup path.' }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved }
}
