param([string]$Image)
$ErrorActionPreference = 'Stop'
$portRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $portRoot
$verificationArguments = @('-B', (Join-Path $repoRoot 'tools/verify-rom.py'), $portRoot)
if ($Image) { $verificationArguments += @('--image', $Image) }
& python @verificationArguments
if ($LASTEXITCODE -ne 0) { throw 'ROM verification failed.' }
