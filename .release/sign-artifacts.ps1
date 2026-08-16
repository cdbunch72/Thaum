#Requires -Version 5.1
# sign-artifacts.ps1
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
<#
.SYNOPSIS
    Create ASCII-armored detached GPG signatures.

.PARAMETER Key
    GPG user id (default: code@gemstone.software). Do not use git-commit@ for artifacts.

.PARAMETER Path
    Files to sign. Each input FILE produces FILE.asc.
#>
[CmdletBinding()]
param(
    [string] $Key = 'code@gemstone.software',
    [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
    [string[]] $Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

if (-not $Path -or $Path.Count -lt 1) {
    throw 'usage: sign-artifacts.ps1 [-Key USER] <file> [file...]'
}

foreach ($f in $Path) {
    if (-not (Test-Path -LiteralPath $f -PathType Leaf)) {
        throw "not a file: $f"
    }
    & gpg --yes --local-user $Key --detach-sign --armor -- $f
    if ($LASTEXITCODE -ne 0) {
        throw "gpg failed signing $f (exit $LASTEXITCODE)"
    }
}
