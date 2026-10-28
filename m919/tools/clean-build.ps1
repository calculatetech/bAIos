# Keep the current ROM and observations. Completed candidate builds are disposable.
[CmdletBinding(SupportsShouldProcess)]
param()
$ErrorActionPreference = 'Stop'
$portRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path (Split-Path -Parent $portRoot) 'shared/tools/build-cleanup.ps1')
$build = Join-Path $portRoot 'build'
Initialize-BuildCleanup $build $PSCmdlet
if (-not (Test-Path -LiteralPath $build)) { return }
$keep = @('baios-m919.bin','baios-m919.lst','configuration.inc','rom-checksums.json','diagnostics','tests','research','review','releases','LATEST.txt','LATEST.json','build-info.json')
$keep += @(Get-LatestCandidateFiles $build)
foreach ($item in Get-ChildItem -LiteralPath $build -Force | Where-Object Name -NotIn $keep) {
    Remove-Generated $item.FullName
}

$post = Join-Path $build 'tests/post'
if (Test-Path -LiteralPath $post) {
    foreach ($folder in Get-ChildItem -LiteralPath $post -Directory -Recurse) {
        if ($folder.Name -eq 'vm') { Remove-Generated $folder.FullName }
    }
    foreach ($file in Get-ChildItem -LiteralPath $post -File -Recurse | Where-Object Extension -In @('.img','.vhd','.86f','.iso')) {
        Remove-Generated $file.FullName
    }
}
