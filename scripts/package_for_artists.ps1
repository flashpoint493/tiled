param(
    [string]$PackageName = "tiled_tools_artist_pack",
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputPath = if ([System.IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $Root $OutputDir }
$StageRoot = Join-Path $Root ".package_stage"
$StageDir = Join-Path $StageRoot $PackageName
$ZipPath = Join-Path $OutputPath "$PackageName.zip"

$ExcludedDirs = @(
    ".git",
    ".venv",
    ".web_runtime",
    ".tiled_tools_runtime",
    ".package_stage",
    "__pycache__",
    "build",
    "dist",
    "output",
    "tiled_tools.egg-info"
)

$ExcludedFilePatterns = @(
    "*.pyc",
    "*.pyo",
    "*.zip"
)

function Test-IsExcludedDir([System.IO.DirectoryInfo]$Dir) {
    return $ExcludedDirs -contains $Dir.Name
}

function Test-IsExcludedFile([System.IO.FileInfo]$File) {
    foreach ($pattern in $ExcludedFilePatterns) {
        if ($File.Name -like $pattern) {
            return $true
        }
    }
    return $false
}

function Get-RelativePath([string]$BasePath, [string]$FullPath) {
    $BaseFullPath = [System.IO.Path]::GetFullPath($BasePath).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $TargetFullPath = [System.IO.Path]::GetFullPath($FullPath)
    $BaseUri = New-Object System.Uri($BaseFullPath + [System.IO.Path]::DirectorySeparatorChar)
    $TargetUri = New-Object System.Uri($TargetFullPath)
    $RelativeUri = $BaseUri.MakeRelativeUri($TargetUri)
    return [System.Uri]::UnescapeDataString($RelativeUri.ToString()).Replace('/', [System.IO.Path]::DirectorySeparatorChar)
}

if (Test-Path $StageRoot) {
    Remove-Item $StageRoot -Recurse -Force
}
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

$RootItem = Get-Item $Root
$Stack = New-Object System.Collections.Stack
$Stack.Push($RootItem)

while ($Stack.Count -gt 0) {
    $Current = [System.IO.DirectoryInfo]$Stack.Pop()
    foreach ($Item in Get-ChildItem -LiteralPath $Current.FullName -Force) {
        if ($Item.PSIsContainer) {
            if (Test-IsExcludedDir $Item) {
                continue
            }
            $RelDir = Get-RelativePath $Root $Item.FullName
            New-Item -ItemType Directory -Force -Path (Join-Path $StageDir $RelDir) | Out-Null
            $Stack.Push($Item)
            continue
        }

        if (Test-IsExcludedFile $Item) {
            continue
        }

        $RelFile = Get-RelativePath $Root $Item.FullName
        $DestFile = Join-Path $StageDir $RelFile
        $DestParent = Split-Path -Parent $DestFile
        New-Item -ItemType Directory -Force -Path $DestParent | Out-Null
        Copy-Item -LiteralPath $Item.FullName -Destination $DestFile -Force
    }
}

Compress-Archive -Path $StageDir -DestinationPath $ZipPath -CompressionLevel Optimal -Force
Remove-Item $StageRoot -Recurse -Force

$Zip = Get-Item $ZipPath
Write-Host "Created package:" $Zip.FullName
Write-Host "Size MB:" ([math]::Round($Zip.Length / 1MB, 2))
Write-Host "Artist usage: unzip, then double-click start_tiled_tools_web.bat"