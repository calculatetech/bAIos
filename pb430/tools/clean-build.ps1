[CmdletBinding(SupportsShouldProcess)]
param()
$ErrorActionPreference = 'Stop'
$portRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path (Split-Path -Parent $portRoot) 'shared/tools/build-cleanup.ps1')
$build = Join-Path $portRoot 'build'
Initialize-BuildCleanup $build $PSCmdlet
if (-not (Test-Path -LiteralPath $build)) { return }
$legacyTools = Join-Path $build 'deps'
if ((Test-Path -LiteralPath $legacyTools) -and @(Get-ChildItem -LiteralPath $legacyTools -Recurse -File -Force).Count) {
    throw 'Move installed tools from build/deps to root tools/deps before cleanup.'
}
$keep = @('baios-pb430.bin','baios-pb430-system.bin','baios-pb430-vga50.bin','baios-pb430-vga60.bin','baios-pb430.lst','configuration.inc','rom-checksums.json','diagnostics','tests','research','review','releases','LATEST.txt','LATEST.json','build-info.json')
$keep += @(Get-LatestCandidateFiles $build)
foreach ($item in Get-ChildItem -LiteralPath $build -Force | Where-Object Name -NotIn $keep) {
    Remove-Generated $item.FullName
}

$results = Join-Path $build 'tests/results'
if (Test-Path -LiteralPath $results) {
    foreach ($case in Get-ChildItem -LiteralPath $results -Directory) {
        if (Test-Path -LiteralPath (Join-Path $case.FullName '.retain-diagnosis')) { continue }
        foreach ($item in Get-ChildItem -LiteralPath $case.FullName -Force) {
            if ($item.Name -in @('vm','roms','fixture','fixture-alias','boot.bin','observer.bin','vga-entry.bin','vga-entry.inc','test-configuration.inc') -or
                $item.Name -like 'cd-*.iso') { Remove-Generated $item.FullName }
        }
        $image = Join-Path $case.FullName 'image'
        $alias = Join-Path $image 'fixture-alias'
        if (Test-Path -LiteralPath $alias) { Remove-Generated $alias }
    }
}
