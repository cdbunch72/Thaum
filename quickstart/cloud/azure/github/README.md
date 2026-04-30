# Azure Container Apps + GitHub Actions

Deploy Thaum as a **single** container app on **Azure Container Apps**, built and pushed from **GitHub Actions**. This path targets a low-friction single service deployment; scale and high-availability tuning are out of scope for this quickstart.

- General Thaum quickstart: [QUICKSTART.md](../../../QUICKSTART.md)
- Example TOML (adjust for Azure): [systemd/thaum.conf.example](../../../systemd/thaum.conf.example)
- Container image tags (GHCR, etc.): [README.md](../../../../README.md) (section *Container images (CI)*)

## What you get

| Aspect | Behavior |
|--------|----------|
| **Topology** | One resource group, one Container Apps environment, one Container App |
| **Default database** | **Bundled PostgreSQL** inside the official Thaum image (`THAUM_EXTERNAL_DB` unset or false). No managed database cost. |
| **Data durability** | Container filesystem is **ephemeral**. The bundled Postgres store can **lose data** on revision change or restart unless you add persistent storage or switch to an external database. |
| **Optional upgrade** | **Azure Database for PostgreSQL** (or other managed Postgres): set **`THAUM_EXTERNAL_DB=true`**, set **`[server.database].db_url`** in your TOML (and supply secrets via env or Key Vault). See [Optional: external managed Postgres](#optional-external-managed-postgres). |

## Prerequisites

- Azure subscription and permission to create resource groups and Container Apps resources
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) (`az login`)
- A GitHub repository for **your** deployment assets (Dockerfile + config + workflow). This can be a **separate** repo from the Thaum source tree, or a folder in a monorepo

Copy the example files from this directory into that repo:

- [Dockerfile.example](Dockerfile.example) → `Dockerfile`
- [deploy.yml.example](deploy.yml.example) → `.github/workflows/deploy.yml`
- Optionally [scripts/keyvault-uri.ps1.example](scripts/keyvault-uri.ps1.example) → `scripts/keyvault-uri.ps1`

## 1. Create Azure resources (CLI)

Pick names and run the setup in PowerShell:

```powershell
$SUBSCRIPTION = "<your-subscription-id-or-name>"
$LOCATION = "eastus"
$RESOURCE_GROUP = "thaum-rg"
$ENVIRONMENT = "thaum-env"
$APP_NAME = "thaum-app"

az account set --subscription $SUBSCRIPTION
az upgrade
az extension add --name containerapp --upgrade --allow-preview true
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az group create --name $RESOURCE_GROUP --location $LOCATION

az containerapp up `
  --name $APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --location $LOCATION `
  --environment $ENVIRONMENT `
  --source .
```

The `az containerapp up` command creates (or reuses) the resource group, registry, environment, and app, then builds/deploys from your local source.

### Secret mount and `secret:key` config pattern

Thaum supports credential indirection as `secret:key`. For Azure Container Apps, define secrets in the app and mount them as files under `/run/secrets`, then reference those names in `thaum.toml`.

Example Container Apps commands:

```powershell
az containerapp secret set `
  --name $APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --secrets webex_token_database="<token>" webex_token_system="<token>" webex_token_helpdesk="<token>"

az containerapp update `
  --name $APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --set-env-vars THAUM_CREDS_DIR=/tmp/thaum-creds `
  --yaml containerapp.secrets.yaml
```

Use a small YAML patch (`containerapp.secrets.yaml`) to mount a `Secret` volume at `/run/secrets` and map secret items to filenames. The filename should match the `secret:key` identifier you use in config.

```yaml
properties:
  template:
    containers:
      - name: thaum-app
        volumeMounts:
          - volumeName: thaum-secrets
            mountPath: /run/secrets
    volumes:
      - name: thaum-secrets
        storageType: Secret
        secrets:
          - secretRef: webex_token_database
            path: webex_token_database
          - secretRef: webex_token_system
            path: webex_token_system
          - secretRef: webex_token_helpdesk
            path: webex_token_helpdesk
```

### Health checks

Thaum exposes:

- `GET /health` — process liveness
- `GET /ready` — database readiness (`SELECT 1`)

Configure Container Apps probes to hit `/ready` (or `/health`) on port `5165`.

## 2. Configuration file

1. Start from [systemd/thaum.conf.example](../../../systemd/thaum.conf.example).
2. Set **`[server].base_url`** to your Container App’s public URL.
3. Save it in your deploy repo as **`thaum.toml`** (TOML content; use the **`.toml`** extension for editor highlighting). To use another path, set **`THAUM_CONFIG_FILE`** in the Dockerfile or environment.

