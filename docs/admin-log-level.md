# Admin log level (signed HTTP)

Runtime root log level is changed with a **signed `POST`** to a **secret path** configured on the server. There is **no** file-based override.

Server settings (`[server.admin]` in your config TOML, canonical filename `thaum.toml`):

| Key | Meaning |
|-----|--------|
| `route_id` | Non-empty segment; route is `POST /{route_id}/log-level`. Empty disables the endpoint. |
| `hmac_secret_b64url` | 32-byte key, base64url (no padding). Supports `env:VAR`, `file:…`, etc. via `resolve_secret`. |
| `clock_skew_seconds` | Max \(\|\text{now} - \text{request time}\|\) in seconds (default 300). |
| `log_state_poll_seconds` | If &gt; 0, each worker polls `admin_log_level_state.updated_at` to stay in sync. |

Environment override: **`THAUM_LOG_ADMIN_HMAC_SECRET_B64U`** replaces the config secret when set.

## Request

**Path:** `POST /{route_id}/log-level`

**Headers**

- `X-Thaum-Timestamp` — ISO-8601 UTC (e.g. `2026-04-01T12:00:00Z`).
- `X-Thaum-Nonce` — 32 **lowercase** hex characters (16 random bytes).
- `X-Thaum-Signature` — `HS256.` + base64url (**no padding**) of `HMAC-SHA256(key, canonical_utf8)`.

**Body (JSON)**

```json
{"loglevel":"DEBUG","v":1}
```

- `v` must be `1`.
- `loglevel` is case-insensitive; allowed values are the Thaum log level names plus **`default`** (clears runtime override and restores `[logging].level` in each worker).
- Normalized level names match `log_setup.parse_level_name` (e.g. `SPAM`, `DEBUG`, `INFO`, …).

## Canonical string (UTF-8)

Sign this exact layout (newline = `\n`, final line empty):

```text
thaum-log-level-v1
POST
/{route_id}/log-level
{epoch_seconds}
{nonce_hex}
loglevel={NORMALIZED}
v=1

```

- `{epoch_seconds}` is **UTC** epoch seconds (integer decimal text) derived from `X-Thaum-Timestamp`.
- `{nonce_hex}` is the header value (lowercase).
- `{NORMALIZED}` is `DEFAULT` or the level name in **uppercase** (e.g. `DEBUG`).

## Persistence

- **`admin_log_nonce`** — stores used nonces with `expires_at`; duplicate nonce ⇒ `401`.
- **`admin_log_level_state`** — singleton row `id=1`: `log_level` (nullable) and `updated_at`. Workers optionally poll this row to apply the same root level.

## Tooling parity

Equivalent script functions exist in both languages:

- Set runtime log level (signed POST):
  - `scripts/powershell/Set-ThaumLogLevel.ps1`
  - `scripts/python/thaum_log_override.py`
- Generate admin route/secret + config snippets:
  - `scripts/powershell/Generate-ThaumAdminLogConfig.ps1`
  - `scripts/python/generate_admin_log_config.py`
- Generate webhook bearer token:
  - `scripts/powershell/Generate-WebhookBearerToken.ps1`
  - `scripts/python/generate_webhook_bearer_token.py`

All scripts implement the protocol contract in this document.

## PowerShell client

Use **[scripts/powershell/Set-ThaumLogLevel.ps1](../scripts/powershell/Set-ThaumLogLevel.ps1)** with a profile INI (see **[scripts/powershell/thaum-admin-log.example.ini](../scripts/powershell/thaum-admin-log.example.ini)**):

```ini
[thaum]
BaseUrl=https://your-host
RouteId=your-secret-segment
HmacSecretB64Url=your-32-byte-key-base64url
```

Or set **`PostUrl`** to the full `https://host/segment/log-level` (path must end with `/<RouteId>/log-level`).

```powershell
.\scripts\powershell\Set-ThaumLogLevel.ps1 -Profile "$env:USERPROFILE\.thaum\admin-log.ini" DEBUG
.\scripts\powershell\Set-ThaumLogLevel.ps1 -Profile ... default
```

## Test vector (HS256)

32-byte all-zero key as base64url (no padding):

```text
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
```

Fixed inputs:

- `route_id` = `testrouteid001`
- `epoch_seconds` = `1700000000`
- `nonce_hex` = `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- `loglevel` = `DEBUG` (canonical `loglevel=DEBUG`)

Canonical message (hex of UTF-8 bytes) ends with `0a` after `v=1` (trailing newline).

Expected `X-Thaum-Signature` value (base64url of raw HMAC output, no padding):

```text
HS256.yvQxOMFbrgE2e8uqSHAJctxQNClKvdQ9qY62JJ6GqPY
```

Verifying in Python:

```python
import base64, binascii, hashlib, hmac

def b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

key = b64u_decode("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
assert len(key) == 32
msg = (
    "thaum-log-level-v1\nPOST\n/testrouteid001/log-level\n1700000000\n"
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nloglevel=DEBUG\nv=1\n"
).encode()
mac = hmac.new(key, msg, hashlib.sha256).digest()
assert base64.urlsafe_b64encode(mac).decode().rstrip("=") == "yvQxOMFbrgE2e8uqSHAJctxQNClKvdQ9qY62JJ6GqPY"
```
