# Thaum Podman/systemd Quickstart

This quickstart shows a minimal Quadlet deployment with:

- Config mounted at `/etc/thaum`
- Logs persisted at `/var/log/thaum`
- Database persisted at `/var/lib/thaum`
- Secrets loaded with systemd encrypted credentials and referenced as `secret:name`

## 1) Prerequisites

- Podman with Quadlet support
- systemd with `systemd-creds`
- A built/published Thaum image (the sample uses `localhost/thaum:latest`)

## 2) Create local config

Copy the example config and edit non-secret values:

- `docs/quickstart/thaum.conf.example`

Install it as `/etc/thaum/thaum.conf` (or another directory you mount to `/etc/thaum`).

Secret-backed keys in this example:

- `[server.database].db_url = "secret:thaum_db_url"`
- `[server.database].database_vault_passphrase = "secret:thaum_database_vault_passphrase"`
- `[defaults.alert.jira].api_token = "secret:thaum_jira_api_token"`
- `[bots.database].token = "secret:thaum_webex_token_database"`

## 3) Create encrypted credentials

Run:

```bash
sudo ./docs/quickstart/setup-systemd-credentials.sh
```

The script prompts for each value and writes encrypted credentials to:

- `/etc/credstore.encrypted/thaum_db_url`
- `/etc/credstore.encrypted/thaum_database_vault_passphrase`
- `/etc/credstore.encrypted/thaum_jira_api_token`
- `/etc/credstore.encrypted/thaum_webex_token_database`

## 4) Install Quadlet files

Copy these files to `/etc/containers/systemd/`:

- `docs/quickstart/quadlet/thaum.container`
- `docs/quickstart/quadlet/thaum-data.volume`
- `docs/quickstart/quadlet/thaum-log.volume`

Then ensure `/etc/thaum/thaum.conf` exists and reload systemd:

```bash
sudo systemctl daemon-reload
```

## 5) Load encrypted credentials into the service

Install the drop-in from:

- `docs/quickstart/quadlet/thaum.service.credentials.conf.example`

to:

- `/etc/systemd/system/thaum.service.d/credentials.conf`

Then reload:

```bash
sudo systemctl daemon-reload
```

## 6) Start and verify

```bash
sudo systemctl enable --now thaum.service
sudo systemctl status thaum.service
sudo journalctl -u thaum.service -n 100 --no-pager
```

If you enable file logging (`[logging] file = true`), logs are written to `/var/log/thaum/thaum.log`.
