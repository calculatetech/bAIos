[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory, ParameterSetName='Workspace')][string]$Path,
    [Parameter(Mandatory, ParameterSetName='Evidence')][string]$Port
)
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
. (Join-Path $repository 'shared/tools/build-cleanup.ps1')
if ($PSCmdlet.ParameterSetName -eq 'Evidence') {
    if ($Port -ne [IO.Path]::GetFileName($Port) -or $Port -in @('.', '..')) { throw 'Select one port name.' }
    $portRoot = Join-Path $repository $Port
    if (-not (Test-Path -LiteralPath (Join-Path $portRoot 'src/bios.asm'))) { throw 'Unknown port.' }
    Initialize-BuildCleanup (Join-Path $portRoot 'build') $PSCmdlet
    foreach ($name in @('logs','results')) {
        Remove-Generated (Join-Path $portRoot ('build/review/shared-update/' + $name))
    }
    return
}
$owned = Join-Path $repository '.agent/test-results/port-update'
Initialize-BuildCleanup $owned $PSCmdlet
$target = Assert-OwnedPath $Path $owned
if ((Split-Path -Leaf $target) -ne 'workspace') {
    throw 'Only an owned port-update workspace can be removed.'
}
Remove-Generated $target
