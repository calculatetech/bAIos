param(
    [string]$OutputDirectory = "build",
    [switch]$FloppyDiagnostic,
    [switch]$MouseDiagnostic,
    [switch]$KeyboardDiagnostic,
    [switch]$Vga141,
    [switch]$VgaBus07,
    [ValidateSet(50, 60)][int]$VgaClockMHz = 60,
    [ValidateSet(4096, 8192)][int]$TestMemoryKiB = 4096
)

$ErrorActionPreference = "Stop"
$release = $PSBoundParameters.ContainsKey('VgaClockMHz') -or (-not $Vga141 -and -not $VgaBus07)
if ($release) { $VgaBus07 = $true; $Vga141 = $true }
if ($VgaBus07 -and -not $release) {
    $Vga141 = $true
    if ($OutputDirectory -eq 'build') { $OutputDirectory = 'build/ram-presets' }
}
if ($Vga141 -and -not $release -and $OutputDirectory -eq "build") { $OutputDirectory = "build/vga141" }
if ($FloppyDiagnostic -and $OutputDirectory -eq "build") { $OutputDirectory = "build/floppy-diagnostic" }
if ($MouseDiagnostic -and $OutputDirectory -eq "build") { $OutputDirectory = "build/mouse-diagnostic" }
if ($KeyboardDiagnostic -and $OutputDirectory -eq "build") { $OutputDirectory = "build/keyboard-diagnostic" }
$root = Split-Path -Parent $PSScriptRoot
$reference = Join-Path $root "reference/COMPAQ_PROLINEA_MT_05-02-94.BIN"
$nasm = (Get-Command nasm -ErrorAction SilentlyContinue).Source
if (-not $nasm) {
    $nasm = Join-Path $env:LOCALAPPDATA "bin/NASM/nasm.exe"
}
if (-not (Test-Path -LiteralPath $nasm)) { throw "NASM was not found." }
if (-not (Test-Path -LiteralPath $reference)) { throw "Retained ROM input was not found: $reference" }

