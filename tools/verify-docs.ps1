$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
& (Join-Path $repository 'shared/tools/verify-docs.ps1') -SourceDirectory (Join-Path $repository 'reference') -OutputDirectory (Join-Path $repository 'reference/searchable') -ExpectedCount 18 -SpotTerms @('VL82C481', 'FDC37C661', 'memory', 'Cirrus')
