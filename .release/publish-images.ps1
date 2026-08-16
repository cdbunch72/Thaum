#Requires -Version 5.1
# publish-images.ps1
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
<#
.SYNOPSIS
    Build, push, and cosign signed GHCR images for a bare Thaum version.

.PARAMETER Version
    Bare version without a leading v (e.g. 0.7.0rc2).

.PARAMETER CosignKey
    Cosign private key file (default: .release/cosign.key).

.PARAMETER SkipLogin
    Do not run docker/podman login to ghcr.io.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Version,
    [string] $CosignKey,
    [switch] $SkipLogin
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

$needMeta = [string]::IsNullOrEmpty($env:THAUM_RELEASE_VERSION) -or ($env:THAUM_RELEASE_VERSION -ne $Version)
if ($needMeta) {
    $metaJson = & $python.Source (Join-Path $Root '.release\release_meta.py') $Version --format json
    if ($LASTEXITCODE -ne 0) {
        throw 'release_meta.py failed'
    }
    $meta = $metaJson | ConvertFrom-Json
    $env:THAUM_RELEASE_VERSION = [string] $meta.version
    $env:THAUM_RELEASE_TAG = [string] $meta.tag
    $env:THAUM_RELEASE_PRERELEASE = if ($meta.prerelease) { '1' } else { '0' }
    $env:GEMSTONE_UTILS_REF = [string] $meta.gemstone_utils_ref
    $env:THAUM_IMAGE_CHANNEL = [string] $meta.image_channel
}

$pythonVersion = if ($env:PYTHON_VERSION) { $env:PYTHON_VERSION } else { '3.13' }
if (-not $CosignKey) {
    $CosignKey = Join-Path $Root '.release\cosign.key'
}
if (-not (Test-Path -LiteralPath $CosignKey -PathType Leaf)) {
    throw @"
cosign private key not found: $CosignKey
Generate with: cosign generate-key-pair --output-key-prefix $($Root)\.release\cosign
Commit the .pub file; keep the private key off GitHub.
"@
}
if (-not (Get-Command cosign -ErrorAction SilentlyContinue)) {
    throw 'cosign is required on PATH'
}

function Get-ContainerEngine {
    if ($env:CONTAINER_ENGINE) {
        return $env:CONTAINER_ENGINE
    }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($docker) {
        docker info 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return 'docker'
        }
    }
    $podman = Get-Command podman -ErrorAction SilentlyContinue
    if ($podman) {
        return 'podman'
    }
    throw 'docker or podman is required'
}

$engine = Get-ContainerEngine
$thaumImage = $env:THAUM_IMAGE
if (-not $thaumImage) {
    $nwo = (gh repo view --json nameWithOwner --jq .nameWithOwner).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or -not $nwo) {
        throw 'gh repo view failed; set THAUM_IMAGE or authenticate gh'
    }
    $thaumImage = "ghcr.io/$($nwo.ToLowerInvariant())"
}
$imageExternal = "${thaumImage}-external-db"

if (-not $SkipLogin) {
    $user = gh api user --jq .login
    if ($LASTEXITCODE -ne 0) {
        throw 'gh api user failed'
    }
    gh auth token | & $engine login ghcr.io -u $user --password-stdin
    if ($LASTEXITCODE -ne 0) {
        throw "$engine login ghcr.io failed"
    }
}

function Get-ReleaseTags([string] $Image) {
    $tags = @(
        "${Image}:$($env:THAUM_RELEASE_VERSION)",
        "${Image}:devel",
        "${Image}:edge"
    )
    if ($env:THAUM_RELEASE_PRERELEASE -ne '1') {
        $tags += "${Image}:latest"
    }
    return $tags
}

function Get-ImageDigest([string] $Ref) {
    $digest = & $engine image inspect --format '{{index .RepoDigests 0}}' $Ref
    if ($LASTEXITCODE -ne 0 -or -not $digest -or $digest -eq '<no value>') {
        throw "no RepoDigest for ${Ref}; push succeeded but digest is missing"
    }
    return [string] $digest.Trim()
}

function Publish-Variant([string] $Image, [string] $Bundled) {
    $versionRef = "${Image}:$($env:THAUM_RELEASE_VERSION)"
    $buildArgs = @(
        'build',
        '--build-arg', "PYTHON_VERSION=$pythonVersion",
        '--build-arg', "GEMSTONE_UTILS_REF=$($env:GEMSTONE_UTILS_REF)",
        '--build-arg', "THAUM_BUNDLED_POSTGRES=$Bundled",
        '--build-arg', "THAUM_IMAGE_VERSION=$($env:THAUM_RELEASE_VERSION)",
        '--build-arg', "THAUM_IMAGE_CHANNEL=$($env:THAUM_IMAGE_CHANNEL)",
        '-t', $versionRef,
        '-f', (Join-Path $Root 'Dockerfile'),
        $Root
    )
    & $engine @buildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$engine build failed for $Image"
    }

    foreach ($tag in (Get-ReleaseTags $Image)) {
        if ($tag -eq $versionRef) { continue }
        & $engine tag $versionRef $tag
        if ($LASTEXITCODE -ne 0) {
            throw "$engine tag failed: $tag"
        }
    }
    foreach ($tag in (Get-ReleaseTags $Image)) {
        & $engine push $tag
        if ($LASTEXITCODE -ne 0) {
            throw "$engine push failed: $tag"
        }
    }

    $digest = Get-ImageDigest $versionRef
    & cosign sign --yes --key $CosignKey $digest
    if ($LASTEXITCODE -ne 0) {
        throw "cosign sign failed for $digest"
    }
}

Publish-Variant -Image $thaumImage -Bundled '1'
Publish-Variant -Image $imageExternal -Bundled '0'