$buildRoot = [IO.Path]::GetFullPath((Join-Path $root "build"))
$candidate = if ([IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $root $OutputDirectory }
$out = [IO.Path]::GetFullPath($candidate).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
$buildPrefix = $buildRoot.TrimEnd('\') + '\'
if ($out -ne $buildRoot -and -not $out.StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDirectory must resolve inside $buildRoot."
}
if ($Vga141 -and -not $release -and $out -eq $buildRoot) { throw "VGA 1.41 must use a separate output directory." }
if ($VgaBus07 -and $out -eq [IO.Path]::GetFullPath((Join-Path $buildRoot 'vga141/bus07'))) {
    throw 'RAM candidates must use a separate directory from the active bus07 output.'
}
$vgaBytes = $null
if ($Vga141) {
    $vgaInput = Join-Path $root 'reference/gd5428_1-41.bin'
    $vgaBytes = [IO.File]::ReadAllBytes($vgaInput)
    if ($vgaBytes.Length -ne 32768 -or $vgaBytes[0] -ne 0x55 -or $vgaBytes[1] -ne 0xAA -or $vgaBytes[2] -ne 0x40 -or
        (Get-FileHash -LiteralPath $vgaInput).Hash -ne '72873E0BB9EFDA71D0B5819CE7B4201D8771C75473CD1170DCC6D2DFB794E0B6') {
        throw 'The supplied VGA 1.41 ROM identity or layout changed.'
    }
    $vgaSum = 0
    foreach ($value in $vgaBytes) { $vgaSum = ($vgaSum + $value) -band 255 }
    if ($vgaSum) { throw 'VGA 1.41 checksum failed.' }
}
if ($VgaBus07) {
    $bus07Input = Join-Path $root 'reference/baios-presario800-vga141-bus07.bin'
    if ((Get-FileHash -LiteralPath $bus07Input).Hash -ne '98716A7CEFC742047806C70A8CBEA04A89648C5BF84859FA1CEA269D791633B7') {
        throw 'The frozen bus07 input identity changed.'
    }
    $bus07 = [IO.File]::ReadAllBytes($bus07Input)
    if ($bus07.Length -ne 131072) { throw 'The frozen bus07 layout changed.' }
    [Array]::Copy($bus07, 0, $vgaBytes, 0, 32768)
}
if ($release -and $VgaClockMHz -eq 50) {
    $vgaBytes[0x08E7] = 0x1C
    $vgaSum = 0
    for ($i = 0; $i -lt 32767; $i++) { $vgaSum = ($vgaSum + $vgaBytes[$i]) -band 255 }
    $vgaBytes[32767] = (-$vgaSum) -band 255
}
[IO.Directory]::CreateDirectory($out) | Out-Null
$system = Join-Path $out "baios-presario800-system.rom"
$physicalName = if ($release) { "baios-presario800-vga$VgaClockMHz.bin" } elseif ($VgaBus07) { 'baios-presario800-vga141-bus07.bin' } else { 'baios-presario800-vga141.bin' }
$physical = Join-Path $out $physicalName
$bootTest = Join-Path $out "boot-test.bin"
$faultTest = Join-Path $out "fault-test.bin"
$keyboardTest = Join-Path $out "keyboard-test.bin"
$roms = Join-Path $out "86box/roms"
$gd5428 = Join-Path $root "reference/86box/video/cirruslogic/5428.bin"
if ($Vga141) {
    $roms = Join-Path $out '86box/roms'
    $privateVideo = Join-Path $roms 'video/cirruslogic/5428.bin'
    [IO.Directory]::CreateDirectory((Split-Path -Parent $privateVideo)) | Out-Null
    Copy-Item -LiteralPath $gd5428 -Destination $privateVideo
}
$wrapper = Join-Path $roms "machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin"
if (-not (Test-Path -LiteralPath $gd5428)) {
    throw "The retained Presario 86Box VGA input is missing: $gd5428"
}
[IO.Directory]::CreateDirectory((Split-Path -Parent $wrapper)) | Out-Null

function Invoke-Nasm([string]$Arguments, [string]$Description) {
    $process = Start-Process -FilePath $nasm -ArgumentList $Arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode) { throw "$Description failed with exit code $($process.ExitCode)." }
}
$includePath = (Join-Path $root "src").TrimEnd('\') + '/'
$biosSource = Join-Path $root "src/bios.asm"
$testSource = Join-Path $root "tests/boot-test.asm"
$keyboardSource = Join-Path $root "tests/keyboard-test.asm"
$diagnosticDefine = if ($FloppyDiagnostic) { '-D FLOPPY_DIAGNOSTIC' } else { '' }
if ($MouseDiagnostic) { $diagnosticDefine += ' -D MOUSE_DIAGNOSTIC' }
if ($KeyboardDiagnostic) { $diagnosticDefine += ' -D KEYBOARD_DIAGNOSTIC' }
if ($Vga141) { $diagnosticDefine += ' -D VGA_BIOS_141' }
$listing = Join-Path $out 'baios-presario800-system.lst'
$testInclude = (Join-Path $root 'tests').TrimEnd('\') + '/'
$testArguments = "-D EXPECTED_MEMORY_KIB=$TestMemoryKiB -I `"$testInclude`""
Invoke-Nasm "$diagnosticDefine -f bin -I `"$includePath`" -l `"$listing`" -o `"$system`" `"$biosSource`"" "NASM"
Invoke-Nasm "$testArguments -f bin -o `"$bootTest`" `"$testSource`"" "Boot-test assembly"
Invoke-Nasm "$testArguments -D FAULT_TEST -f bin -o `"$faultTest`" `"$testSource`"" "Fault-test assembly"
Invoke-Nasm "$testArguments -f bin -o `"$keyboardTest`" `"$keyboardSource`"" "Keyboard-test assembly"
$registerTest = Join-Path $out 'vga-register-test.bin'
$registerSource = Join-Path $root 'tests/vga-register-test.asm'
$registerDefine = if ($Vga141) { '-D VGA_BIOS_141' } else { '' }
Invoke-Nasm "$registerDefine -f bin -I `"$includePath`" -I `"$testInclude`" -o `"$registerTest`" `"$registerSource`"" "VGA register-test assembly"
$vgaTest = Join-Path $out 'VGACHECK.COM'
$vgaSource = Join-Path $root 'tests/vga-test.asm'
Invoke-Nasm "-f bin -I `"$testInclude`" -o `"$vgaTest`" `"$vgaSource`"" "VGA-test assembly"
$cacheOff = Join-Path $out 'L1OFF.COM'
$cacheSource = Join-Path $root 'tests/cache-off.asm'
Invoke-Nasm "-f bin -o `"$cacheOff`" `"$cacheSource`"" "Cache diagnostic assembly"
$diagnostics = Join-Path $out 'diagnostics'
[IO.Directory]::CreateDirectory($diagnostics) | Out-Null
$rtcSource = Join-Path $root 'tests/rtc-test.asm'
$rtcTest = Join-Path $diagnostics 'rtc-test.bin'
$rtcCheck = Join-Path $diagnostics 'RTCCHECK.COM'
Invoke-Nasm "-D RTC_BOOT_TEST -f bin -o `"$rtcTest`" `"$rtcSource`"" "RTC boot-test assembly"
Invoke-Nasm "-f bin -o `"$rtcCheck`" `"$rtcSource`"" "Read-only RTC diagnostic assembly"
$rtcSpeedsys = Join-Path $diagnostics 'SPRTC.COM'
Invoke-Nasm "-D RTC_SPEEDSYS_TEST -f bin -o `"$rtcSpeedsys`" `"$rtcSource`"" "Speedsys RTC diagnostic assembly"
$hardwareState = Join-Path $diagnostics 'HWSTATE.COM'
$hardwareSource = Join-Path $root 'tests/hw-state.asm'
Invoke-Nasm "-f bin -o `"$hardwareState`" `"$hardwareSource`"" "Read-only hardware snapshot assembly"

$systemBytes = [IO.File]::ReadAllBytes($system)
$listingLines = [IO.File]::ReadAllLines($listing)
$endLine = [Array]::FindIndex($listingLines, [Predicate[string]] { param($line) $line.TrimEnd().EndsWith('rom_code_end:') })
if ($endLine -lt 0) { throw 'ROM used-space marker was not found.' }
$paddingLine = $listingLines[($endLine + 1)..($listingLines.Length - 1)] | Where-Object { $_ -match '^\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]' } | Select-Object -First 1
if ($paddingLine -notmatch '^\s*\d+\s+([0-9A-F]{8})') { throw 'ROM used-space address was not found.' }
$usedBytes = [Convert]::ToInt32($Matches[1], 16)
if ($systemBytes.Length -ne 65536) { throw "System ROM is $($systemBytes.Length) bytes, not 65536." }
$sum = 0
for ($i = 0; $i -lt 65535; $i++) { $sum = ($sum + $systemBytes[$i]) -band 0xFF }
$systemBytes[65535] = (0x100 - $sum) -band 0xFF
[IO.File]::WriteAllBytes($system, $systemBytes)

$referenceBytes = [IO.File]::ReadAllBytes($reference)
if ($referenceBytes.Length -ne 131072) { throw "Reference ROM is not 128 KiB." }
$physicalBytes = [byte[]]::new(131072)
[Array]::Copy($referenceBytes, 0, $physicalBytes, 0, 65536)
if ($Vga141) { [Array]::Copy($vgaBytes, 0, $physicalBytes, 0, 32768) }
[Array]::Copy($systemBytes, 0, $physicalBytes, 65536, 65536)
[IO.File]::WriteAllBytes($physical, $physicalBytes)
if ($release) { [IO.File]::WriteAllBytes((Join-Path $out 'baios-presario800.bin'), $physicalBytes) }

[IO.File]::WriteAllBytes($wrapper, $physicalBytes)
if ($release) {
    $clockRoms = Join-Path $out "86box/vga$VgaClockMHz/roms"
    $clockWrapper = Join-Path $clockRoms 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
    [IO.Directory]::CreateDirectory((Split-Path -Parent $clockWrapper)) | Out-Null
    $clockVideo = Join-Path $clockRoms 'video/cirruslogic/5428.bin'
    [IO.Directory]::CreateDirectory((Split-Path -Parent $clockVideo)) | Out-Null
    Copy-Item -LiteralPath $gd5428 -Destination $clockVideo
    [IO.File]::WriteAllBytes($clockWrapper, $physicalBytes)
}

[pscustomobject]@{
    SystemRom = $system
    PhysicalRom = $physical
    EmulatorRom = $wrapper
    BootTest = $bootTest
    FaultTest = $faultTest
    KeyboardTest = $keyboardTest
    VgaTest = $vgaTest
    CacheOff = $cacheOff
    RtcTest = $rtcTest
    RtcCheck = $rtcCheck
    CodeUsedBytes = $usedBytes
    CodeFreeBeforeF065 = 0xF065 - $usedBytes
    CodeFreeAfterF070 = 0xFFF0 - 0xF070
    SystemFreeBytes = (0xF065 - $usedBytes) + (0xFFF0 - 0xF070)
    SystemSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $system).Hash
    PhysicalSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $physical).Hash
} | Format-List
