param(
    [string]$EmulatorPath
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$buildRoot = [IO.Path]::GetFullPath((Join-Path $root "build"))
$left = Join-Path $buildRoot "repro-a"
$right = Join-Path $buildRoot "repro-b"
$artifacts = @(
    "baios-presario800-system.rom",
    "baios-presario800.bin",
    "boot-test.bin",
    "fault-test.bin",
    "keyboard-test.bin",
    "diagnostics/rtc-test.bin",
    "diagnostics/RTCCHECK.COM",
    "diagnostics/SPRTC.COM"
)

foreach ($directory in @($left, $right)) {
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    foreach ($name in $artifacts) {
        $path = Join-Path $directory $name
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
    }
}

& (Join-Path $PSScriptRoot "build.ps1") -OutputDirectory "build/repro-a" | Out-Null
& (Join-Path $PSScriptRoot "build.ps1") -OutputDirectory "build/repro-b" | Out-Null
foreach ($name in $artifacts) {
    $leftHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $left $name)).Hash
    $rightHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $right $name)).Hash
    if ($leftHash -ne $rightHash) { throw "Reproducibility failed for $name." }
}

& (Join-Path $PSScriptRoot "build.ps1") | Out-Null
& (Join-Path $PSScriptRoot "verify-rom.ps1") -SelfTest
& (Join-Path $PSScriptRoot "verify-docs.ps1")
foreach ($check in @('test-rtc.py', 'test-legacy-disk.py', 'test-setup.py', 'test-ide-options.py', 'test-ports.py',
                    'test-memory-banks.py', 'test-external-cache.py', 'test-chipset.py')) {
    & python -B (Join-Path $PSScriptRoot $check)
    if ($LASTEXITCODE) { throw "$check failed with exit $LASTEXITCODE." }
}

