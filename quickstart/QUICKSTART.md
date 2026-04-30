# Thaum quickstart

Thaum reads configuration from `THAUM_CONFIG_FILE` (default in the container image: `/etc/thaum/thaum.conf`). The default container layout runs **bundled PostgreSQL** in the image unless `THAUM_EXTERNAL_DB` is set (see [Architecture](../docs/ARCHITECTURE.md)). Production deployments typically:

- Mount config and persistent data (database, logs)
- Store sensitive values outside the config file using **systemd encrypted credentials** and `secret:name` entries in TOML (see [`systemd/thaum.conf.example`](systemd/thaum.conf.example))

Shared artifacts for both paths below:

- Example config: [`systemd/thaum.conf.example`](systemd/thaum.conf.example)
- Interactive credential helper: [`systemd/scripts/setup-systemd-credentials.sh`](systemd/scripts/setup-systemd-credentials.sh)
- Atlassian Cloud (**site id**, **org id**, API token): [Atlassian / Jira](../docs/Atlassian-Jira.md)
- LDAP / Active Directory lookup (optional **platform_ids** attribute): [LDAP-AD lookup](../docs/LDAP-AD-lookup.md)

## Choose a deployment path

| Path | Use when |
|------|----------|
| [**systemd/quadlet**](systemd/quadlet/README.md) | Podman Quadlet + container image; app reachable on **127.0.0.1:5165** on the host |
| [**systemd/containerless**](systemd/containerless/README.md) | Bare metal / venv + systemd; **Unix domain socket** upstream to nginx (recommended for multi-service hosts) |
| [**cloud/azure/github**](cloud/azure/github/README.md) | **Azure Container Apps** + **GitHub Actions**; single-instance quickstart with example Dockerfile and workflow |
| [**kubernetes**](kubernetes/README.md) | **Kubernetes** (on-prem or cloud clusters); HA-oriented guide with example manifests and external Postgres |
