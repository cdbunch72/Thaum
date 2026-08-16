#Requires -Version 5.1
# cut-release.ps1
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
<#
.SYNOPSIS
    Cut a signed Thaum GitHub Release from a bare version.

.PARAMETER Version
    Bare version without a leading v (e.g. 0.7.0rc2).

.PARAMETER SkipImages
    Do not build or push GHCR images.

.PARAMETER CodeKey
    GPG user id for SHA256SUMS.txt and the zip (default: code@gemstone.software).

.PARAMETER GitCommitKey
    GPG user id for git tag -s (default: git-commit@gemstone.software).

.PARAMETER CosignKey
    Cosign private key path forwarded to publish-images.ps1.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Version,
    [switch] $SkipImages,
    [string] $CodeKey = 'code@gemstone.software',
    [string] $GitCommitKey = 'git-commit@gemstone.software',
    [string] $CosignKey
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $python) {
    throw 'python or python3 is required'
}

$notesPath = Join-Path $Root 'dist\NOTES.md'
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'dist') | Out-Null
$metaJson = & $python.Source (Join-Path $Root '.release\release_meta.py') $Version --format json --notes-out $notesPath
if ($LASTEXITCODE -ne 0) {
    throw 'release_meta.py failed'
}
$meta = $metaJson | ConvertFrom-Json
$tag = [string] $meta.tag

$status = git status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw 'git status failed'
}
if ($status) {
    git status --porcelain
    throw 'working tree is dirty'
}

git rev-parse -q --verify "refs/tags/${tag}" 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    throw "tag ${tag} already exists"
}

$sums = Join-Path $Root 'SHA256SUMS.txt'
$sumsAsc = Join-Path $Root 'SHA256SUMS.txt.asc'
$hashedCommit = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $hashedCommit) {
    throw 'git rev-parse HEAD failed'
}
$sumsDate = [datetime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss'Z'")
$sumsMeta = @(
    '--version', [string] $meta.version,
    '--date', $sumsDate,
    '--hashed-commit', $hashedCommit
)

& $python.Source (Join-Path $Root '.release\generate_checksums.py') @sumsMeta --output $sums
if ($LASTEXITCODE -ne 0) {
    throw 'generate_checksums.py failed'
}

$sumsChanged = $true
git cat-file -e 'HEAD:SHA256SUMS.txt' 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    git diff --quiet -- SHA256SUMS.txt
    if ($LASTEXITCODE -eq 0) {
        $sumsChanged = $false
    }
}
if ($sumsChanged -or -not (Test-Path -LiteralPath $sumsAsc -PathType Leaf)) {
    & (Join-Path $PSScriptRoot 'sign-artifacts.ps1') -Key $CodeKey $sums
}

git add -- SHA256SUMS.txt SHA256SUMS.txt.asc
if ($LASTEXITCODE -ne 0) {
    throw 'git add SHA256SUMS failed'
}
git diff --cached --quiet -- SHA256SUMS.txt SHA256SUMS.txt.asc
if ($LASTEXITCODE -eq 0) {
    Write-Output 'SHA256SUMS.txt already committed'
} else {
    $msg = @"
Record SHA256SUMS signed by ${CodeKey} for ${tag}.

"@
    git commit -m $msg
    if ($LASTEXITCODE -ne 0) {
        throw 'git commit of SHA256SUMS failed'
    }
}

& (Join-Path $PSScriptRoot 'package-thaum-utils.ps1') -Tag $tag
$zip = Join-Path $Root "dist\thaum-utils-${tag}.zip"
$zipSums = Join-Path $Root 'dist\SHA256SUMS.zip'
& $python.Source (Join-Path $Root '.release\generate_checksums.py') @sumsMeta --binary --output $zipSums $zip
if ($LASTEXITCODE -ne 0) {
    throw 'generate_checksums.py --binary failed'
}
& (Join-Path $PSScriptRoot 'sign-artifacts.ps1') -Key $CodeKey $zip $zipSums

git tag -s -u $GitCommitKey -m "Thaum ${tag}" $tag
if ($LASTEXITCODE -ne 0) {
    throw 'git tag -s failed'
}
git push origin HEAD "refs/tags/${tag}"
if ($LASTEXITCODE -ne 0) {
    throw 'git push of checksum commit and signed tag failed'
}

$ghArgs = @(
    'release', 'create', $tag,
    '--verify-tag',
    '--title', $tag,
    '--notes-file', $notesPath
)
if ($meta.prerelease) {
    $ghArgs += '--prerelease'
}
$ghArgs += @($zip, "${zip}.asc", $zipSums, "${zipSums}.asc", $sums, "${sums}.asc")
& gh @ghArgs
if ($LASTEXITCODE -ne 0) {
    throw 'gh release create failed'
}

if (-not $SkipImages) {
    $publish = Join-Path $PSScriptRoot 'publish-images.ps1'
    if ($CosignKey) {
        & $publish -Version $Version -CosignKey $CosignKey
    } else {
        & $publish -Version $Version
    }
}
