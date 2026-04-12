# Azure App Service + GitHub Actions

Deploy Thaum as a **single** Linux container on **Azure App Service**, built and pushed from **GitHub Actions**. This path targets **one Web App instance** and **low cost**: it is **not** a horizontal-scaling or high-availability guide.

- General Thaum quickstart: [QUICKSTART.md](../../../QUICKSTART.md)
- Example TOML (adjust for Azure): [systemd/thaum.conf.example](../../../systemd/thaum.conf.example)
- Container image tags (GHCR, etc.): [README.md](../../../../README.md) (section *Container images (CI)*)

## What you get

| Aspect | Behavior |
|--------|----------|
| **Topology** | One App Service plan, one Web App, one container revision |
| **Default database** | **Bundled PostgreSQL** inside the official Thaum image (`THAUM_EXTERNAL_DB` unset or false). No managed database cost. |
| **Data durability** | App Service **local disk is often ephemeral**. The bundled Postgres store can **lose data** on restart or move unless you attach **persistent storage** to the volume used for Postgres data, or switch to an external database (see below). Acceptable for lab/low-cost; use external DB or storage for production expectations. |
| **Optional upgrade** | **Azure Database for PostgreSQL** (or other managed Postgres): set **`THAUM_EXTERNAL_DB=true`**, set **`[server.database].db_url`** in your TOML (and supply secrets via env or Key Vault). See [Optional: external managed Postgres](#optional-external-managed-postgres). |

## Prerequisites

- Azure subscription and permission to create resource groups, App Service, and (recommended) Azure Container Registry
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) (`az login`)
- A GitHub repository for **your** deployment assets (Dockerfile + config + workflow). This can be a **separate** repo from the Thaum source tree, or a folder in a monorepo

Copy the example files from this directory into that repo:

- [Dockerfile.example](Dockerfile.example) → `Dockerfile`
- [deploy.yml.example](deploy.yml.example) → `.github/workflows/deploy.yml`
- Optionally [scripts/keyvault-uri.ps1.example](scripts/keyvault-uri.ps1.example) → `scripts/keyvault-uri.ps1`

## 1. Create Azure resources (CLI)

Pick names (globally unique for Web App and ACR):

```bash
export SUBSCRIPTION="<your-subscription-id-or-name>"
export LOCATION="eastus"
export RG="thaum-rg"
export PLAN="thaum-plan"
export APP="thaum-app-<unique>"
export ACR="thaumacr<unique>"   # 5–50 alphanumeric only, globally unique

az account set --subscription "$SUBSCRIPTION"
az group create --name "$RG" --location "$LOCATION"

# Linux App Service plan (adjust SKU: B1 is a common dev size; production may differ)
az appservice plan create \
  --name "$PLAN" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --is-linux \
  --sku B1

# Web App for containers (placeholder image; you will point to ACR after first push)
az webapp create \
  --name "$APP" \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --deployment-container-image-name "mcr.microsoft.com/azuredocs/aci-helloworld:latest"

# Container listens on 5165 (Gunicorn in the Thaum image)
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings WEBSITES_PORT=5165

# Optional: reduce cold starts on supported SKUs (adds cost)
# az webapp config set --resource-group "$RG" --name "$APP" --always-on true
```

### Azure Container Registry (recommended)

Push **your** image (Dockerfile `FROM` upstream Thaum + your config) to ACR; the Web App pulls from there.

```bash
az acr create --resource-group "$RG" --name "$ACR" --sku Basic --admin-enabled true
az acr credential show --name "$ACR" --query "passwords[0].value" -o tsv   # save for GitHub Secrets if not using service principal alone
```

After your pipeline pushes `YOUR_ACR.azurecr.io/your-image:tag`, point the Web App at it (see [deploy.yml.example](deploy.yml.example) or run `az webapp config container set` with your registry URL, image name, and credentials).

**Portal:** You can create the same resources in the Azure Portal (**Create a resource** → **Web App** → **Docker Container**, Linux). Set **Configuration** → **Application settings** → add **`WEBSITES_PORT` = `5165`**.

