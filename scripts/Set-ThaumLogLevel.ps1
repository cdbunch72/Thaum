#Requires -Version 5.1
<#
.SYNOPSIS
    Set Thaum root log level via signed POST (see docs/admin-log-level.md).

.PARAMETER Profile
    Path to INI file with [thaum] BaseUrl, RouteId, HmacSecretB64Url (optional PostUrl instead of BaseUrl+RouteId).

.PARAMETER LogLevel
    Level name (DEBUG, INFO, default, etc.) or overrides profile for this invocation.

.PARAMETER SecretB64Url
    Overrides profile HmacSecretB64Url.

.PARAMETER BaseUrl
    Overrides profile BaseUrl (no trailing slash).

.PARAMETER RouteId
    Overrides profile RouteId.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string] $Profile,

    [Parameter(Mandatory = $true, Position = 0)]
    [string] $LogLevel,

    [string] $SecretB64Url,
    [string] $BaseUrl,
    [string] $RouteId,
    [string] $PostUrl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Read-ThaumAdminIni {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Profile not found: $Path"
    }
    $ini = @{}
    $section = ''
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -match '^\s*[;#]') { return }
        if ($line -match '^\[(.+)\]\s*$') { $section = $Matches[1].Trim(); return }
        if ($line -match '^([^=]+)=(.*)$') {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim()
            if ($section) { $ini["$section|$key"] = $val }
            else { $ini[$key] = $val }
        }
    }
    return $ini
}

function B64Url-Decode {
    param([string] $s)
    $t = $s.Replace('-', '+').Replace('_', '/')
    switch ($t.Length % 4) {
        2 { $t += '==' }
        3 { $t += '=' }
    }
    return [Convert]::FromBase64String($t)
}

function B64Url-Encode-Raw {
    param([byte[]] $bytes)
    $b64 = [Convert]::ToBase64String($bytes)
    $b64 = $b64.TrimEnd('=').Replace('+', '-').Replace('/', '_')
    return $b64
}

function New-HexNonce32 {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buf = New-Object byte[] 16
    $rng.GetBytes($buf)
    return ([BitConverter]::ToString($buf)).Replace('-', '').ToLowerInvariant()
}

function Build-CanonicalMessage {
    param(
        [string] $RouteId,
        [int] $EpochSec,
        [string] $NonceHex,
        [string] $LogLevelNorm
    )
    $lines = @(
        'thaum-log-level-v1',
        'POST',
        "/$RouteId/log-level",
        "$EpochSec",
        $NonceHex,
        "loglevel=$LogLevelNorm",
        'v=1',
        ''
    )
    $text = ($lines -join "`n")
    return [System.Text.Encoding]::UTF8.GetBytes($text)
}

# --- load profile ---
$pBase = ''
$pRoute = ''
$pSecret = ''
$pPost = ''

if ($Profile) {
    $ini = Read-ThaumAdminIni -Path $Profile
    $pBase = $ini['thaum|BaseUrl']
    $pRoute = $ini['thaum|RouteId']
    $pSecret = $ini['thaum|HmacSecretB64Url']
    $pPost = $ini['thaum|PostUrl']
}

if ($BaseUrl) { $pBase = $BaseUrl }
if ($RouteId) { $pRoute = $RouteId }
if ($SecretB64Url) { $pSecret = $SecretB64Url }
if ($PostUrl) { $pPost = $PostUrl }

if (-not $pSecret) { throw 'HmacSecretB64Url is required (profile or -SecretB64Url).' }

$key = B64Url-Decode -s $pSecret
if ($key.Length -ne 32) { throw 'Decoded HMAC key must be 32 bytes.' }

$routeForCanon = $pRoute
if ($pPost) {
    $postUri = $pPost
    $u = [Uri]$pPost
    $segs = $u.AbsolutePath.Trim('/').Split([char[]]@('/'), [StringSplitOptions]::RemoveEmptyEntries)
    if ($segs.Length -lt 2 -or $segs[-1] -ne 'log-level') {
        throw "PostUrl path must end with /<RouteId>/log-level"
    }
    $routeForCanon = $segs[-2]
}
else {
    if (-not $pBase -or -not $pRoute) { throw 'Need PostUrl or both BaseUrl and RouteId (profile or parameters).' }
    $b = $pBase.TrimEnd('/')
    $postUri = "$b/$pRoute/log-level"
}

$raw = $LogLevel.Trim()
$norm = $raw.ToUpperInvariant()
if ($norm -eq 'DEFAULT') {
    $canonicalLevel = 'DEFAULT'
}
else {
    $canonicalLevel = $norm
}

$nonce = New-HexNonce32
$ts = [DateTimeOffset]::UtcNow
$epoch = [int64]$ts.ToUnixTimeSeconds()
$tsIso = $ts.ToString('yyyy-MM-ddTHH:mm:ss') + 'Z'

$msg = Build-CanonicalMessage -RouteId $routeForCanon -EpochSec $epoch -NonceHex $nonce -LogLevelNorm $canonicalLevel

$hmac = New-Object System.Security.Cryptography.HMACSHA256 (,$key)
$mac = $hmac.ComputeHash($msg)
$sig = 'HS256.' + (B64Url-Encode-Raw -bytes $mac)

$bodyObj = @{ loglevel = $raw; v = 1 }
$json = $bodyObj | ConvertTo-Json -Compress

$headers = @{
    'X-Thaum-Timestamp' = $tsIso
    'X-Thaum-Nonce'     = $nonce
    'X-Thaum-Signature' = $sig
    'Content-Type'      = 'application/json'
}

Invoke-RestMethod -Uri $postUri -Method Post -Headers $headers -Body $json
