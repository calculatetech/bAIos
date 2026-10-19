$ErrorActionPreference = 'Stop'
$portRoot = Split-Path -Parent $PSScriptRoot
$repository = Split-Path -Parent $portRoot
& (Join-Path $repository 'tools/verify-docs.ps1')
& (Join-Path $repository 'shared/tools/verify-docs.ps1') -SourceDirectory (Join-Path $portRoot 'docs') -OutputDirectory (Join-Path $portRoot 'docs/searchable') -ExpectedCount 1