### Health checks

Thaum exposes:

- `GET /health` — process liveness
- `GET /ready` — database readiness (`SELECT 1`)

Configure App Service **Health check** (when available on your plan) to hit `/ready` or `/health` on your site’s HTTPS URL. Paths are under your public `base_url` host.

## 2. Configuration file

1. Start from [systemd/thaum.conf.example](../../../systemd/thaum.conf.example).
2. Set **`[server].base_url`** to your Web App’s public URL, for example `https://thaum-app-<unique>.azurewebsites.net` (or your custom domain).
3. Place the file in your deploy repo as **`thaum.conf`** (or another name and set `THAUM_CONFIG_FILE` in the Dockerfile).

The stock Thaum container defaults to `THAUM_CONFIG_FILE=/etc/thaum/thaum.conf`. The [Dockerfile.example](Dockerfile.example) copies your file to that path.

Keep secrets out of committed files: use **`env:`** references and App Service **Configuration** application settings, or Key Vault references (see [Key Vault URI helper](#key-vault-uri-helper)).

### `THAUM_BASE_URL` in CI

If your pipeline substitutes `base_url` via environment at build time, some checks may expect **`THAUM_BASE_URL`**; see `thaum_config_check.py` epilog in the main repo. For a static committed TOML with a real `base_url`, you typically do not need this.

## 3. Dockerfile (deploy repo)

Use [Dockerfile.example](Dockerfile.example):

- **`FROM`** a **pinned** upstream image (version tag or digest), not only `:latest`, for reproducible deploys. Default upstream: `ghcr.io/gemstone-software-dev/thaum` (see [README.md](../../../../README.md)).
- **`COPY`** your versioned `thaum.conf` into `/etc/thaum/`.
- For **external Postgres**, set **`THAUM_EXTERNAL_DB=true`** in the Dockerfile or App Service settings and supply **`db_url`** (and secrets) as documented in [ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md).

## 4. GitHub Actions

Copy [deploy.yml.example](deploy.yml.example) to `.github/workflows/deploy.yml` and set:

- **Repository variables** (or hardcode in the workflow): resource group, Web App name, ACR login server, image name/tag
- **Repository secrets**
  - **`AZURE_CREDENTIALS`**: JSON output of a service principal with rights to push to ACR and update the Web App (e.g. `az ad sp create-for-rbac --name "gha-thaum" --role contributor --scopes /subscriptions/<sub>/resourceGroups/<rg> --sdk-auth`)
  - Registry credentials if your workflow uses explicit `docker login` (some setups rely on `az acr login` after `azure/login` with an SP that has `AcrPush`)

The workflow **builds** your image, runs **`thaum_config_check.py --schema-check`** **inside** the built image (no checkout of the Thaum source repo required), **pushes** to ACR, and **updates** the Web App container. The example uses **`az acr credential show`** so the Web App can pull the image; **ACR admin account** must be enabled (see CLI snippet above). If your org disables admin users, configure pull authentication separately (for example [managed identity for the Web App](https://learn.microsoft.com/azure/app-service/configure-custom-container)) and replace the `az webapp config container set` step accordingly.

- **`--schema-check`**: safe in CI without resolving secrets or hitting the database.
- **`--test-config`**: full validation + DB ping; run only where secrets and DB exist (e.g. manual run on a trusted host or a protected environment).

## Optional: external managed Postgres

1. Create a managed Postgres instance and a database/user for Thaum.
2. Set App Service application setting **`THAUM_EXTERNAL_DB=true`**.
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
| [Dockerfile.example](Dockerfile.example) | `FROM` upstream Thaum image + `COPY` `thaum.conf` |
| [deploy.yml.example](deploy.yml.example) | Build → schema-check → push to ACR → update Web App |
| [scripts/keyvault-uri.ps1.example](scripts/keyvault-uri.ps1.example) | Print Key Vault URI (non-interactive) |
| [scripts/keyvault-uri.bat.example](scripts/keyvault-uri.bat.example) | Invoke the PowerShell script from cmd |
