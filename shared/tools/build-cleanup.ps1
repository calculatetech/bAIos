# Port commands own retention policy; this file owns deletion safety.
function Assert-OwnedPath([string]$path, [string]$owner) {
    $root = [IO.Path]::GetFullPath($owner).TrimEnd('\', '/')
    $target = [IO.Path]::GetFullPath($path).TrimEnd('\', '/')
    if ([IO.Path]::GetFileName($target) -eq '.git') { throw "Repository metadata is not generated output: $target" }
    if (-not $target.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing a target outside build: $target"
    }
    $ancestor = $target
    while ($ancestor) {
        if (Test-Path -LiteralPath $ancestor) {
            if ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Reparse target or ancestor: $ancestor"
            }
        }
        $parent = Split-Path -Parent $ancestor
        if ($parent -eq $ancestor) { break }
        $ancestor = $parent
    }
    if (Test-Path -LiteralPath $target -PathType Container) {
        $pending = [Collections.Generic.Stack[string]]::new()
        $pending.Push($target)
        while ($pending.Count) {
            foreach ($item in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
                if ($item.Name -eq '.git') { throw "Repository inside generated output; relocate unique work first: $($item.FullName)" }
                if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse child: $($item.FullName)" }
                if ($item.PSIsContainer) { $pending.Push($item.FullName) }
            }
        }
    }
    return $target
}

function Get-LatestCandidateFiles([string]$build) {
    $manifest = Join-Path $build 'LATEST.json'
    if (-not (Test-Path -LiteralPath $manifest)) { return @() }
    $data = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    foreach ($file in (@($data.files) + @($data.completed.files))) {
        if ($null -eq $file) { continue }
        if ($file.name -ne [IO.Path]::GetFileName($file.name) -or $file.name -match '[/\\]' -or $file.name -in @('.', '..')) {
            throw 'Invalid filename in LATEST.json'
        }
        $file.name
    }
}

function Initialize-BuildCleanup([string]$build, $caller) {
    if (Get-Process -Name 86Box -ErrorAction SilentlyContinue) {
        throw 'An emulator is running. Stop it before cleaning build output.'
    }
    $script:BuildCleanupRoot = [IO.Path]::GetFullPath($build)
    $script:BuildCleanupCmdlet = $caller
    # Check the build root and its ancestors before enumerating its contents.
    Assert-OwnedPath (Join-Path $script:BuildCleanupRoot '__safety_check__') $script:BuildCleanupRoot | Out-Null
}

function Remove-Generated([string]$path) {
    $target = Assert-OwnedPath $path $script:BuildCleanupRoot
    if (-not (Test-Path -LiteralPath $target)) { return }
    if ($script:BuildCleanupCmdlet.ShouldProcess($target, 'Purge obsolete generated output')) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
