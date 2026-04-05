#Requires -Version 5.1
# Generate-ThaumAdminLogConfig.ps1
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
<#
.SYNOPSIS
    Generate admin route/secret material and config snippets for log-level admin API.

.DESCRIPTION
    Creates a random route id and 32-byte HMAC key (base64url no padding), and
    outputs ready-to-paste `config.toml` `[server.admin]` lines plus an INI profile compatible with
    Set-ThaumLogLevel.ps1. Optionally writes the key to a secret file and writes
    the profile to disk.

.PARAMETER BaseUrl
    Base URL used in generated client profile output.

.PARAMETER RouteId
    Explicit route id. If omitted, a random route id is generated.

.PARAMETER RouteLength
    Route-id length when randomly generated.

.PARAMETER SecretFile
    Optional path to write the base64url secret; output server snippet will use file: reference.

.PARAMETER ProfileIni
    Optional path to write INI profile.

.PARAMETER UsePostUrl
    Write PostUrl in profile instead of BaseUrl+RouteId.

.EXAMPLE
    .\scripts\powershell\Generate-ThaumAdminLogConfig.ps1 -BaseUrl https://thaum.example.com -ProfileIni "$env:USERPROFILE\.thaum\admin-log.ini"
#>
[CmdletBinding()]
param(
    [string] $BaseUrl = "https://thaum.example.com",
    [string] $RouteId,
    [int] $RouteLength = 24,
    [string] $SecretFile,
    [string] $ProfileIni,
    [switch] $UsePostUrl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-RouteId([int]$Length) {
    $alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-".ToCharArray()
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] $Length
    $rng.GetBytes($bytes)
    $chars = New-Object char[] $Length
    # Modulo is unbiased here: alphabet length is 64 and byte range is 256,
    # so each symbol gets exactly 4 source-byte values (256 % 64 == 0).
    for ($i = 0; $i -lt $Length; $i++) { $chars[$i] = $alphabet[$bytes[$i] % $alphabet.Length] }
    return -join $chars
}

function B64Url-NoPad([byte[]]$Data) {
    [Convert]::ToBase64String($Data).TrimEnd('=').Replace('+','-').Replace('/','_')
}

if (-not $RouteId) { $RouteId = New-RouteId $RouteLength }
$key = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($key)
$secretB64u = B64Url-NoPad $key

$secretRef = $secretB64u
if ($SecretFile) {
    $parent = Split-Path -Parent $SecretFile
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    Set-Content -LiteralPath $SecretFile -Value $secretB64u -Encoding UTF8
    $secretRef = "file:$($SecretFile -replace '\\','/')"
}

if ($ProfileIni) {
    $parent = Split-Path -Parent $ProfileIni
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    if ($UsePostUrl) {
        @(
            "[thaum]"
            "PostUrl=$($BaseUrl.TrimEnd('/'))/$RouteId/log-level"
            "HmacSecretB64Url=$secretB64u"
        ) | Set-Content -LiteralPath $ProfileIni -Encoding UTF8
    } else {
        @(
            "[thaum]"
            "BaseUrl=$($BaseUrl.TrimEnd('/'))"
            "RouteId=$RouteId"
            "HmacSecretB64Url=$secretB64u"
        ) | Set-Content -LiteralPath $ProfileIni -Encoding UTF8
    }
}

Write-Output "# --- server [server.admin] snippet (config.toml) ---"
Write-Output "[server.admin]"
Write-Output "route_id = `"$RouteId`""
Write-Output "hmac_secret_b64url = `"$secretRef`""
Write-Output "clock_skew_seconds = 300"
Write-Output "log_state_poll_seconds = 2.0"
Write-Output ""
Write-Output "# --- client profile (INI) ---"
if ($UsePostUrl) {
    Write-Output "[thaum]"
    Write-Output "PostUrl=$($BaseUrl.TrimEnd('/'))/$RouteId/log-level"
    Write-Output "HmacSecretB64Url=$secretB64u"
} else {
    Write-Output "[thaum]"
    Write-Output "BaseUrl=$($BaseUrl.TrimEnd('/'))"
    Write-Output "RouteId=$RouteId"
    Write-Output "HmacSecretB64Url=$secretB64u"
}
