#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

DAEMON_URL="http://127.0.0.1:18081"
WALLET_URL="http://127.0.0.1:18082"
WALLET_AUTH="wallet:testpass"
SILEX_CLI="/private/tmp/xelis-vm/target/release/silex-cli"
ROOT="/Users/adrien/opencode/xelis-vault"
CONTRACTS_DIR="$ROOT/contracts"
BUILD_DIR="$ROOT/build"

wallet_rpc() {
    curl -s -X POST "$WALLET_URL/json_rpc" \
        -H "Content-Type: application/json" \
        -u "$WALLET_AUTH" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"$1\",\"params\":$2}"
}

daemon_rpc() {
    curl -s -X POST "$DAEMON_URL/json_rpc" \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"$1\"}"
}

compile() {
    local name="$1"
    local src="$2"
    local hex=$("$SILEX_CLI" "$src" 2>/dev/null | tr -d '\n')
    if [ -n "$hex" ]; then
        echo "$hex" > "$BUILD_DIR/${name}.hex"
        echo -e "${GREEN}[✓]${NC} $name ($(wc -c < "$BUILD_DIR/${name}.hex")b)"
    else
        echo -e "${RED}[✗]${NC} $name"
        return 1
    fi
}

deploy() {
    local name="$1"
    local module="$2"
    local has_constructor="$3"
    local invoke_json=""

    if [ "$has_constructor" = "true" ]; then
        invoke_json=',"invoke":{"max_gas":100000,"deposits":{}}'
    fi

    local result=$(wallet_rpc "build_transaction" \
        "{\"deploy_contract\":{\"contract_version\":\"v0\",\"module\":\"$module\"$invoke_json},\"broadcast\":true}")

    local tx_hash=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('hash','ERROR'))" 2>/dev/null)
    if [ "$tx_hash" = "ERROR" ]; then
        local err=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',{}).get('message','unknown'))")
        echo -e "${RED}[✗]${NC} $name: $err"
        return 1
    fi
    echo -e "${GREEN}[✓]${NC} $name: $tx_hash"
    echo "$tx_hash"
}

wait_mined() {
    while true; do
        local info=$(daemon_rpc "get_info")
        local mempool=$(echo "$info" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('mempool_size',1))" 2>/dev/null)
        if [ "$mempool" = "0" ]; then break; fi
        sleep 3
    done
}

# Format: name:source:has_constructor
CONTRACTS=(
    "InterestRateModel:$CONTRACTS_DIR/interest/InterestRateModel.slx:false"
    "xUSD:$CONTRACTS_DIR/xusd/xUSD.slx:true"
    "PriceOracle:$CONTRACTS_DIR/oracle/PriceOracle.slx:true"
    "InsurancePool:$CONTRACTS_DIR/insurance/InsurancePool.slx:true"
    "PrivateInsurance:$CONTRACTS_DIR/insurance/PrivateInsurance.slx:true"
    "ComplianceModule:$CONTRACTS_DIR/compliance/ComplianceModule.slx:true"
    "AssetVault:$CONTRACTS_DIR/rwa/AssetVault.slx:true"
    "TreasuryVault:$CONTRACTS_DIR/treasury/TreasuryVault.slx:true"
    "RevenueShare:$CONTRACTS_DIR/treasury/RevenueShare.slx:true"
    "Payroll:$CONTRACTS_DIR/payroll/Payroll.slx:true"
    "FlashLoan:$CONTRACTS_DIR/flashloan/FlashLoan.slx:true"
    "LendingMarket:$CONTRACTS_DIR/lending/LendingMarket.slx:true"
    "PeerLoan:$CONTRACTS_DIR/lending/PeerLoan.slx:true"
    "SyndicatePool:$CONTRACTS_DIR/pools/SyndicatePool.slx:true"
    "SealedBidAuction:$CONTRACTS_DIR/auction/SealedBidAuction.slx:true"
    "SavingsRate:$CONTRACTS_DIR/savings/SavingsRate.slx:true"
    "VLT:$CONTRACTS_DIR/token/VLT.slx:true"
    "VaultEngine:$CONTRACTS_DIR/vault/VaultEngine.slx:true"
    "GovernanceVault:$CONTRACTS_DIR/governance/GovernanceVault.slx:true"
    "Timelock:$CONTRACTS_DIR/governance/Timelock.slx:true"
    "Governor:$CONTRACTS_DIR/governance/Governor.slx:true"
)

# Step 1: Compile all
echo -e "${YELLOW}=== Compiling ===${NC}"
for entry in "${CONTRACTS[@]}"; do
    IFS=':' read -r name src _ <<< "$entry"
    compile "$name" "$src"
done

# Step 2: Deploy all
echo ""
echo -e "${YELLOW}=== Deploying to testnet ===${NC}"

NAMES=()
TOTAL=${#CONTRACTS[@]}
IDX=1
for entry in "${CONTRACTS[@]}"; do
    IFS=':' read -r name src has_constr <<< "$entry"
    NAMES+=("$name")
    module=$(cat "$BUILD_DIR/${name}.hex")
    echo -e "${YELLOW}[$IDX/$TOTAL]${NC} Deploying $name..."
    deploy "$name" "$module" "$has_constr" || true
    wait_mined
    IDX=$((IDX + 1))
done

# Step 3: Get addresses
echo ""
echo -e "${YELLOW}=== Retrieving addresses ===${NC}"
sleep 5

ALL_CONTRACTS=$(daemon_rpc "get_contracts" "" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'result' in data:
    for c in data['result']:
        print(c)
")

# Filter our contracts (last N)
OUR_NAMES=("${NAMES[@]}")
mapfile -t ALL_ADDRS <<< "$ALL_CONTRACTS"
OUR_ADDRS=("${ALL_ADDRS[@]: -${#OUR_NAMES[@]}}")

echo ""
echo "=== Contract Addresses ==="
for i in "${!OUR_NAMES[@]}"; do
    echo -e "${GREEN}${OUR_NAMES[$i]}:${NC} ${OUR_ADDRS[$i]}"
done

# Save to JSON
python3 -c "
import json
names = [${OUR_NAMES[@]}]
addrs = [${OUR_ADDRS[@]}]
print('names:', names)
print('addrs:', addrs)
registry = {}
for n, a in zip(names, addrs):
    registry[n] = a
with open('$BUILD_DIR/testnet_registry.json', 'w') as f:
    json.dump(registry, f, indent=2)
print('Saved to build/testnet_registry.json')
"

echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
