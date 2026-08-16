#Requires -Version 5.1
# package-thaum-utils.ps1
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
<#
.SYNOPSIS
    Package thaum-utils into dist/thaum-utils-<tag>.zip and SHA256SUMS.txt.

.PARAMETER Tag
    Git/GitHub tag including the v prefix (e.g. v0.7.0rc2).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Tag
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Out = Join-Path $Root 'dist'
$Staging = Join-Path $Out 'thaum-utils'
$ZipName = "thaum-utils-${Tag}.zip"
$ZipPath = Join-Path $Out $ZipName
$SumsPath = Join-Path $Out 'SHA256SUMS.txt'

if (Test-Path $Staging) {
    Remove-Item -Recurse -Force $Staging
}
New-Item -ItemType Directory -Force -Path $Staging | Out-Null
Copy-Item -Recurse (Join-Path $Root 'quickstart') $Staging
Copy-Item -Recurse (Join-Path $Root 'docs') $Staging
Copy-Item -Recurse (Join-Path $Root 'scripts') $Staging
Copy-Item (Join-Path $Root 'sample.thaum.toml') $Staging
Copy-Item (Join-Path $Root 'incident_prompt_card.sample.j2') $Staging

if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}
if (Test-Path $SumsPath) {
    Remove-Item -Force $SumsPath
}

Push-Location $Out
try {
    $zipCmd = Get-Command zip -ErrorAction SilentlyContinue
    if ($zipCmd) {
        & zip -r $ZipName thaum-utils
        if ($LASTEXITCODE -ne 0) {
            throw "zip failed with exit code $LASTEXITCODE"
        }
    } else {
        Compress-Archive -Path 'thaum-utils' -DestinationPath $ZipName
    }
    $hash = (Get-FileHash -Algorithm SHA256 -Path $ZipName).Hash.ToLowerInvariant()
    # GNU sha256sum text mode: two spaces between hash and filename
    Set-Content -Path $SumsPath -Value "$hash  $ZipName" -Encoding ascii
} finally {
    Pop-Location
}

Write-Output $ZipPath
Write-Output $SumsPath
