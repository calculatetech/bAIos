param()
$ErrorActionPreference = 'Stop'
& python -B (Join-Path $PSScriptRoot 'build.py')
if ($LASTEXITCODE -ne 0) { throw 'PB430 firmware build failed.' }
