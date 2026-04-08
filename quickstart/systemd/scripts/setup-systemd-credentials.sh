#!/usr/bin/env bash
set -euo pipefail

CREDSTORE_DIR="${CREDSTORE_DIR:-/etc/credstore.encrypted}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (or use sudo) so credentials can be written to ${CREDSTORE_DIR}."
  exit 1
fi

if ! command -v systemd-creds >/dev/null 2>&1; then
  echo "systemd-creds not found in PATH."
  exit 1
fi

mkdir -p "${CREDSTORE_DIR}"
chmod 0700 "${CREDSTORE_DIR}"

write_credential() {
  local cred_name="$1"
  local prompt="$2"
  local secret_value

  read -r -s -p "${prompt}: " secret_value
  echo

  if [[ -z "${secret_value}" ]]; then
    echo "Credential ${cred_name} was empty; skipping."
    return 1
  fi

  printf '%s' "${secret_value}" | systemd-creds encrypt - "${CREDSTORE_DIR}/${cred_name}" --name="${cred_name}"
  chmod 0600 "${CREDSTORE_DIR}/${cred_name}"
  echo "Saved encrypted credential: ${CREDSTORE_DIR}/${cred_name}"
}

echo "Creating encrypted systemd credentials for Thaum."
write_credential "thaum_db_url" "Database URL (example: sqlite:////var/lib/thaum/thaum.db)"
write_credential "thaum_database_vault_passphrase" "Database vault passphrase"
write_credential "thaum_jira_api_token" "Jira API token"
write_credential "thaum_webex_token_database" "Webex bot token (database bot)"

echo "Done."
