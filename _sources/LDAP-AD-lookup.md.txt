# LDAP / Active Directory lookup (`lookup.plugins.ldap_ad`)

Thaum’s **LDAP AD** lookup plugin resolves people and groups from your directory and merges them into the shared identity cache (`schema_person` / `schema_platform_id`). Configure it under **`[lookup.ldap_ad]`** (merged with **`[lookup]`**).

## Primary person identity

- **`person_id_mode`** / **`person_id_attribute`** — how **`get_person_by_id`** finds a user (e.g. `sAMAccountName`, `uid`).
- **`email_attribute`** / **`fallback_email_attributes`** — mail and UPN for **`get_person_by_email`** and cache keys.

## Extra platform ids (`jira`, `webex`, …)

Optional fields **`platform_ids_ldap_attribute`** and **`platform_ids_format`** let you store **additional** Thaum **`platform_ids`** (beyond the primary LDAP id) in a dedicated directory attribute.

- **`platform_ids_ldap_attribute`** — LDAP attribute name (e.g. an extension attribute your ID team provisions). If unset, behavior is unchanged: only the primary id from **`person_id`** or (for group members) the member **DN** under **`ldap_ad`** is used.
- **`platform_ids_format`** — how that attribute is encoded:

| Value | Meaning |
|-------|--------|
| **`json`** | **Single-valued** attribute containing a JSON **object**: keys are Thaum platform keys (`jira`, `webex`, …), values are string ids. |
| **`multi-value-attr-delimited`** | Same as **`multi-value-attr-delimited(:)`** — **multi-valued** attribute; each value is **`plugin` + `:` + `id`**. |
| **`multi-value-attr-delimited(:)`** | Delimiter **`:`** (explicit). |
| **`multi-value-attr-delimited(/)`** | Delimiter **`/`**. |
| **`multi-value-attr-delimited(,)`** | Delimiter **`,`**. |

For **delimited** encodings, each line is split on the **first** occurrence of the delimiter only, so the id portion may contain further delimiter characters if you choose a different delimiter (e.g. `:id:with:colons` with delimiter `/`).

### Merge semantics

The plugin builds a base map (e.g. `{ "webex": "<id>", "ldap_ad": "<dn>" }`) and merges **extra** ids from **`platform_ids_ldap_attribute`**. Keys from the LDAP attribute **override** the same key from the base map on conflict, so explicit ids in the attribute win.

## Limits and operations

Directory servers enforce **per-attribute** size and count limits; values vary by vendor and OID. Normal deployments with a **small** number of platform ids per user are fine. **Dozens** of distinct plugins per person is unusual; if you approach directory limits, prefer a compact JSON object or review whether the design is appropriate.

Malformed JSON or bad delimited lines are logged and skipped so a single bad entry does not fail the whole lookup.
