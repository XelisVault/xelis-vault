#!/bin/bash
# Batch deploy all 20 contracts to devnet
# Each deploy takes ~30-60s for range proofs, total ~10-20min

set -e

WALLET="http://localhost:18082/json_rpc"
AUTH="-u :testpassword"
BUILD="/Users/adrien/opencode/xelis-vault/build"
DAEMON_LOG="/Users/adrien/opencode/xelis-vault/data/daemon.log"
REGISTRY="$BUILD/registry.json"

CONTRACTS=(
  PriceOracle xUSD InterestRateModel VaultEngine FlashLoan
  InsurancePool PrivateInsurance LendingMarket PeerLoan
  SyndicatePool SealedBidAuction AssetVault TreasuryVault
  RevenueShare Payroll SavingsRate ComplianceModule VLT GovernanceVault Timelock
)

# Check wallet
echo "Checking wallet..."
BALANCE=$(curl -s $AUTH "$WALLET" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"get_balance","params":{}}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result','?'))")
echo "Balance: $BALANCE"

# Pre-read all hex files to avoid filesystem issues
declare -A HEXES
for c in "${CONTRACTS[@]}"; do
  HEXES[$c]=$(cat "$BUILD/$c.hex")
done

# Deploy each
for c in "${CONTRACTS[@]}"; do
  echo ""
  echo "=== Deploying $c ==="
  PAYLOAD=$(python3 -c "
import json
print(json.dumps({
  'jsonrpc': '2.0', 'id': '1',
  'method': 'build_transaction',
  'params': {
    'deploy_contract': {
      'module': '''${HEXES[$c]}''',
      'invoke': {'max_gas': 1000000}
    },
    'broadcast': True
  }
}))")
  
  RESULT=$(curl -s --max-time 600 $AUTH "$WALLET" -H "Content-Type: application/json" -d "$PAYLOAD" 2>&1)
  
  if echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'result' in d else 1)" 2>/dev/null; then
    echo "OK"
  else
    echo "FAIL: $(echo "$RESULT" | head -c 200)"
  fi
  
  sleep 1
done

echo ""
echo "=== All deploys attempted ==="
echo "Waiting 60s for mining..."
sleep 60

# Extract addresses from daemon log
echo ""
echo "=== Contract Addresses ==="
echo "{" > "$REGISTRY"
FIRST=true
for c in "${CONTRACTS[@]}"; do
  # Find the contract address from deploy log
  # Format: "Invoke contract HASH from HASH"
  ADDR=$(grep "Invoke contract" "$DAEMON_LOG" | grep -oP 'Invoke contract \K([0-9a-f]{64})' | tail -1)
  if [ -n "$ADDR" ]; then
    if [ "$FIRST" = true ]; then
      FIRST=false
    else
      echo "," >> "$REGISTRY"
    fi
    echo -n "  \"$c\": \"$ADDR\"" | tee -a "$REGISTRY"
    echo ""
  fi
done
echo "" >> "$REGISTRY"
echo "}" >> "$REGISTRY"
echo "Registry saved to $REGISTRY"
