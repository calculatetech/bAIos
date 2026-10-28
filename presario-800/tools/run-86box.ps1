param(
    [string]$EmulatorPath,
    [int]$TimeoutSeconds = 45,
    [switch]$NoDisk,
    [switch]$BadBoot,
    [switch]$FaultTest,
    [switch]$IdentifyTimeout,
    [switch]$IdentifyPostBusy,
    [switch]$IdentifyPostError,
    [switch]$BootPostBusy,
    [switch]$BootPostError,
    [switch]$KeyboardTest,
    [switch]$RtcTest,
    [switch]$Vga141,
    [ValidateSet(50, 60)][int]$VgaClockMHz = 60,
    [switch]$VgaRegisterTest,
    [switch]$SetupTest,
    [ValidateSet(4096, 8192)][int]$MemoryKiB = 4096,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$modes = @($NoDisk, $BadBoot, $FaultTest, $IdentifyTimeout, $IdentifyPostBusy, $IdentifyPostError, $BootPostBusy, $BootPostError, $KeyboardTest, $RtcTest, $VgaRegisterTest, $SetupTest) | Where-Object { $_ }
if ($modes.Count -gt 1) { throw "Select only one test mode." }

$root = Split-Path -Parent $PSScriptRoot
$build = Join-Path $root "build"
$vm = Join-Path $build "tests/86box/vm"
$roms = Join-Path $build "tests/86box/roms"
$release = $PSBoundParameters.ContainsKey('VgaClockMHz') -or -not $Vga141
if ($Vga141 -and -not $release) {
    $build = Join-Path $build 'review/vga141'
    $vm = Join-Path $build 'tests/86box/vm'
    $roms = Join-Path $build 'tests/86box/roms'
}
$disk = Join-Path $vm "boot-test-8g.img"
$config = Join-Path $vm "86box.cfg"
$log = Join-Path $vm "86box.log"
$bootTest = Join-Path $build "tests/payloads/boot-test.bin"
$faultBootTest = Join-Path $build "tests/payloads/fault-test.bin"
$keyboardBootTest = Join-Path $build "tests/payloads/keyboard-test.bin"
$rtcBootTest = Join-Path $build 'diagnostics/rtc-test.bin'
$referencePath = Join-Path $root "reference/COMPAQ_PROLINEA_MT_05-02-94.BIN"
$wrapper = Join-Path $roms "machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin"
$exe = $EmulatorPath
if (-not $exe) {
    $command = Get-Command 86Box.exe -ErrorAction SilentlyContinue
    if ($command) { $exe = $command.Source }
}
if (-not $exe) {
    $exe = Join-Path $env:LOCALAPPDATA "Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe"
}
if (-not (Test-Path -LiteralPath $exe)) { throw "86Box was not found. Put 86Box.exe on PATH or pass -EmulatorPath <path>." }
"86Box selected: $exe"

$selection = if ($release) { @{ VgaClockMHz = $VgaClockMHz } } else { @{ Vga141 = $true } }
& (Join-Path $PSScriptRoot "build.ps1") @selection -TestMemoryKiB $MemoryKiB | Out-Null
& (Join-Path $PSScriptRoot "verify-rom.ps1") @selection | Out-Null
[IO.Directory]::CreateDirectory($vm) | Out-Null

function Install-TestRom([switch]$ForceIdentifyTimeout, [int]$IdentifyPostStatus, [int]$BootPostStatus, [switch]$WarmResetTest) {
    $nasm = (Get-Command nasm -ErrorAction SilentlyContinue).Source
    if (-not $nasm) { $nasm = Join-Path $env:LOCALAPPDATA "bin/NASM/nasm.exe" }
    $testSystem = Join-Path $build "emulator-test-system.rom"
    $testMode = if ($SetupTest) { 'EMULATOR_POST_SUMMARY_TEST' } else { 'EMULATOR_TEST' }
    $arguments = @('-D', $testMode, '-D', 'VGA_BIOS_141')
    if ($BadBoot -or $BootPostBusy -or $BootPostError) {
        $arguments += @('-D', 'EMULATOR_BOOT_RETRY_EXIT=0x64')
    } elseif ($NoDisk -or $IdentifyTimeout -or $IdentifyPostBusy -or $IdentifyPostError) {
        $arguments += @('-D', 'EMULATOR_BOOT_RETRY_EXIT=0x63')
    }
    if ($SetupTest) { $arguments += @('-D', 'EMULATOR_SETUP_TEST') }
    if ($ForceIdentifyTimeout) { $arguments += @('-D', 'EMULATOR_IDENTIFY_TIMEOUT') }
    if ($IdentifyPostStatus) { $arguments += @('-D', "EMULATOR_IDENTIFY_POST_STATUS=$IdentifyPostStatus") }
    if ($BootPostStatus) { $arguments += @('-D', "EMULATOR_BOOT_POST_STATUS=$BootPostStatus") }
    if ($WarmResetTest) { $arguments += @('-D', 'EMULATOR_WARM_RESET_TEST') }
    $includePath = (Join-Path $root 'src').TrimEnd('\') + '/'
    $biosSource = Join-Path $root 'src/bios.asm'
    $arguments += @('-f', 'bin', '-I', "`"$includePath`"", '-o', "`"$testSystem`"", "`"$biosSource`"")
    $process = Start-Process -FilePath $nasm -ArgumentList ($arguments -join ' ') -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode) { throw "Emulator-test BIOS assembly failed with exit code $($process.ExitCode)." }

    $system = [IO.File]::ReadAllBytes($testSystem)
    if ($system.Length -ne 65536) { throw "Emulator-test system ROM size failed." }
    $sum = 0
    for ($i = 0; $i -lt 65535; $i++) { $sum = ($sum + $system[$i]) -band 0xFF }
    $system[65535] = (0x100 - $sum) -band 0xFF
    [IO.File]::WriteAllBytes($testSystem, $system)

    $reference = [IO.File]::ReadAllBytes($referencePath)
    $selectedName = if ($release) { "baios-presario800-vga$VgaClockMHz.bin" } else { 'baios-presario800-vga141.bin' }
    $selected = [IO.File]::ReadAllBytes((Join-Path $build $selectedName))
    [Array]::Copy($selected, 0, $reference, 0, 65536)
    $image = [byte[]]::new(131072)
    [Array]::Copy($reference, 0, $image, 0, 65536)
    [Array]::Copy($system, 0, $image, 65536, 65536)
    [IO.File]::WriteAllBytes($wrapper, $image)

    if ($image.Length -ne 131072 -or $system[0xFFF0] -ne 0xEA) { throw "Emulator-test image structure failed." }
    for ($i = 0; $i -lt 65536; $i++) {
        if ($image[$i] -ne $reference[$i]) { throw "Emulator-test retained region differs at 0x$($i.ToString('X5'))." }
    }
    $sum = 0
    foreach ($value in $system) { $sum = ($sum + $value) -band 0xFF }
    if ($sum -ne 0) { throw "Emulator-test checksum failed." }
}

$testRom = $true # Compile fixture observers without changing production ROMs.
try {
    $identifyPostStatus = if ($IdentifyPostBusy) { 0x80 } elseif ($IdentifyPostError) { 0x21 } else { 0 }
    $bootPostStatus = if ($BootPostBusy) { 0x80 } elseif ($BootPostError) { 0x21 } else { 0 }
    if ($testRom) { Install-TestRom -ForceIdentifyTimeout:$IdentifyTimeout -IdentifyPostStatus $identifyPostStatus -BootPostStatus $bootPostStatus -WarmResetTest:$KeyboardTest }

    if (-not $NoDisk) {
        $stream = [IO.File]::Open($disk, [IO.FileMode]::Create, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
        try {
            $stream.SetLength(8GB)
            function Write-Sector([uint32]$Lba, [byte[]]$Bytes) {
                if ($Bytes.Length -gt 512) { throw "Sector payload is too large." }
                $stream.Position = [int64]$Lba * 512
                $stream.Write($Bytes, 0, $Bytes.Length)
            }

            if (-not $BadBoot -and -not $IdentifyTimeout -and -not $IdentifyPostBusy -and -not $IdentifyPostError) {
                $payloadPath = if ($VgaRegisterTest) { Join-Path $build 'tests/payloads/vga-register-test.bin' } elseif ($FaultTest) { $faultBootTest } elseif ($KeyboardTest) { $keyboardBootTest } elseif ($RtcTest) { $rtcBootTest } else { $bootTest }
                $payload = [IO.File]::ReadAllBytes($payloadPath)
                if ($payload.Length -ne 8192) { throw "Boot test must be 16 sectors." }
                $stream.Write($payload, 0, $payload.Length)
            }
            if (-not $RtcTest -and -not $FaultTest -and -not $KeyboardTest -and -not $BadBoot -and -not $IdentifyTimeout -and -not $IdentifyPostBusy -and -not $IdentifyPostError) {
                $bulk = [byte[]]::new(127 * 512)
                for ($i = 0; $i -lt $bulk.Length; $i++) { $bulk[$i] = 0xA5 }
                $stream.Position = [int64]16 * 512
                $stream.Write($bulk, 0, $bulk.Length)
                $protected = [byte[]]::new(512)
                for ($i = 0; $i -lt $protected.Length; $i++) { $protected[$i] = 0x5A }
                # Guest occupies0..15; bulk occupies16..142. Never overlap code.
                Write-Sector 144 $protected
                Write-Sector 4819628 ([Text.Encoding]::ASCII.GetBytes("CCHS"))
                Write-Sector 16450560 ([Text.Encoding]::ASCII.GetBytes("HIGH"))
                Write-Sector 16777215 ([Text.Encoding]::ASCII.GetBytes("LAST"))
                $stream.Position = 0
                $loadedGuest = [byte[]]::new($payload.Length)
                if ($stream.Read($loadedGuest, 0, $loadedGuest.Length) -ne $payload.Length -or
                    [Convert]::ToBase64String($loadedGuest) -ne [Convert]::ToBase64String($payload)) {
                    throw "Disk fixture data overwrote the guest program."
                }
            }
            $stream.Flush()
        } finally {
            $stream.Dispose()
        }
    }

    $diskForConfig = $disk.Replace('\', '/')
    $hardDiskConfig = if ($NoDisk) { "[Storage controllers]`r`nhdc_1 = ide_isa`r`n`r`n[Hard disks]" } else { @"
[Storage controllers]
hdc_1 = ide_isa

[Hard disks]
hdd_01_parameters = 64, 16, 16384, 0, ide
hdd_01_fn = $diskForConfig
hdd_01_speed = ramdisk
hdd_01_ide_channel = 0:0
"@ }
    $floppyA = if ($SetupTest) { '35_2hd' } else { 'none' }
    $cfg = @"
[General]
vid_renderer = qt_software

[Machine]
machine = d824
cpu_family = i486dx
cpu_speed = 25000000
cpu_multi = 1
fpu_type = internal
cpu_use_dynarec = 0
fpu_softfloat = 0
time_sync = disabled
mem_size = $MemoryKiB

[Video]
gfxcard = internal

[Cirrus Logic GD5428 (ISA) (On-Board)]
memory = 1024

[Input devices]
mouse_type = none

[Sound]
sndcard = none

[Network]
net_01_card = none

[Ports (COM & LPT)]

$hardDiskConfig

[Floppy and CD-ROM drives]
fdd_01_type = $floppyA
fdd_02_type = none

[Other peripherals]
postcard_enabled = 1
unittester_enabled = 1

[86Box Unit Tester]
exit_enabled = 1
"@
    if ($cfg -notmatch '(?m)^machine = d824$' -or $cfg -notmatch '(?m)^gfxcard = internal$') {
        throw "86Box target configuration changed."
    }
    [IO.File]::WriteAllText($config, $cfg, [Text.UTF8Encoding]::new($false))
    # This fixture has no floppy hardware. Use a valid saved None/None record,
    # not the physical-board defaults that intentionally seek both drives.
    $nvrDirectory = Join-Path $vm 'nvr'
    [IO.Directory]::CreateDirectory($nvrDirectory) | Out-Null
    $cmos = [byte[]]::new(256)
    $cmos[0x0A] = 0x26
    $cmos[0x0B] = 2
    $cmos[0x0D] = 0x80
    $cmos[4] = 0x12
    $cmos[6] = 5
    $cmos[7] = 1
    $cmos[8] = 1
    $cmos[9] = 0x26
    $cmos[0x32] = 0x20
    [Array]::Copy([byte[]](0x42, 0x38, 1, 1, 2, 0x82, 0x5A), 0, $cmos, 0x38, 7)
    if ($SetupTest) {
        # Match the existing Setup stimulus fixture's real floppy-seek window.
        $cmos[0x10] = 0x40
        $cmos[0x3D] = 0x42
    }
    if ($FaultTest) {
        # This fixture injects faults after individual sectors, so use single-sector PIO.
        $ide = [byte[]](1, 0,0,1,0,0,4,16,63,255,255,0,4, 0,0,1,0,0,4,16,63,255,255,0,4)
        [Array]::Copy($ide, 0, $cmos, 0x44, $ide.Length)
        $cmos[0x40] = 73
        $cmos[0x41] = 68
        $cmos[0x42] = 1
        $sum = 73 + 68 + 1
        foreach ($value in $ide) { $sum += $value }
        $cmos[0x43] = (-$sum) -band 255
    }
    [IO.File]::WriteAllBytes((Join-Path $nvrDirectory 'd824.nvr'), $cmos)
    if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log }

    $expectedExit = if ($RtcTest -or $VgaRegisterTest -or $SetupTest) { 0x67 } elseif ($KeyboardTest) { 0x66 } elseif ($FaultTest) { 0x62 } elseif ($BadBoot -or $BootPostBusy -or $BootPostError) { 0x64 } elseif ($NoDisk -or $IdentifyTimeout -or $IdentifyPostBusy -or $IdentifyPostError) { 0x63 } else { $null }
    $emulatorArguments = "-P `"$vm`" -R `"$roms`" -L `"$log`" -N"
    if ($null -ne $expectedExit) {
        $process = Start-Process -FilePath $exe -ArgumentList $emulatorArguments -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
            throw "86Box did not reach the expected terminal path within $TimeoutSeconds seconds."
        }
        if ($process.ExitCode -ne $expectedExit) { throw "Unexpected emulator exit code 0x$($process.ExitCode.ToString('X2'))." }
        if ($VgaRegisterTest -and $release) {
            $snapshotBytes = [byte[]]::new(14 * 512)
            $snapshotDisk = [IO.File]::OpenRead($disk)
            try {
                $snapshotDisk.Position = 32 * 512
                if ($snapshotDisk.Read($snapshotBytes, 0, $snapshotBytes.Length) -ne $snapshotBytes.Length) { throw "Incomplete VGA register snapshots." }
            } finally { $snapshotDisk.Dispose() }
            $expectedModes = @(0, 3, 0x0503, 0x0603, 0x12, 0x13, 0x101, 0x102, 0x103, 0x104, 0x105, 0x106, 0x111, 0x112)
            $expectedClock = if ($VgaClockMHz -eq 50) { 0x1C } else { 0x22 }
            for ($i = 0; $i -lt $expectedModes.Count; $i++) {
                $offset = $i * 512
                if ([Text.Encoding]::ASCII.GetString($snapshotBytes, $offset, 4) -ne 'VGAR' -or
                    [BitConverter]::ToUInt16($snapshotBytes, $offset + 4) -ne $expectedModes[$i] -or
                    $snapshotBytes[$offset + 47] -ne $expectedClock) {
                    throw "VGA clock did not persist in snapshot $i at $VgaClockMHz MHz."
                }
            }
            "VGA $VgaClockMHz MHz SR1F retained through all 14 startup/text/graphics/VBE snapshots: PASS"
        }
        "86Box terminal-path validation passed with exit 0x$($expectedExit.ToString('X2'))."
        return
    }

    $process = Start-Process -FilePath $exe -ArgumentList $emulatorArguments -WindowStyle Hidden -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $passed = $false
    try {
        while ([DateTime]::UtcNow -lt $deadline -and -not $process.HasExited) {
            Start-Sleep -Milliseconds 250
            $check = [IO.File]::Open($disk, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
            try {
                $check.Position = [int64]145 * 512
                $marker = [byte[]]::new(8)
                [void]$check.Read($marker, 0, 8)
                if ([Text.Encoding]::ASCII.GetString($marker) -eq 'BAIOS_OK') {
                    $passed = $true
                    break
                }
            } finally {
                $check.Dispose()
            }
        }
    } finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        $process.WaitForExit()
    }
    if (-not $passed) {
        $tail = if (Test-Path -LiteralPath $log) { (Get-Content -Tail 40 -LiteralPath $log) -join [Environment]::NewLine } else { '<no log>' }
        $reason = if ($process.ExitCode) { "boot-test failure code 0x$($process.ExitCode.ToString('X2'))" } else { "timeout after $TimeoutSeconds seconds" }
        throw "86Box did not write the completion marker: $reason.`n$tail"
    }

    "86Box boot and INT 13h validation passed on 8 GiB image."
} finally {
    # This runner creates only this disposable disk; keep logs/configuration.
    $diskPath = [IO.Path]::GetFullPath($disk)
    $vmPrefix = [IO.Path]::GetFullPath($vm).TrimEnd('\') + '\'
    if (-not $diskPath.StartsWith($vmPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a test disk outside the VM directory."
    }
    if (-not $KeepArtifacts -and (Test-Path -LiteralPath $diskPath)) {
        Remove-Item -LiteralPath $diskPath
    }
    if ($testRom) {
        & (Join-Path $PSScriptRoot "build.ps1") @selection | Out-Null
        & (Join-Path $PSScriptRoot "verify-rom.ps1") @selection | Out-Null
    }
}
