# Atlassian Cloud and Jira (Thaum)

Thaum can integrate with **Atlassian Cloud** using:

- **`[connections.<name>]`** with **`plugin = "atlassian"`** — shared **`site_url`**, **`cloud_id`**, **`org_id`**, **`user`**, and **`api_token`** (merged into **`[lookup.atlassian]`** when **`connection_ref`** is set; see **`sample.config.toml`**).
- **`lookup.atlassian`** — Public Teams API (`api.atlassian.com`) and Jira REST for users; uses platform id key **`jira`** in the identity cache.
- **`alerts.plugins.jira`** — Jira Service Management Ops alerts; same site REST and **`api.atlassian.com/{cloud_id}/...`** paths.

Alert defaults do **not** yet support **`connection_ref`**; duplicate **`site_url`**, **`cloud_id`**, **`user`**, and **`api_token`** in **`[defaults.alert.jira]`** so they match your connection profile, or merge by hand. Use **one** API token credential for both (e.g. **`secret:atlassian-api-token`**) when the token is stored once in systemd credentials.

## Finding **`cloud_id`** (site id)

The **Cloud id** is a UUID Atlassian uses in URLs such as `https://api.atlassian.com/jsm/ops/api/{cloud_id}/...`.

Common ways to obtain it (UI and product names change; verify against current Atlassian help):

- From a Jira Cloud URL: open your site, inspect links or admin/developer tools that expose **cloud id** or **site id**.
- From **Atlassian Administration** / **Products** / **Product URLs** — documentation often describes where the site UUID appears.

Placeholders in samples:

- **`00000000-0000-0000-0000-000000000000`** — replace with your real **site / cloud** UUID (contrast with **`org_id`** below).

## Finding **`org_id`** (organization id)

**`org_id`** is required for **org-scoped** APIs (e.g. Public Teams list under **`/public/teams/v1/org/{orgId}/...`**). It is **not** the same as **`cloud_id`**.

- Obtain it from **Atlassian Administration** for your **organization** (organization settings / API documentation for your tenant).

Placeholder in samples:

- **`ffffffff-ffff-ffff-ffff-ffffffffffff`** — replace with your real **organization** id (distinct from the all-zeros **`cloud_id`** placeholder).

## Service account, API token, and permissions

Use a dedicated **Atlassian account** (often called a “service” or “bot” user in runbooks) and an **API token** created for that account. Thaum sends **HTTP Basic** auth (`user` + **API token**) to **`{site_url}/rest/api/3/...`** and compatible **`api.atlassian.com`** endpoints.

Required scopes and product entitlements depend on your tenant (JSM Ops, Teams, site admin, etc.). **Atlassian’s permission model is complex and poorly summarized in one place**; exact minimum scopes are not guaranteed here.

### What worked for us

We validated Thaum against a combination of:

- Jira REST (**user** lookup by **`accountId`**),
- JSM Ops alert APIs,
- Public Teams list and members APIs,

using a single technical user and API token where possible.

### Caveat

**We do not guarantee** that the same minimal permissions will work in every tenant or after Atlassian changes Cloud behavior. You may need **broader** (or in rare cases **different**) roles or product access than we used. Treat permissions as **trial in a non-production site** first, then tighten. Thaum’s documentation is **not** a substitute for Atlassian’s official security and admin guides.

## Secrets and Quadlet / systemd

Prefer **`secret:credential-name`** in TOML (systemd **encrypted credentials**), not **`file:/run/secrets/...`**, for Quadlet and rootless-friendly layouts: the container entrypoint stages credentials into a path readable by the app user and sets **`CREDENTIALS_DIRECTORY`** (see [quadlet README](../quickstart/systemd/quadlet/README.md)).

The sample uses **`secret:atlassian-api-token`** for the shared Atlassian API token so **one** credential file backs both **`[connections.*].api_token`** and **`[defaults.alert.jira].api_token`** when they share the same token value.
