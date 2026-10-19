param([string]$OutputDirectory = 'build')
$ErrorActionPreference = 'Stop'
$portRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $portRoot
& python -B (Join-Path $repoRoot 'tools/build-rom.py') $portRoot --output $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed.' }
