#!/bin/bash
# Fixed deploy script for 9 missing core vault contracts
set -euo pipefail

WALLET="http://127.0.0.1:18082/json_rpc"
DAEMON="http://127.0.0.1:18081/json_rpc"
AUTH="-u :testnet_vault_2026"
BUILD="/Users/adrien/opencode/xelis-vault/build"

rpc_wallet() { curl -s --max-time 600 $AUTH "$WALLET" -H "Content-Type: application/json" -d "$(cat)"; }
rpc_daemon() { curl -s --max-time 30 "$DAEMON" -H "Content-Type: application/json" -d "$(cat)"; }

wait_tx_confirmed() {
  local tx=$1
  local max=${2:-300}
  for i in $(seq 1 $max); do
    local r=$(echo '{"jsonrpc":"2.0","id":"1","method":"get_transaction","params":["'"$tx"'"]}' | rpc_daemon)
    local blk=$(echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin).get('result',{}); print(len(d.get('blocks',[])) if isinstance(d.get('blocks'),list) else 0)")
    local topo=$(echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin).get('result',{}); print(d.get('topoheight','null'))")
    if [ "$blk" -gt 0 ] && [ "$topo" != "null" ]; then
      echo "  ✅ block=$blk topo=$topo (${i}s)"
      return 0
    fi
    if [ "$blk" -gt 0 ] && [ "$topo" = "null" ]; then
      : # in block but not ordered yet
    fi
    sleep 1
  done
  echo "  ❌ TIMEOUT (${max}s)"
  return 1
}

deploy_no_ctor() {
  local name=$1
  local hex=$(cat "$BUILD/$name.hex")
  local r=$(echo '{"jsonrpc":"2.0","id":"1","method":"build_transaction","params":{"deploy_contract":{"module":"'"$hex"'"},"broadcast":true}}' | rpc_wallet)
  local err=$(echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',{}).get('message',''))")
  if [ -n "$err" ]; then echo "ERROR:$err"; return 1; fi
  echo "$r" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['hash'])"
}

deploy_with_ctor() {
  local name=$1
  local hex=$(cat "$BUILD/$name.hex")
  local r=$(echo '{"jsonrpc":"2.0","id":"1","method":"build_transaction","params":{"deploy_contract":{"module":"'"$hex"'","invoke":{"max_gas":1000000}},"broadcast":true}}' | rpc_wallet)
  local err=$(echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',{}).get('message',''))")
  if [ -n "$err" ]; then echo "ERROR:$err"; return 1; fi
  echo "$r" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['hash'])"
}