$outsideId = [guid]::NewGuid().ToString("N")
$outsideBuilds = @(
    "build-other-$outsideId/organization-check",
    "../organization-outside-$outsideId",
    (Join-Path $root "absolute-outside-$outsideId")
)
foreach ($outsideBuild in $outsideBuilds) {
    $rejected = $false
    try {
        & (Join-Path $PSScriptRoot "build.ps1") -OutputDirectory $outsideBuild | Out-Null
    } catch {
        if ($_.Exception.Message -notlike "OutputDirectory must resolve inside *") { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "An outside build directory was accepted: $outsideBuild" }
    $outsidePath = if ([IO.Path]::IsPathRooted($outsideBuild)) { $outsideBuild } else { Join-Path $root $outsideBuild }
    if (Test-Path -LiteralPath ([IO.Path]::GetFullPath($outsidePath))) { throw "A rejected build directory was created: $outsideBuild" }
}

$runner = Join-Path $PSScriptRoot "run-86box.ps1"
$originalPath = $env:Path
$originalLocalAppData = $env:LOCALAPPDATA
$originalNasmOverride = Get-Item Env:BAIOS_NASM -ErrorAction SilentlyContinue
$wingetEmulator = Join-Path $originalLocalAppData "Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe"
$knownEmulator = $EmulatorPath
if (-not $knownEmulator) {
    $command = Get-Command 86Box.exe -ErrorAction SilentlyContinue
    if ($command) { $knownEmulator = $command.Source }
}
if (-not $knownEmulator -and (Test-Path -LiteralPath $wingetEmulator)) { $knownEmulator = $wingetEmulator }
if (-not $knownEmulator -or -not (Test-Path -LiteralPath $knownEmulator)) { throw "86Box was not found for selector validation." }
$knownEmulator = (Resolve-Path -LiteralPath $knownEmulator).Path
$nasm = Get-Command nasm -ErrorAction SilentlyContinue
$nasmPath = if ($nasm) { $nasm.Source } else { Join-Path $originalLocalAppData "bin/NASM/nasm.exe" }
if (-not (Test-Path -LiteralPath $nasmPath)) { throw "NASM was not found for selector validation." }
$emulatorDirectory = Split-Path -Parent $knownEmulator
$selectorLocalAppData = Join-Path $buildRoot ("selector-" + [guid]::NewGuid().ToString("N"))
$selectorPackageParent = Join-Path $selectorLocalAppData "Microsoft/WinGet/Packages"
$selectorPackage = Join-Path $selectorPackageParent "86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe"
$pathEmulatorDirectory = Join-Path $selectorLocalAppData "path-emulator"
$nasmFixtureDirectory = Join-Path $selectorLocalAppData "nasm"
$emulatorFixtureDirectory = Join-Path $selectorLocalAppData "emulator"
$spacedRepository = Join-Path $selectorLocalAppData "repository with spaces"
$missingLocalAppData = Join-Path $selectorLocalAppData "missing-localappdata"
$missingMessage = "86Box was not found. Put 86Box.exe on PATH or pass -EmulatorPath <path>."
$selectorRoot = [IO.Path]::GetFullPath($selectorLocalAppData)
$buildPrefix = $buildRoot.TrimEnd('\') + '\'
if (-not $selectorRoot.StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Selector fixture escaped the system build directory." }
function Test-EmulatorSelector([string]$ExpectedPath, [string]$ExplicitPath) {
    $arguments = @{ NoDisk = $true; TimeoutSeconds = 60 }
    if ($ExplicitPath) { $arguments.EmulatorPath = $ExplicitPath }
    $output = & $runner @arguments
    $output | Write-Output
    if ($output -notcontains "86Box selected: $ExpectedPath") { throw "The wrong 86Box selector won." }
}
try {
    [IO.Directory]::CreateDirectory($selectorPackageParent) | Out-Null
    [IO.Directory]::CreateDirectory($nasmFixtureDirectory) | Out-Null
    $nasmLauncher = "@echo off`r`n`"%BAIOS_NASM%`" %*`r`n"
    [IO.File]::WriteAllText((Join-Path $nasmFixtureDirectory "nasm.cmd"), $nasmLauncher, [Text.Encoding]::ASCII)
    $fixtureTarget = $emulatorDirectory
    if ([IO.Path]::GetFileName($knownEmulator) -ne "86Box.exe") {
        [IO.Directory]::CreateDirectory($emulatorFixtureDirectory) | Out-Null
        Copy-Item -Path (Join-Path $emulatorDirectory "*") -Destination $emulatorFixtureDirectory -Recurse
        Copy-Item -LiteralPath $knownEmulator -Destination (Join-Path $emulatorFixtureDirectory "86Box.exe") -Force
        $fixtureTarget = $emulatorFixtureDirectory
    }
    New-Item -ItemType Junction -Path $selectorPackage -Target $fixtureTarget | Out-Null
    New-Item -ItemType Junction -Path $pathEmulatorDirectory -Target $fixtureTarget | Out-Null
    New-Item -ItemType Junction -Path $spacedRepository -Target (Split-Path -Parent $root) | Out-Null

    $spacedPort = Join-Path $spacedRepository (Split-Path -Leaf $root)
    $spacedOutput = & (Join-Path $spacedPort "tools/run-86box.ps1") -EmulatorPath $knownEmulator -NoDisk -TimeoutSeconds 60
    $spacedOutput | Write-Output
    if ($spacedOutput -notcontains "86Box selected: $knownEmulator") { throw "86Box failed through a repository path that contains spaces." }

    $env:BAIOS_NASM = $nasmPath
    $env:Path = "$nasmFixtureDirectory;$pathEmulatorDirectory"
    $env:LOCALAPPDATA = $selectorLocalAppData
    Test-EmulatorSelector $knownEmulator $knownEmulator

    Test-EmulatorSelector (Join-Path $pathEmulatorDirectory "86Box.exe") ""

    $env:Path = $nasmFixtureDirectory
    Test-EmulatorSelector (Join-Path $selectorPackage "86Box.exe") ""

    $env:LOCALAPPDATA = $missingLocalAppData
    $missingSelectorRejected = $false
    try {
        & $runner -NoDisk -TimeoutSeconds 1
    } catch {
        if ($_.Exception.Message -ne $missingMessage) { throw }
        $missingSelectorRejected = $true
    }
    if (-not $missingSelectorRejected) { throw "Missing 86Box selectors were accepted." }
} finally {
    $env:Path = $originalPath
    $env:LOCALAPPDATA = $originalLocalAppData
    if ($originalNasmOverride) { $env:BAIOS_NASM = $originalNasmOverride.Value } else { Remove-Item Env:BAIOS_NASM -ErrorAction SilentlyContinue }
    foreach ($junction in @($selectorPackage, $pathEmulatorDirectory, $spacedRepository)) {
        if (Test-Path -LiteralPath $junction) {
            $attributes = [IO.File]::GetAttributes($junction)
            if (-not ($attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Selector fixture is not a reparse point." }
            [IO.Directory]::Delete($junction)
        }
    }
    if (Test-Path -LiteralPath $selectorLocalAppData) { [IO.Directory]::Delete($selectorLocalAppData, $true) }
}

& (Join-Path $PSScriptRoot "run-86box.ps1") -EmulatorPath $EmulatorPath -BadBoot -TimeoutSeconds 60
& (Join-Path $PSScriptRoot "run-86box.ps1") -EmulatorPath $EmulatorPath -IdentifyTimeout -TimeoutSeconds 60
& (Join-Path $PSScriptRoot "run-86box.ps1") -EmulatorPath $EmulatorPath -IdentifyPostBusy -TimeoutSeconds 60
& (Join-Path $PSScriptRoot "run-86box.ps1") -EmulatorPath $EmulatorPath -IdentifyPostError -TimeoutSeconds 60
& (Join-Path $PSScriptRoot "run-86box.ps1") -EmulatorPath $EmulatorPath -BootPostBusy -TimeoutSeconds 60
& (Join-Path $PSScriptRoot "run-86box.ps1") -EmulatorPath $EmulatorPath -BootPostError -TimeoutSeconds 60
& (Join-Path $PSScriptRoot "run-86box.ps1") -EmulatorPath $EmulatorPath -FaultTest -TimeoutSeconds 120
& (Join-Path $PSScriptRoot "run-86box.ps1") -EmulatorPath $EmulatorPath -KeyboardTest -TimeoutSeconds 120
& (Join-Path $PSScriptRoot "run-86box.ps1") -EmulatorPath $EmulatorPath -RtcTest -TimeoutSeconds 60
& (Join-Path $PSScriptRoot "run-86box.ps1") -EmulatorPath $EmulatorPath -TimeoutSeconds 60

"Complete validation passed, including reproducible builds."
