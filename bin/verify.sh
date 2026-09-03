#!/usr/bin/env bash
# ============================================================================
#   XELIS Vault - System Verification (Unix/Linux/macOS)
# ============================================================================
set -euo pipefail

VAULT_DIR="${HOME}/.xelis-vault"
RPC_URL="http://127.0.0.1:18082/json_rpc"

echo ""
echo "  ╔══════════════════════════════════════════════════════════════════╗"
echo "  ║           XELIS Vault - System Verification                    ║"
echo "  ╚══════════════════════════════════════════════════════════════════╝"
echo ""

echo "  [1/5] Configuration..."
if [[ -f "${VAULT_DIR}/config/config.json" ]]; then
    echo "        [OK] config.json found"
    python3 -c "import json; d=json.load(open('${VAULT_DIR}/config/config.json')); [print(f'        {k}: {v}') for k,v in d.items() if k not in ('contracts','seed')]" 2>/dev/null || cat "${VAULT_DIR}/config/config.json"
else
    echo "        [!] config.json not found"
fi

echo ""
echo "  [2/5] Wallet process..."
if pgrep -f "xelis_wallet" > /dev/null 2>&1; then
    echo "        [OK] Wallet: RUNNING"
    ss -tlnp 2>/dev/null | grep "18082" || netstat -tlnp 2>/dev/null | grep "18082" || echo "        (port 18082 check requires ss/netstat)"
else
    echo "        [!] Wallet: STOPPED"
fi

echo ""
echo "  [3/5] Wallet RPC address..."
RESP=$(curl -s -X POST -H "Content-Type: application/json" \
    -u wallet:testpass \
    -d '{"jsonrpc":"2.0","id":1,"method":"get_address","params":{}}' \
    "${RPC_URL}" 2>/dev/null || echo "{}")
ADDR=$(echo "${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('address','unreachable'))" 2>/dev/null || echo "unreachable")
echo "        ${ADDR}"

echo ""
echo "  [4/5] Balances..."
ADDR_FULL="YOUR_WALLET_ADDRESS_HERE"
VLT_ASSET="3f1f9a3c0a90a0a548670a069e8edad5c0c20914b20b289426b2857c6715f58f"

RESP=$(curl -s -X POST -H "Content-Type: application/json" \
    -u wallet:testpass \
    -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"get_balance\",\"params\":{\"address\":\"${ADDR_FULL}\"}}" \
    "${RPC_URL}" 2>/dev/null || echo "{}")
XEL=$(echo "${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d.get(\"result\",{}).get(\"balance\",0)/1e8:.8f}')" 2>/dev/null || echo "error")
echo "        XEL: ${XEL}"

RESP=$(curl -s -X POST -H "Content-Type: application/json" \
    -u wallet:testpass \
    -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"get_balance\",\"params\":{\"address\":\"${ADDR_FULL}\",\"asset\":\"${VLT_ASSET}\"}}" \
    "${RPC_URL}" 2>/dev/null || echo "{}")
VLT=$(echo "${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d.get(\"result\",{}).get(\"balance\",0)/1e8:.8f}')" 2>/dev/null || echo "error")
echo "        VLT: ${VLT}"

echo ""
echo "  [5/5] Miner registration..."
echo "        (requires 1000 VLT minimum)"
echo ""

echo "  ══════════════════════════════════════════════════════════════════"
echo "  Verification complete."
echo ""

