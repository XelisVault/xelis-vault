#!/bin/bash
set -euo pipefail

echo "=== XELIS Vault — Contract Deployment ==="
echo ""

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

DAEMON_URL=${DAEMON_URL:-"http://127.0.0.1:18081"}
WALLET_URL=${WALLET_URL:-"http://127.0.0.1:18082"}
SILEX_CLI=${SILEX_CLI:-"/private/tmp/xelis-vm/target/release/silex-cli"}
CONTRACTS_DIR=${CONTRACTS_DIR:-"$(cd "$(dirname "$0")/../contracts" && pwd)"}

echo -e "${BLUE}[INFO]${NC} Daemon: $DAEMON_URL"
echo -e "${BLUE}[INFO]${NC} Wallet: $WALLET_URL"
echo -e "${BLUE}[INFO]${NC} Silex CLI: $SILEX_CLI"
echo -e "${BLUE}[INFO]${NC} Contracts: $CONTRACTS_DIR"
echo ""

wallet_rpc() {
    local method="$1"
    local params="$2"
    curl -s -X POST "$WALLET_URL/json_rpc" \
        -H "Content-Type: application/json" \
        -u ":" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"$method\",\"params\":$params}"
}

daemon_rpc() {
    local method="$1"
    local params="$2"
    curl -s -X POST "$DAEMON_URL/json_rpc" \
        -H "Content-Type: application/json" \
        -u ":" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"$method\",\"params\":$params}"
}

# Compile .slx to hex module
compile() {
    local file="$1"
    "$SILEX_CLI" "$file" 2>/dev/null
}

# Deploy a contract, returns tx hash
deploy() {
    local module="$1"
    wallet_rpc "build_transaction" \
        "{\"deploy_contract\":{\"contract_version\":\"v0\",\"module\":\"$module\"},\"broadcast\":true}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['hash'])"
}

# Call init() entry (entry_id=0) on a contract, returns tx hash
call_init() {
    local contract="$1"
    wallet_rpc "build_transaction" \
        "{\"invoke_contract\":{\"contract\":\"$contract\",\"max_gas\":100000,\"entry_id\":0,\"parameters\":[],\"permission\":\"all\"},\"broadcast\":true}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['hash'])"
}

# Wait for mempool to drain (tx confirmed)
wait_mined() {
    while true; do
        local mempool=$(daemon_rpc "get_info" "{}" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['mempool_size'])")
        if [ "$mempool" = "0" ]; then
            break
        fi
        sleep 3
    done
}

# Get all deployed contract addresses (from latest to oldest)
get_deployed_contracts() {
    daemon_rpc "get_contracts" "{}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'result' in data:
    for c in data['result']:
        print(c)
"
}

XUSD_MODULE=$(compile "$CONTRACTS_DIR/xusd/xUSD.slx")
echo -e "${YELLOW}[1/4]${NC} Deploying xUSD Savings Stablecoin..."
XUSD_TX=$(deploy "$XUSD_MODULE")
echo -e "${BLUE}[TX]${NC} $XUSD_TX"
wait_mined
echo -e "${GREEN}[✓]${NC} xUSD deployed"
echo ""

ORACLE_MODULE=$(compile "$CONTRACTS_DIR/oracle/PriceOracle.slx")
echo -e "${YELLOW}[2/4]${NC} Deploying PriceOracle..."
ORACLE_TX=$(deploy "$ORACLE_MODULE")
echo -e "${BLUE}[TX]${NC} $ORACLE_TX"
wait_mined
echo -e "${GREEN}[✓]${NC} PriceOracle deployed"
echo ""

INTEREST_MODULE=$(compile "$CONTRACTS_DIR/interest/InterestRateModel.slx")
echo -e "${YELLOW}[3/4]${NC} Deploying InterestRateModel..."
INTEREST_TX=$(deploy "$INTEREST_MODULE")
echo -e "${BLUE}[TX]${NC} $INTEREST_TX"
wait_mined
echo -e "${GREEN}[✓]${NC} InterestRateModel deployed"
echo ""

VAULT_MODULE=$(compile "$CONTRACTS_DIR/vault/VaultEngine.slx")
echo -e "${YELLOW}[4/4]${NC} Deploying VaultEngine..."
VAULT_TX=$(deploy "$VAULT_MODULE")
echo -e "${BLUE}[TX]${NC} $VAULT_TX"
wait_mined
echo -e "${GREEN}[✓]${NC} VaultEngine deployed"
echo ""

echo "=== Contract Addresses ==="
CONTRACTS=$(get_deployed_contracts)
# Contract addresses are returned in order (oldest first in the response list)
# The first contract deployed is xUSD, second is Oracle, third is Interest, fourth is Vault
mapfile -t ADDR_ARRAY <<< "$CONTRACTS"
XUSD_CONTRACT="${ADDR_ARRAY[-4]:-}"
ORACLE_CONTRACT="${ADDR_ARRAY[-3]:-}"
INTEREST_CONTRACT="${ADDR_ARRAY[-2]:-}"
VAULT_CONTRACT="${ADDR_ARRAY[-1]:-}"
echo -e "${GREEN}xUSD:${NC}          $XUSD_CONTRACT"
echo -e "${GREEN}Oracle:${NC}        $ORACLE_CONTRACT"
echo -e "${GREEN}Interest:${NC}      $INTEREST_CONTRACT"
echo -e "${GREEN}VaultEngine:${NC}   $VAULT_CONTRACT"
echo ""

echo "=== Calling init() on each contract ==="
for addr in "$XUSD_CONTRACT" "$ORACLE_CONTRACT" "$INTEREST_CONTRACT" "$VAULT_CONTRACT"; do
    if [ -n "$addr" ]; then
        echo -e "${YELLOW}init()${NC} on $addr ..."
        call_init "$addr" > /dev/null 2>&1 || echo -e "${RED}[!]${NC} init() failed (might already be initialized)"
        wait_mined
    fi
done
echo -e "${GREEN}[✓]${NC} All init() calls completed"
echo ""

# Save to .env
cat > "$(dirname "$0")/../.env" << EOF
DAEMON_URL=$DAEMON_URL
WALLET_URL=$WALLET_URL
VAULT_CONTRACT=$VAULT_CONTRACT
XUSD_ASSET=$XUSD_CONTRACT
ORACLE_CONTRACT=$ORACLE_CONTRACT
INTEREST_CONTRACT=$INTEREST_CONTRACT
EOF

echo -e "${GREEN}Configuration saved to .env${NC}"
echo ""
echo "=== Deployment Complete ==="
echo "Next steps:"
echo "  1. Set XEL price in Oracle"
echo "  2. Configure VaultEngine with xUSD asset and Oracle/Interest addresses"
echo "  3. Test vault lifecycle (open, deposit, borrow, repay, liquidate)"
