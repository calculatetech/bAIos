param(
    [Parameter(Mandatory)]
    [string]$ImagePath,
    [int]$CaptureAfterSeconds = 15,
    [int]$ExpectedExitCode = -1,
    [ValidateSet(4096, 8192)][int]$MemoryKiB = 4096,
    [int]$TimeoutSeconds = 120,
    [ValidateSet('Default', 'On', 'Off')][string]$BootNumLock = 'Default'
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$build = Join-Path $root $(if ($env:BAIOS_BUILD_DIRECTORY) { $env:BAIOS_BUILD_DIRECTORY } else { 'build' })
$build = [IO.Path]::GetFullPath($build)
$buildPrefix = [IO.Path]::GetFullPath((Join-Path $root 'build')).TrimEnd('\') + '\'
if (-not ($build + '\').StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Build directory is outside the system build tree.' }
$vm = Join-Path $build "tests/86box/card-vm"
$roms = Join-Path $build "tests/86box/roms"
$image = [IO.Path]::GetFullPath($ImagePath)
if (-not (Test-Path -LiteralPath $image)) { throw "VHD image was not found: $image" }

$stream = [IO.File]::OpenRead($image)
try {
    $stream.Position = $stream.Length - 512
    $footer = [byte[]]::new(512)
    if ($stream.Read($footer, 0, 512) -ne 512 -or [Text.Encoding]::ASCII.GetString($footer, 0, 8) -ne "conectix") {
        throw "The image does not have a valid VHD footer."
    }
} finally {
    $stream.Dispose()
}
$cylinders = [int]$footer[56] * 256 + $footer[57]
$heads = $footer[58]
$sectors = $footer[59]
if (-not $cylinders -or -not $heads -or -not $sectors) { throw "The VHD geometry is invalid." }

[IO.Directory]::CreateDirectory($vm) | Out-Null
if ($BootNumLock -ne 'Default') {
    # Independent saved schema2 record; each reset must reload this policy.
    $nvr = Join-Path $vm 'nvr'
    [IO.Directory]::CreateDirectory($nvr) | Out-Null
    $cmos = [byte[]]::new(256)
    $cmos[0x0A], $cmos[0x0B], $cmos[0x0D] = 0x26, 2, 0x80
    $cmos[4], $cmos[6], $cmos[7], $cmos[8], $cmos[9], $cmos[0x32] = 0x12, 5, 1, 1, 0x26, 0x20
    $cmos[0x37] = 0xA0
    $flags = 0x12 -bor [int]($BootNumLock -eq 'On')
    $record = [byte[]](66, 56, 2, $flags, 2, 0, 0, 0)
    $record[5] = (256 - ((66 + 56 + 2 + $flags + 2) -band 255)) -band 255
    [Array]::Copy($record, 0, $cmos, 0x38, 8)
    [IO.File]::WriteAllBytes((Join-Path $nvr 'd824.nvr'), $cmos)
}
$imageForConfig = $image.Replace('\', '/')
$unitTesterConfig = if ($ExpectedExitCode -ge 0) { "unittester_enabled = 1`n`n[86Box Unit Tester]`nexit_enabled = 1" } else { "" }
$config = @"
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

[Input devices]
mouse_type = none

[Sound]
sndcard = none

[Network]
net_01_card = none

[Ports (COM & LPT)]

[Storage controllers]
hdc_1 = ide_isa

[Hard disks]
hdd_01_parameters = $sectors, $heads, $cylinders, 0, ide
hdd_01_fn = $imageForConfig
hdd_01_speed = ramdisk
hdd_01_ide_channel = 0:0

[Floppy and CD-ROM drives]
fdd_01_type = none
fdd_02_type = none

[Other peripherals]
postcard_enabled = 1
$unitTesterConfig
"@
[IO.File]::WriteAllText((Join-Path $vm "86box.cfg"), $config, [Text.UTF8Encoding]::new($false))

$exe = (Get-Command 86Box.exe -ErrorAction SilentlyContinue).Source
if (-not $exe) { $exe = Join-Path $env:LOCALAPPDATA "Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe" }
if (-not (Test-Path -LiteralPath $exe)) { throw "86Box was not found." }

if ($ExpectedExitCode -ge 0) {
    $arguments = "-P `"$vm`" -R `"$roms`" -N"
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WindowStyle Hidden -PassThru
    try {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) { throw "DOS memory test timed out." }
        if ($process.ExitCode -ne $ExpectedExitCode) {
            throw "DOS memory test exited 0x$($process.ExitCode.ToString('X2')); expected 0x$($ExpectedExitCode.ToString('X2'))."
        }
        "DOS memory test passed with exit 0x$($process.ExitCode.ToString('X2'))."
    } finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        $process.WaitForExit()
    }
    return
}

Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class BaiosWindowCapture {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr window, IntPtr deviceContext, uint flags);
}
'@

$arguments = "-P `"$vm`" -R `"$roms`" -N"
$process = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru
try {
    for ($attempt = 0; $attempt -lt 80 -and $process.MainWindowHandle -eq 0; $attempt++) {
        Start-Sleep -Milliseconds 250
        $process.Refresh()
    }
    if ($process.MainWindowHandle -eq 0) { throw "86Box did not create a window." }
    Start-Sleep -Seconds $CaptureAfterSeconds

    $rect = [BaiosWindowCapture+RECT]::new()
    if (-not [BaiosWindowCapture]::GetWindowRect($process.MainWindowHandle, [ref]$rect)) { throw "Could not read the 86Box window bounds." }
    $bitmap = [Drawing.Bitmap]::new($rect.R - $rect.L, $rect.B - $rect.T)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $deviceContext = $graphics.GetHdc()
    try {
        if (-not [BaiosWindowCapture]::PrintWindow($process.MainWindowHandle, $deviceContext, 2)) { throw "Could not capture the 86Box window." }
    } finally {
        $graphics.ReleaseHdc($deviceContext)
        $graphics.Dispose()
    }
    $screenshot = Join-Path $build "review/card-boot.png"
    [IO.Directory]::CreateDirectory((Split-Path -Parent $screenshot)) | Out-Null
    $bitmap.Save($screenshot, [Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
    [pscustomobject]@{
        Geometry = "$cylinders/$heads/$sectors"
        Screenshot = $screenshot
    } | Format-List
} finally {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    $process.WaitForExit()
}
