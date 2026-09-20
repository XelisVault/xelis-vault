#!/usr/bin/env bash
# XELIS Vault CLI launcher (Unix/Linux/macOS)
VAULT_DIR="${HOME}/.xelis-vault"

# Try venv first, then system python
if [[ -x "${VAULT_DIR}/venv/bin/python" ]]; then
    exec "${VAULT_DIR}/venv/bin/python" "${VAULT_DIR}/src/scripts/xvault.py" "$@"
elif command -v python3 &>/dev/null; then
    exec python3 "${VAULT_DIR}/src/scripts/xvault.py" "$@"
else
    echo "Error: Python not found. Install Python 3 or set up the venv." >&2
    exit 1
fi
