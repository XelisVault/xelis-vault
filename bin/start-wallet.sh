#!/usr/bin/env bash
# Xelis Vault - Start Wallet (Unix/Linux/macOS)
# Usage: ./start-wallet.sh [password]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Find Python
PYTHON=""
if [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON="python3"
elif command -v python &> /dev/null; then
    PYTHON="python"
else
    echo "ERROR: Python not found. Please install Python or create venv."
    exit 1
fi

# Default password
PASS="${1:-testpass}"

# Wallet port
PORT=18082

echo ""
echo "========================================"
echo "  XELIS WALLET"
echo "========================================"
echo ""
echo "  RPC: http://127.0.0.1:$PORT/json_rpc"
echo "  User: wallet"
echo "  Pass: $PASS"
echo ""
echo "  Starting wallet..."
echo "  Press Ctrl+C to stop"
echo ""

# Start wallet
$PYTHON src/scripts/onboarding.py wallet --password "$PASS" --port $PORT
