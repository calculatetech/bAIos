# Preview with -WhatIf. Each maintained port owns its retention policy.
[CmdletBinding(SupportsShouldProcess)]
param([string]$Port)
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
. (Join-Path $repository 'shared/tools/build-cleanup.ps1')
Initialize-BuildCleanup (Join-Path $repository 'build') $PSCmdlet
$ports = @(Get-ChildItem -LiteralPath $repository -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'tools/clean-build.ps1') })
if ($Port) {
    $ports = @($ports | Where-Object Name -EQ $Port)
    if ($ports.Count -ne 1) { throw "Unknown maintained port: $Port" }
}
foreach ($item in $ports) {
    Assert-OwnedPath $item.FullName $repository | Out-Null
    & (Join-Path $item.FullName 'tools/clean-build.ps1') -WhatIf:$WhatIfPreference
}
if (-not $Port -and (Test-Path -LiteralPath (Join-Path $repository 'build'))) {
    Initialize-BuildCleanup (Join-Path $repository 'build') $PSCmdlet
    foreach ($item in Get-ChildItem -LiteralPath (Join-Path $repository 'build') -Force) {
        Remove-Generated $item.FullName
    }
}
