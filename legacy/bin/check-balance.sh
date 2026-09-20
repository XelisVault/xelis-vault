#!/usr/bin/env bash
# ============================================================================
#   XELIS Vault - Balance Checker (Unix/Linux/macOS)
# ============================================================================
set -euo pipefail

RPC_URL="http://127.0.0.1:18082/json_rpc"
ADDR="YOUR_WALLET_ADDRESS_HERE"
VLT="3f1f9a3c0a90a0a548670a069e8edad5c0c20914b20b289426b2857c6715f58f"

echo ""
echo "  ╔══════════════════════════════════════════════════════════════════╗"
echo "  ║           XELIS Vault - Wallet Balance Check                   ║"
echo "  ╚══════════════════════════════════════════════════════════════════╝"
echo ""

echo "  [1/4] Testing RPC connectivity..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${RPC_URL}" 2>/dev/null || echo "000")
if [[ "${HTTP_CODE}" == "000" ]]; then
    echo "    [!] ERROR: Wallet RPC not reachable at ${RPC_URL}"
    echo "    Start the wallet first: ./bin/start-wallet.sh"
    exit 1
fi
echo "    [OK] HTTP ${HTTP_CODE}"

echo ""
echo "  [2/4] Wallet address..."
RESP=$(curl -s -X POST -H "Content-Type: application/json" \
    -u wallet:testpass \
    -d '{"jsonrpc":"2.0","id":1,"method":"get_address","params":{}}' \
    "${RPC_URL}" 2>/dev/null || echo "{}")
echo "    ${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('    ' + d.get('result',{}).get('address','error'))" 2>/dev/null || echo "    ${RESP}"

echo ""
echo "  [3/4] XEL balance..."
RESP=$(curl -s -X POST -H "Content-Type: application/json" \
    -u wallet:testpass \
    -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"get_balance\",\"params\":{\"address\":\"${ADDR}\"}}" \
    "${RPC_URL}" 2>/dev/null || echo "{}")
echo "    ${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); b=d.get('result',{}).get('balance',0); print(f'    {b/1e8:.8f} XEL')" 2>/dev/null || echo "    ${RESP}"

echo ""
echo "  [4/4] VLT balance..."
RESP=$(curl -s -X POST -H "Content-Type: application/json" \
    -u wallet:testpass \
    -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"get_balance\",\"params\":{\"address\":\"${ADDR}\",\"asset\":\"${VLT}\"}}" \
    "${RPC_URL}" 2>/dev/null || echo "{}")
echo "    ${RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); b=d.get('result',{}).get('balance',0); print(f'    {b/1e8:.8f} VLT')" 2>/dev/null || echo "    ${RESP}"

echo ""
echo "  ══════════════════════════════════════════════════════════════════"
echo ""

