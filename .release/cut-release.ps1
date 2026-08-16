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
    Package, sign, tag, and create the GitHub Release without building/pushing GHCR images.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Version,
    [switch] $SkipImages
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

& (Join-Path $PSScriptRoot 'package-thaum-utils.ps1') -Tag $tag
$zip = Join-Path $Root "dist\thaum-utils-${tag}.zip"
$sums = Join-Path $Root 'dist\SHA256SUMS.txt'
& (Join-Path $PSScriptRoot 'sign-artifacts.ps1') $zip $sums

$gitKey = if ($env:GIT_COMMIT_SIGNING_KEY) { $env:GIT_COMMIT_SIGNING_KEY } else { 'git-commit@gemstone.software' }
git tag -s -u $gitKey -m "Thaum ${tag}" $tag
if ($LASTEXITCODE -ne 0) {
    throw 'git tag -s failed'
}
git push origin "refs/tags/${tag}"
if ($LASTEXITCODE -ne 0) {
    throw 'git push of signed tag failed'
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
$ghArgs += @($zip, "${zip}.asc", $sums, "${sums}.asc")
& gh @ghArgs
if ($LASTEXITCODE -ne 0) {
    throw 'gh release create failed'
}

if (-not $SkipImages) {
    & (Join-Path $PSScriptRoot 'publish-images.ps1') -Version $Version
}
