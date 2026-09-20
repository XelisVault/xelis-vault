#!/usr/bin/env bash
# ============================================================================
#   XELIS Vault - Wallet + Oracle Keeper Launcher (Unix/Linux/macOS)
# ============================================================================
set -euo pipefail

VAULT_DIR="${HOME}/.xelis-vault"
WALLET_BIN="${VAULT_DIR}/bin/xelis_wallet"
WALLET_DIR="${VAULT_DIR}/wallets/xvault-user"
LOG_DIR="${VAULT_DIR}/logs"
RPC_PORT=18082
RPC_URL="http://127.0.0.1:${RPC_PORT}/json_rpc"
DAEMON_RPC="https://testnet-node.xelis.io"

# Seed can be provided via environment variable or will be prompted
SEED="${XELIS_WALLET_SEED:-}"
if [[ -z "${SEED}" ]]; then
    echo "  [!] No seed provided. Set XELIS_WALLET_SEED environment variable"
    echo "      or create wallet manually with: xelis_wallet --generate"
    echo ""
    echo "      Example: export XELIS_WALLET_SEED=\"your seed words here\""
    exit 1
fi

# Find keeper binary (exe or Python fallback)
KEEPER_EXE=""
KEEPER_PY="${VAULT_DIR}/src/scripts/xvault-miner.py"
if [[ -x "${VAULT_DIR}/bin/xvault-miner" ]]; then
    KEEPER_EXE="${VAULT_DIR}/bin/xvault-miner"
elif [[ -x "${VAULT_DIR}/bin/xvault-miner.exe" ]]; then
    KEEPER_EXE="${VAULT_DIR}/bin/xvault-miner.exe"
elif [[ -x "${VAULT_DIR}/build/dist/xvault-miner" ]]; then
    KEEPER_EXE="${VAULT_DIR}/build/dist/xvault-miner"
fi

echo ""
echo "  ╔══════════════════════════════════════════════════════════════════╗"
echo "  ║         XELIS Vault - Wallet + Oracle Keeper Launcher          ║"
echo "  ╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Check prerequisites ──────────────────────────────────────────
echo "  [1/4] Checking prerequisites..."

if [[ ! -x "${WALLET_BIN}" ]]; then
    if [[ -x "${WALLET_BIN}.exe" ]]; then
        WALLET_BIN="${WALLET_BIN}.exe"
    else
        echo ""
        echo "    [!] ERROR: Wallet binary not found:"
        echo "        ${WALLET_BIN}"
        echo ""
        echo "    Please ensure xelis_wallet is in the bin directory and executable."
        echo "    chmod +x ${WALLET_BIN}"
        exit 1
    fi
fi
echo "        [OK] Wallet binary found"

KEEPER_AVAILABLE=0
if [[ -n "${KEEPER_EXE}" ]]; then
    KEEPER_AVAILABLE=1
    echo "        [OK] Keeper binary found: ${KEEPER_EXE}"
elif [[ -f "${KEEPER_PY}" ]]; then
    KEEPER_AVAILABLE=1
    echo "        [OK] Keeper Python script found"
else
    echo "        [!] Keeper not found - will start wallet only"
    echo "            Place xvault-miner in ${VAULT_DIR}/bin/ or run:"
    echo "            python3 ${KEEPER_PY}"
fi

# ── Step 2: Kill existing instances ──────────────────────────────────────
echo ""
echo "  [2/4] Cleaning up existing instances..."
pkill -f "xelis_wallet.*${RPC_PORT}" 2>/dev/null && echo "        Killed existing Wallet" || true
pkill -f "xvault-miner.*run-keeper" 2>/dev/null && echo "        Killed existing Keeper" || true
sleep 1
echo "        [OK] Cleanup done"

# ── Step 3: Start wallet ─────────────────────────────────────────────────
echo ""
echo "  [3/4] Starting wallet..."
echo "        RPC: ${RPC_URL}"
echo "        Address: (will be displayed after wallet starts)"

mkdir -p "${WALLET_DIR}"
mkdir -p "${LOG_DIR}"

nohup "${WALLET_BIN}" \
    --seed "${SEED}" \
    --network testnet \
    --wallet-path "${WALLET_DIR}" \
    --password testpass \
    --rpc-bind-address "127.0.0.1:${RPC_PORT}" \
    --rpc-username wallet \
    --rpc-password testpass \
    --daemon-address "${DAEMON_RPC}" \
    --logs-path "${LOG_DIR}/" \
    --disable-ascii-art \
    > "${LOG_DIR}/wallet.log" 2>&1 &

WALLET_PID=$!
echo "        Wallet PID: ${WALLET_PID}"

# ── Step 4: Wait for wallet and start keeper ─────────────────────────────
echo ""
echo "  [4/4] Waiting for wallet to be ready..."

WAITED=0
while true; do
    sleep 1
    WAITED=$((WAITED + 1))

    # Check if wallet process is still running
    if ! kill -0 "${WALLET_PID}" 2>/dev/null; then
        echo ""
        echo "    [!] ERROR: Wallet process exited unexpectedly."
        echo "        Check ${LOG_DIR}/wallet.log for errors."
        exit 1
    fi

    # Try to reach the RPC
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${RPC_URL}" 2>/dev/null || echo "000")
    if [[ "${HTTP_CODE}" == "200" || "${HTTP_CODE}" == "401" ]]; then
        echo "        [OK] Wallet ready (${WAITED}s)"
        break
    fi

    if [[ ${WAITED} -ge 90 ]]; then
        echo ""
        echo "    [!] WARNING: Wallet not responding after ${WAITED}s."
        echo "        The wallet process is running (PID ${WALLET_PID}) but RPC is not accessible."
        echo "        You can still use the wallet manually."
        break
    fi

    printf "        Waiting... (%ds)\r" "${WAITED}"
done

# Start keeper if available
if [[ "${KEEPER_AVAILABLE}" == "1" ]]; then
    echo ""
    echo "        Starting Oracle Keeper..."

    if [[ -n "${KEEPER_EXE}" ]]; then
        nohup "${KEEPER_EXE}" --run-keeper \
            --rpc "${DAEMON_RPC}" \
            --wallet-url "${RPC_URL}" \
            > "${LOG_DIR}/keeper.log" 2>&1 &
    else
        nohup python3 "${KEEPER_PY}" --run-keeper \
            --rpc "${DAEMON_RPC}" \
            --wallet-url "${RPC_URL}" \
            > "${LOG_DIR}/keeper.log" 2>&1 &
    fi

    KEEPER_PID=$!
    echo "        [OK] Keeper started (PID ${KEEPER_PID})"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════════════════════════════╗"
echo "  ║                        LAUNCH COMPLETE                         ║"
echo "  ╠══════════════════════════════════════════════════════════════════╣"
echo "  ║  Processes running:                                            ║"
echo "  ║    - Wallet  (PID ${WALLET_PID}, RPC on port ${RPC_PORT})                  ║"
if [[ "${KEEPER_AVAILABLE}" == "1" ]]; then
echo "  ║    - Keeper  (PID ${KEEPER_PID}, submits prices + heartbeats)          ║"
else
echo "  ║                                                                  ║"
echo "  ║  To start keeper manually:                                       ║"
echo "  ║    python3 ${VAULT_DIR}/src/scripts/xvault-miner.py              ║"
fi
echo "  ║                                                                  ║"
echo "  ║  Logs: ${LOG_DIR}/                                               ║"
echo "  ║                                                                  ║"
echo "  ║  To stop: pkill -f xelis_wallet; pkill -f xvault-miner          ║"
echo "  ╚══════════════════════════════════════════════════════════════════╝"
echo ""
