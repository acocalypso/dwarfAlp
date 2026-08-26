[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Archive,
    [Parameter(Mandatory = $true)]
    [string] $Destination
)

$ErrorActionPreference = 'Stop'
$archivePath = (Resolve-Path -LiteralPath $Archive).Path
$destinationPath = [IO.Path]::GetFullPath($Destination)

if (Test-Path -LiteralPath $destinationPath) {
    if (Get-ChildItem -LiteralPath $destinationPath -Force | Select-Object -First 1) {
        throw "Destination must be empty: $destinationPath"
    }
} else {
    New-Item -ItemType Directory -Path $destinationPath | Out-Null
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    $destinationRoot = $destinationPath + [IO.Path]::DirectorySeparatorChar
    foreach ($entry in $zip.Entries) {
        if ([string]::IsNullOrEmpty($entry.Name)) { continue }
        $target = [IO.Path]::GetFullPath((Join-Path $destinationPath $entry.FullName))
        if (-not $target.StartsWith($destinationRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe ZIP member path: $($entry.FullName)"
        }
        $parent = [IO.Path]::GetDirectoryName($target)
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
    }
} finally {
    $zip.Dispose()
}
