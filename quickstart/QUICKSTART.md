# Thaum quickstart

Thaum reads configuration from `THAUM_CONFIG_FILE` (default in the container image: `/etc/thaum/thaum.conf`). Production deployments typically:

- Mount config and persistent data (database, logs)
- Store sensitive values outside the config file using **systemd encrypted credentials** and `secret:name` entries in TOML (see [`systemd/thaum.conf.example`](systemd/thaum.conf.example))

Shared artifacts for both paths below:

- Example config: [`systemd/thaum.conf.example`](systemd/thaum.conf.example)
- Interactive credential helper: [`systemd/scripts/setup-systemd-credentials.sh`](systemd/scripts/setup-systemd-credentials.sh)

## Choose a deployment path

| Path | Use when |
|------|----------|
| [**systemd/quadlet**](systemd/quadlet/README.md) | Podman Quadlet + container image; app reachable on **127.0.0.1:5165** on the host |
| [**systemd/containerless**](systemd/containerless/README.md) | Bare metal / venv + systemd; **Unix domain socket** upstream to nginx (recommended for multi-service hosts) |
