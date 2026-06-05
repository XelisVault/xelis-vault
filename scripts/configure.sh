#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
DAEMON_URL="http://127.0.0.1:18081"
WALLET_URL="http://127.0.0.1:18082"
WALLET_AUTH="wallet:testpass"
REGISTRY="/Users/adrien/opencode/xelis-vault/build/testnet_registry.json"

wallet_rpc() { curl -s -X POST "$WALLET_URL/json_rpc" -H "Content-Type: application/json" -u "$WALLET_AUTH" -d "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"$1\",\"params\":$2}"; }
daemon_rpc() { curl -s -X POST "$DAEMON_URL/json_rpc" -H "Content-Type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"$1\"}"; }

wait_mined() {
    while true; do
        local mempool=$(daemon_rpc "get_info" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('mempool_size',1))")
        if [ "$mempool" = "0" ]; then break; fi; sleep 3
    done
}

invoke() {
    local contract="$1" entry_id="$2" params="$3" deposits="$4" label="$5"
    if [ -z "$deposits" ] || [ "$deposits" = "null" ]; then deposits="{}"; fi
    local result=$(wallet_rpc "build_transaction" "{\"invoke_contract\":{\"contract\":\"$contract\",\"max_gas\":200000,\"entry_id\":$entry_id,\"parameters\":$params,\"deposits\":$deposits,\"permission\":\"all\"},\"broadcast\":true}")
    local tx_hash=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('hash','ERROR'))")
    if [ "$tx_hash" = "ERROR" ]; then
        local err=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',{}).get('message','unknown'))")
        echo -e "${RED}[✗]${NC} $label: $err"; return 1
    fi
    echo -e "${GREEN}[✓]${NC} $label: $tx_hash"
    wait_mined; echo "$tx_hash"
}

contract() { python3 -c "import json; print(json.load(open('$REGISTRY'))['$1'])"; }

ZERO_HASH="0000000000000000000000000000000000000000000000000000000000000000"
XUSD_ASSET="f03625136c1274265c3eea5e8b85c9714b9380d93d8c6ef6aa658ff4c4a14731"
VLT_ASSET="d44cca8930e9678a8eabe386e43493428589b6593998725f86b0c2dc6a8ad2cd"
GOV_VAULT_ADDR="xet:czr9q8k5xlzqdptq7n2vapyjfduldts6tw3e6apl99vknzvmu4zsq8z9j8v"

BALANCE=$(wallet_rpc "get_balance" "{}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',0))")
echo "Wallet balance: $((BALANCE / 1000000000)) XEL"
echo -e "${YELLOW}=== Configuring Contracts ===${NC}"

# 1. xUSD.create_asset() — done
echo -e "${BLUE}[1]${NC} xUSD.create_asset() — done (asset: $XUSD_ASSET)"

# 2. PriceOracle.propose_price(10000000)
echo -e "${BLUE}[2]${NC} PriceOracle.propose_price(10000000)"
invoke "$(contract PriceOracle)" 2 "[{\"type\":\"primitive\",\"value\":{\"type\":\"u64\",\"value\":\"10000000\"}}]" "null" "Propose XEL price \$0.10"

# 3. PriceOracle.execute_price() — needs 720 block timelock
echo -e "${BLUE}[3]${NC} PriceOracle.execute_price()"
invoke "$(contract PriceOracle)" 3 "[]" "null" "Execute price"

# 4. VaultEngine.set_oracle_contract (entry 17)
echo -e "${BLUE}[4]${NC} VaultEngine.set_oracle_contract()"
invoke "$(contract VaultEngine)" 17 "[{\"type\":\"primitive\",\"value\":{\"type\":\"opaque\",\"value\":{\"type\":\"Hash\",\"value\":\"$(contract PriceOracle)\"}}}]" "null" "Set oracle"

# 5. VaultEngine.set_xusd_contract (entry 18)
echo -e "${BLUE}[5]${NC} VaultEngine.set_xusd_contract()"
invoke "$(contract VaultEngine)" 18 "[{\"type\":\"primitive\",\"value\":{\"type\":\"opaque\",\"value\":{\"type\":\"Hash\",\"value\":\"$(contract xUSD)\"}}}]" "null" "Set xUSD contract"

# 6. VaultEngine.set_xusd_asset (entry 19)
echo -e "${BLUE}[6]${NC} VaultEngine.set_xusd_asset()"
invoke "$(contract VaultEngine)" 19 "[{\"type\":\"primitive\",\"value\":{\"type\":\"opaque\",\"value\":{\"type\":\"Hash\",\"value\":\"$XUSD_ASSET\"}}}]" "null" "Set xUSD asset"

# 7. VLT.create_asset(rewards_vault) — done on VLT v3
echo -e "${BLUE}[7]${NC} VLT.create_asset() — done (asset: $VLT_ASSET)"

# 8. GovernanceVault.set_vlt_contract (entry 11)
echo -e "${BLUE}[8]${NC} GovernanceVault.set_vlt_contract()"
invoke "$(contract GovernanceVault)" 11 "[{\"type\":\"primitive\",\"value\":{\"type\":\"opaque\",\"value\":{\"type\":\"Hash\",\"value\":\"$(contract VLT)\"}}}]" "null" "Set VLT contract"

# 9. GovernanceVault.set_vlt_asset (entry 12)
echo -e "${BLUE}[9]${NC} GovernanceVault.set_vlt_asset()"
invoke "$(contract GovernanceVault)" 12 "[{\"type\":\"primitive\",\"value\":{\"type\":\"opaque\",\"value\":{\"type\":\"Hash\",\"value\":\"$VLT_ASSET\"}}}]" "null" "Set VLT asset"

echo ""
echo -e "${GREEN}=== Configuration Done ===${NC}"
