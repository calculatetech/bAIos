[CmdletBinding(SupportsShouldProcess)]
param()
$ErrorActionPreference = 'Stop'
$portRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path (Split-Path -Parent $portRoot) 'shared/tools/build-cleanup.ps1')
$build = Join-Path $portRoot 'build'
Initialize-BuildCleanup $build $PSCmdlet
if (-not (Test-Path -LiteralPath $build)) { return }
$keep = @('baios-mp386.bin','baios-mp386-even.bin','baios-mp386-odd.bin',
          'baios-mp386.lst','configuration.inc','rom-checksums.json',
          'diagnostics','research','review-checkout','baseline','test-results','first-boot',
          'linear-capacity','oem-shadow','oem-cache','cache-state-recovery',
          'cmos-cache','zero-base','post-alignment','setup-alignment','review-correction','final-validation')
foreach ($item in Get-ChildItem -LiteralPath $build -Force | Where-Object Name -NotIn $keep) {
    Remove-Generated $item.FullName
}
$results = Join-Path $build 'test-results'
if (Test-Path -LiteralPath $results) {
    foreach ($item in Get-ChildItem -LiteralPath $results -File -Filter 'boot-*.bin') {
        Remove-Generated $item.FullName
    }
}
