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
. (Join-Path $root '../shared/tools/build-cleanup.ps1')
$originalBuild = Get-Item Env:BAIOS_BUILD_DIRECTORY -ErrorAction SilentlyContinue
$buildRoot = [IO.Path]::GetFullPath((Join-Path $root 'build'))
$selection = if ($env:BAIOS_BUILD_DIRECTORY) { $env:BAIOS_BUILD_DIRECTORY } else { 'build' }
$sourceBuild = [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($selection)) { $selection } else { Join-Path $root $selection }))
Assert-OwnedPath (Join-Path $sourceBuild '__emm_source__') $buildRoot | Out-Null
$physical = Join-Path $sourceBuild 'baios-presario800.bin'
$sourceRoms = Join-Path $sourceBuild 'tests/86box/roms'
$image = [IO.File]::ReadAllBytes($physical)
if ($image.Length -ne 131072) { throw 'Physical ROM size is invalid.' }
if (-not (Test-Path -LiteralPath $sourceRoms -PathType Container)) { throw 'Selected build ROM assets are missing.' }
Assert-OwnedPath $sourceRoms $buildRoot | Out-Null
$diagnostics = Join-Path $buildRoot 'diagnostics'
$scratch = Assert-OwnedPath (Join-Path $diagnostics ('er-' + [guid]::NewGuid().ToString('N').Substring(0, 8))) $buildRoot
if (Test-Path -LiteralPath $scratch) { throw 'EMM invocation already exists.' }
[IO.Directory]::CreateDirectory($scratch) | Out-Null
$disk = Join-Path $scratch 'test.vhd'
$guest = Join-Path $scratch 'reset.com'
$privateBuild = $scratch.Substring($root.Length + 1)
$privateRoms = Join-Path $scratch 'tests/86box/roms'
$wrapperName = 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
$recordPath = Join-Path $scratch 'invocation.json'
$record = [ordered]@{
    status = 'running'; source_build = $sourceBuild; source_path = (Join-Path $root 'src/bios.asm')
    selected_physical = $physical; private_build = $privateBuild; image = $disk
    production = [bool]$ProductionRom; negative = [bool]$NegativeControl; keypad = [bool]$KeypadDelete
    requested_numlock = $BootNumLock; initial_nvram_present = $null
}
function Write-Invocation { $record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $recordPath -Encoding utf8 }
function Remove-CompletedInvocation {
    [CmdletBinding(SupportsShouldProcess)]
    param([string]$Path)
    Initialize-BuildCleanup $buildRoot $PSCmdlet
    Remove-Generated $Path
}
Write-Invocation
Write-Output "EMM fixture: $scratch"
try {
    [IO.Directory]::CreateDirectory((Split-Path -Parent $privateRoms)) | Out-Null
    Copy-Item -LiteralPath $sourceRoms -Destination $privateRoms -Recurse
    [IO.File]::WriteAllBytes((Join-Path $scratch 'baios-presario800.bin'), $image)
    $nasm = Join-Path $env:LOCALAPPDATA 'bin/NASM/nasm.exe'
    $defines = if ($KeypadDelete) { @('-D', 'KEYPAD_DELETE') } else { @() }
    if ($BootNumLock -ne 'Default') { $defines += @('-D', "EXPECTED_NUMLOCK=$([int]($BootNumLock -eq 'On'))") }
    & $nasm @defines -f bin -o $guest (Join-Path $root 'tests/emm-reset-test.asm')
    if ($LASTEXITCODE) { throw 'Reset guest assembly failed.' }
    $source = [IO.File]::ReadAllText((Join-Path $root 'src/bios.asm'))
    $sourcePath = Join-Path $scratch 'bios.asm'
    $system = Join-Path $scratch 'system.rom'
    [IO.File]::WriteAllText($sourcePath, $source)
    if (-not $ProductionRom) {
        if ($NegativeControl) {
            $irqSource = [IO.File]::ReadAllText((Join-Path $root '../shared/src/pc/keyboard-irq.inc'))
            $pattern = 'stc\s+mov ah, 0x4F\s+int 0x15\s+jnc \.scan_consumed'
            if ([regex]::Matches($irqSource, $pattern).Count -ne 1) { throw 'Keyboard hook not uniquely found.' }
            $irqPath = Join-Path $scratch 'negative-keyboard-irq.inc'
            [IO.File]::WriteAllText($irqPath, [regex]::Replace($irqSource, $pattern, ''))
            $include = 'presario_shared "pc/keyboard-irq.inc"'
            if ($source.Split([string[]]@($include), [StringSplitOptions]::None).Length -ne 2) { throw 'Keyboard include not uniquely found.' }
            $source = $source.Replace($include, '%include "' + $irqPath.Replace('\', '/') + '"')
        }
        [IO.File]::WriteAllText($sourcePath, $source)
        & $nasm -D VGA_BIOS_141 -D EMULATOR_TEST -D EMULATOR_EMM_RESET_TEST -f bin -I ((Join-Path $root 'src') + '/') -o $system $sourcePath
        if ($LASTEXITCODE) { throw 'Reset-test ROM assembly failed.' }
        $bytes = [IO.File]::ReadAllBytes($system)
        if ($bytes.Length -ne 65536) { throw 'Reset-test ROM size is invalid.' }
        $sum = 0
        for ($i = 0; $i -lt 65535; $i++) { $sum = ($sum + $bytes[$i]) -band 255 }
        $bytes[65535] = (256 - $sum) -band 255
        [IO.File]::WriteAllBytes($system, $bytes)
        [Array]::Copy($bytes, 0, $image, 65536, 65536)
    } else {
        [IO.File]::WriteAllBytes($system, [byte[]]$image[65536..131071])
    }
    [IO.File]::WriteAllBytes((Join-Path $privateRoms $wrapperName), $image)
    & python -B (Join-Path $PSScriptRoot 'memory-fixture.py') $ImagePath --output $disk --guest $guest
    if ($LASTEXITCODE) { throw 'Disposable EMM386 fixture creation failed.' }
    $record.initial_nvram_present = Test-Path -LiteralPath (Join-Path $scratch 'tests/86box/card-vm/nvr/d824.nvr')
    Write-Invocation
    $env:BAIOS_BUILD_DIRECTORY = $privateBuild
    $expected = if ($NegativeControl) { 0x68 } else { 0x67 }
    $fixtureNumLock = if ($BootNumLock -eq 'Default') { 'On' } else { $BootNumLock }
    & (Join-Path $PSScriptRoot 'run-card-vhd.ps1') -ImagePath $disk -MemoryKiB 8192 -ExpectedExitCode $expected -TimeoutSeconds 90 -BootNumLock $fixtureNumLock
    $record.status = 'passed'
    Write-Invocation
    # The unchanged runner has waited for or stopped its process before it returns.
    Remove-CompletedInvocation $scratch
} catch {
    $record.status = 'failed'
    $record.error = $_.Exception.Message
    Write-Invocation
    Write-Output "Retained EMM fixture: $scratch"
    throw
} finally {
    if ($null -eq $originalBuild) { Remove-Item Env:BAIOS_BUILD_DIRECTORY -ErrorAction SilentlyContinue }
    else { Set-Item Env:BAIOS_BUILD_DIRECTORY -Value $originalBuild.Value }
}
