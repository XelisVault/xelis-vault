#!/usr/bin/env bash
# XELIS Vault Relayer launcher (Unix/Linux/macOS)
VAULT_DIR="${HOME}/.xelis-vault"

if [[ -x "${VAULT_DIR}/venv/bin/python" ]]; then
    exec "${VAULT_DIR}/venv/bin/python" "${VAULT_DIR}/src/scripts/relayer_daemon.py" "$@"
elif command -v python3 &>/dev/null; then
    exec python3 "${VAULT_DIR}/src/scripts/relayer_daemon.py" "$@"
else
    echo "Error: Python not found. Install Python 3 or set up the venv." >&2
    exit 1
fi
