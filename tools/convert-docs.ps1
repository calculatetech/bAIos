$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
& (Join-Path $repository 'shared/tools/convert-docs.ps1') -SourceDirectory (Join-Path $repository 'reference') -OutputDirectory (Join-Path $repository 'reference/searchable') -TemporaryDirectory (Join-Path $repository '.agent/test-results/docs-ocr')