invoke_contract() {
  local label=$1; shift
  local contract=$1; shift
  local entry=$1; shift
  local params=${1:-[]}; shift || true
  local deposits=${1:-}; shift || true

  local payload='{"contract":"'"$contract"'","entry_id":'"$entry"',"parameters":'"$params"',"max_gas":500000,"permission":"none"'
  if [ -n "$deposits" ]; then payload+=',"deposits":'"$deposits"; fi
  payload+='}'

  local r=$(echo '{"jsonrpc":"2.0","id":"1","method":"build_transaction","params":{"invoke_contract":'"$payload"',"broadcast":true}}' | rpc_wallet)
  local err=$(echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',{}).get('message',''))")
  if [ -n "$err" ]; then echo "ERROR:$err"; return 1; fi
  local tx=$(echo "$r" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['hash'])")
  echo "$tx"
}

wait_tx_in_block() {
  local tx=$1
  local max=${2:-60}
  for i in $(seq 1 $max); do
    local r=$(echo '{"jsonrpc":"2.0","id":"1","method":"get_transaction","params":["'"$tx"'"]}' | rpc_daemon)
    local blk=$(echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin).get('result',{}); print(len(d.get('blocks',[])) if isinstance(d.get('blocks'),list) else 0)")
    if [ "$blk" -gt 0 ]; then
      echo " ✅ block=${blk} (${i}s)"
      return 0
    fi
    sleep 1
  done
  echo " ⚠️  no block yet"
  return 0
}

echo "=========================================="
echo " Deploy 9 missing contracts"
echo "=========================================="

REGS="{}"

# 1. InterestRateModel (no constructor)
echo -n "InterestRateModel... "
IRM=$(deploy_no_ctor InterestRateModel)
echo "$IRM"
wait_tx_in_block "$IRM" 90
REGS=$(echo "$REGS" | python3 -c "import sys,json; r=json.load(sys.stdin); r['InterestRateModel']={'tx_hash':'$IRM'}; print(json.dumps(r))")

# 2. PriceOracle (no constructor) + init()
echo -n "PriceOracle... "
PO=$(deploy_no_ctor PriceOracle)
echo "$PO"
wait_tx_in_block "$PO" 90
REGS=$(echo "$REGS" | python3 -c "import sys,json; r=json.load(sys.stdin); r['PriceOracle']={'tx_hash':'$PO'}; print(json.dumps(r))")
echo -n "PriceOracle.init()... "
POINIT=$(invoke_contract "init" "$PO" 0 '[]' '')
echo "$POINIT"
wait_tx_in_block "$POINIT" 90

# 3. xUSD (no constructor) + init()
echo -n "xUSD... "
XUSD=$(deploy_no_ctor xUSD)
echo "$XUSD"
wait_tx_in_block "$XUSD" 90
REGS=$(echo "$REGS" | python3 -c "import sys,json; r=json.load(sys.stdin); r['xUSD']={'tx_hash':'$XUSD'}; print(json.dumps(r))")
echo -n "xUSD.init()... "
XUSDINIT=$(invoke_contract "init" "$XUSD" 0 '[]' '')
echo "$XUSDINIT"
wait_tx_in_block "$XUSDINIT" 90

# 4-9. Constructor contracts
echo ""
echo "--- Constructor contracts ---"
for name in VLT ComplianceModule Timelock FlashLoan AssetVault SyndicatePool; do
  echo -n "$name... "
  H=$(deploy_with_ctor "$name")
  echo "$H"
  wait_tx_in_block "$H" 90
  REGS=$(echo "$REGS" | python3 -c "import sys,json; r=json.load(sys.stdin); r['$name']={'tx_hash':'$H'}; print(json.dumps(r))")
done

echo ""
echo "=========================================="
echo " Phase 2: Wait for ordering & wire"
echo "=========================================="

# Wait for all deploy TXs to get topo (ordered)
echo "Waiting for all TXs to be ordered (up to 10min)..."
python3 -c "
import json, time, urllib.request
DAEMON = 'http://127.0.0.1:18081/json_rpc'
reg = json.loads('$REGS')
txs = [info['tx_hash'] for info in reg.values()]
print(f'Checking {len(txs)} TXs...')
for _ in range(600):
    all_ordered = True
    for tx in txs:
        p = json.dumps({'jsonrpc':'2.0','id':'1','method':'get_transaction','params':[tx]}).encode()
        r = urllib.request.Request(DAEMON, data=p, headers={'Content-Type':'application/json'})
        d = json.loads(urllib.request.urlopen(r, timeout=10).read())
        res = d.get('result', {})
        topo = res.get('topoheight')
        blk = len(res.get('blocks', []))
        if topo is None:
            all_ordered = False
    if all_ordered:
        print('All TXs ordered!')
        break
    time.sleep(5)
else:
    print('TIMEOUT waiting for ordering')
" 2>&1

echo ""
echo "=========================================="
echo " Phase 3: Wiring"
echo "=========================================="

VE="46c72cb50a9b5d4123c99d08e2320afdc30f32496da145f91da8052d23c723d8"
XEL_ASSET="0000000000000000000000000000000000000000000000000000000000000000"

echo "1/5: xUSD.create_asset() with 1 XEL deposit..."
TX_CA=$(invoke_contract "create_asset" "$XUSD" 1 '[]' '{"'"$XEL_ASSET"'":{"amount":100000000}}')
echo "  $TX_CA"
wait_tx_in_block "$TX_CA" 120

echo "2/5: xUSD.get_asset_hash()..."
TX_AH=$(invoke_contract "get_asset_hash" "$XUSD" 5 '[]' '')
echo "  $TX_AH"
wait_tx_in_block "$TX_AH" 120

echo "3/5: PriceOracle.propose_price(50000000)..."
TX_PP=$(invoke_contract "propose_price" "$PO" 1 '[{"type":"primitive","value":{"type":"u64","value":"50000000"}}]' '')
echo "  $TX_PP"
wait_tx_in_block "$TX_PP" 120

echo "4/5: VaultEngine.set_oracle_contract(PO)..."
TX_SO=$(invoke_contract "set_oracle" "$VE" 8 '[{"type":"primitive","value":{"type":"hash","value":"'"$PO"'"}}]' '')
echo "  $TX_SO"
wait_tx_in_block "$TX_SO" 120

echo "5/5: VaultEngine.set_xusd_contract(xUSD)..."
TX_SX=$(invoke_contract "set_xusd" "$VE" 9 '[{"type":"primitive","value":{"type":"hash","value":"'"$XUSD"'"}}]' '')
echo "  $TX_SX"
wait_tx_in_block "$TX_SX" 120

echo ""
echo "=========================================="
echo " Saving registry"
echo "=========================================="
echo "$REGS" > "$BUILD/registry_core.json"
echo "Saved to $BUILD/registry_core.json"
echo "Done!"