The stock Thaum image does **not** set `THAUM_CONFIG_FILE`; the app resolves config automatically (see `thaum.paths.resolve_config_path`). [Dockerfile.example](Dockerfile.example) copies **`thaum.toml`** to **`/etc/thaum/thaum.toml`**.

Keep secrets out of committed files: use `secret:key` references and mounted files in `/run/secrets`, or use Key Vault references (see [Key Vault URI helper](#key-vault-uri-helper)).

### `THAUM_BASE_URL` in CI

If your pipeline substitutes `base_url` via environment at build time, some checks may expect **`THAUM_BASE_URL`**; see `thaum_config_check.py` epilog in the main repo. For a static committed TOML with a real `base_url`, you typically do not need this.

## 3. Dockerfile (deploy repo)

Use [Dockerfile.example](Dockerfile.example):

- **`FROM`** a **pinned** upstream image (version tag or digest), not only `:latest`, for reproducible deploys. Default upstream: `ghcr.io/gemstone-software-dev/thaum` (see [README.md](../../../../README.md)).
- **`COPY`** your versioned `thaum.toml` into `/etc/thaum/` as `/etc/thaum/thaum.toml` (canonical filename).
- For **external Postgres**, set **`THAUM_EXTERNAL_DB=true`** in the Dockerfile or Container Apps env vars and supply **`db_url`** (and secrets) as documented in [ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md).

## 4. GitHub Actions

Copy [deploy.yml.example](deploy.yml.example) to `.github/workflows/deploy.yml` and set:

- **Repository variables** (or hardcode in the workflow): resource group, Container App name, ACR login server, image name/tag
- **Repository secrets**
  - **`AZURE_CREDENTIALS`**: JSON output of a service principal with rights to push to ACR and update the Container App (e.g. `az ad sp create-for-rbac --name "gha-thaum" --role contributor --scopes /subscriptions/<sub>/resourceGroups/<rg> --sdk-auth`)
  - Registry credentials if your workflow uses explicit `docker login` (some setups rely on `az acr login` after `azure/login` with an SP that has `AcrPush`)

The workflow **builds** your image, runs **`thaum_config_check.py --schema-check`** **inside** the built image (no checkout of the Thaum source repo required), **pushes** to ACR, and **updates** the Container App image revision.

- **`--schema-check`**: safe in CI without resolving secrets or hitting the database.
- **`--test-config`**: full validation + DB ping; run only where secrets and DB exist (e.g. manual run on a trusted host or a protected environment).

## Optional: external managed Postgres

1. Create a managed Postgres instance and a database/user for Thaum.
2. Set Container Apps environment variable **`THAUM_EXTERNAL_DB=true`**.
3. In your TOML, set **`[server.database].db_url`** to the SQLAlchemy URL (use **`env:`** or Key Vault; do not commit passwords).
4. Redeploy. The container runs **Gunicorn only** (no bundled Postgres); see [Dockerfile](../../../../Dockerfile) and [docker/entrypoint.sh](../../../../docker/entrypoint.sh).

## Key Vault URI helper

For **`azexp:`** (and related) resolution, the exact reference grammar lives in **gemstone_utils** (Thaum loads the experimental backend when running full config checks). This repo’s checker enables that path in **`--test-config`** only; see `scripts/python/thaum_config_check.py` in the main tree.

To print your Key Vault **vault URI** for documentation or manual TOML editing:

- PowerShell: [scripts/keyvault-uri.ps1.example](scripts/keyvault-uri.ps1.example)
- Or: `az keyvault show --name <VaultName> --query properties.vaultUri -o tsv`

There is **no** interactive “enter all secrets” wizard: operators with **multiple bots** or complex layouts should use **`az keyvault secret set`** (or your org’s process) with naming conventions you control.

## Files in this directory

| File | Purpose |
|------|---------|
| [Dockerfile.example](Dockerfile.example) | `FROM` upstream Thaum image + `COPY` `thaum.toml` → `/etc/thaum/thaum.toml` |
| [deploy.yml.example](deploy.yml.example) | Build → schema-check → push to ACR → update Container App |
| [scripts/keyvault-uri.ps1.example](scripts/keyvault-uri.ps1.example) | Print Key Vault URI (non-interactive) |
| [scripts/keyvault-uri.bat.example](scripts/keyvault-uri.bat.example) | Invoke the PowerShell script from cmd |
