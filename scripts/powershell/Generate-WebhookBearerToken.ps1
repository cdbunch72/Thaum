#Requires -Version 5.1
# Generate-WebhookBearerToken.ps1
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
<#
.SYNOPSIS
    Generate canonical webhook bearer JSON for Thaum alert status webhooks.

.DESCRIPTION
    Produces canonical compact JSON with keys exp/iat/key/warn matching the Python
    generator semantics, and optionally prints Authorization: Bearer <b64url(canonical-json)>.

.PARAMETER WarnDays
    Days before exp to warn at validation time.

.PARAMETER Expire
    Days from now until expiry, or `never`.

.PARAMETER IncludeBearerLine
    Also print Authorization header line using base64url(canonical UTF-8 JSON).

.EXAMPLE
    .\scripts\powershell\Generate-WebhookBearerToken.ps1 -Expire 180 -WarnDays 30 -IncludeBearerLine
#>
[CmdletBinding()]
param(
    [int] $WarnDays = 30,
    [string] $Expire = "180",
    [switch] $IncludeBearerLine
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function B64Url-NoPad([byte[]]$Data) {
    [Convert]::ToBase64String($Data).TrimEnd('=').Replace('+','-').Replace('/','_')
}

function Parse-ExpireDays([string]$Value) {
    $v = $Value.Trim().ToLowerInvariant()
    if ($v -eq "never") { return $null }
    $n = 0
    if (-not [int]::TryParse($v, [ref]$n) -or $n -lt 0) {
        throw "Expire must be non-negative integer days or 'never'."
    }
    return $n
}

$iat = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$expDays = Parse-ExpireDays $Expire
$expJson = "null"
if ($null -ne $expDays) {
    $exp = $iat + ($expDays * 86400)
    $expJson = "$exp"
}

$keyBytes = New-Object byte[] 16
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($keyBytes)
$key = B64Url-NoPad $keyBytes

# Canonical key order, compact JSON
$canonical = "{`"exp`":$expJson,`"iat`":$iat,`"key`":`"$key`",`"warn`":$WarnDays}"
Write-Output $canonical

if ($IncludeBearerLine) {
    $wire = B64Url-NoPad ([System.Text.Encoding]::UTF8.GetBytes($canonical))
    Write-Output "Authorization: Bearer $wire"
}
