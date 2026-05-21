# VM Bug Reproducers — XELIS Vault
## Copy-paste these to reproduce every bug

### Setup
```bash
# Start devnet daemon + wallet (or use testnet)
docker compose -f contrib/devnet/docker-compose.yml up -d
```

### Bug 1: Storage store drops after load
```bash
# Deploy
curl -X POST http://127.0.0.1:18082/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"deploy_contract","params":{"name":"Bug1","path":"tests/bugs/01_store_drops_after_load.slx"}}'

# Call entry 1 (bug) — SHOULD return 3, ACTUALLY returns 0
curl -X POST http://127.0.0.1:18082/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"call_contract","params":{"contract":"CONTRACT_HASH","entry":1,"params":[]}}'

# Call entry 2 (expected with dummy topoheight) — returns 3
curl -X POST http://127.0.0.1:18082/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"call_contract","params":{"contract":"CONTRACT_HASH","entry":2,"params":[]}}'
```
**Bug**: `store(B) → load(A) → store(C)` → C is dropped. Returns 0 instead of 3.
**Workaround**: Insert `get_current_topoheight()` between load and next store.

---

### Bug 2: get_current_topoheight() before first store drops it
```bash
# Deploy
curl -X POST http://127.0.0.1:18082/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"deploy_contract","params":{"name":"Bug2","path":"tests/bugs/02_topo_before_store_drops.slx"}}'

# Call entry 1 (bug) — SHOULD return 42, ACTUALLY returns 0
# Call entry 2 (expected with dummy store first) — returns 42
```
**Bug**: `get_current_topoheight()` as first operation breaks subsequent `store()`.
**Workaround**: Do a dummy `store(key, 0u64)` before calling topoheight.

---

### Bug 3: get_deposit_for_asset() before store drops it
```bash
# Deploy
curl -X POST http://127.0.0.1:18082/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"deploy_contract","params":{"name":"Bug3","path":"tests/bugs/03_deposit_before_store_drops.slx"}}'

# Invoke with 1 XEL deposit, call entry 1 (bug):
curl -X POST http://127.0.0.1:18082/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"call_contract","params":{"contract":"CONTRACT_HASH","entry":1,"params":[],"deposits":[{"asset":null,"amount":100000000}]}}'

# SHOULD return 42, ACTUALLY returns 0

# Call entry 2 (expected) — returns 42
```
**Bug**: `get_deposit_for_asset()` as first operation breaks subsequent `store()`.
**Workaround**: Do a dummy `store(key, 0u64)` before reading deposits.

---

### Bug 4: to_hex() / to_string() broken
```bash
# Deploy
curl -X POST http://127.0.0.1:18082/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"deploy_contract","params":{"name":"Bug4","path":"tests/bugs/04_tohex_broken.slx"}}'

# Call entry 1 — stores under corrupted key
# Check storage for "k" prefix — key is garbage, not hex
```
**Bug**: `Hash.to_hex()` and `Address.to_string()` return empty/garbage strings.
**Workaround**: Only `u64.to_string(10u32)` works for key generation.

---

### Bug 5: Entry return values always 0
```bash
# Deploy
curl -X POST http://127.0.0.1:18082/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"deploy_contract","params":{"name":"Bug5","path":"tests/bugs/05_return_always_zero.slx"}}'

# Call entry 1 (bug_param) with x=42:
curl -X POST http://127.0.0.1:18082/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"call_contract","params":{"contract":"CONTRACT_HASH","entry":1,"params":[42]}}'

# SHOULD return 42, ACTUALLY returns 0

# Call entry 2 (bug_stored) — returns 0 instead of 42
# Call entry 3 (bug_computed) — returns 0 instead of 42
# Call entry 4 (works_constant) — returns 42 correctly (only literal constants work)
```
**Bug**: `return x;` returns 0 for any non-literal value (params, stored values, computed).
**Workaround**: Always `return 0;` from entry functions.

---

### Bug 6: require/expect strings limited to [a-zA-Z0-9]
```bash
# Deploy
curl -X POST http://127.0.0.1:18082/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"deploy_contract","params":{"name":"Bug6","path":"tests/bugs/06_require_string_validation.slx"}}'

# Call entry 1 (bug with space "v is not 1") — EXECUTION FAILS with unclear error
# Call entry 2 (bug2 with exclamation "not found!") — EXECUTION FAILS
# Call entry 3 (works with alphanumeric "vnot1") — WORKS
```
**Bug**: `require()` and `.expect()` strings must be `^[a-zA-Z0-9]+$`. Any special char or space causes execution failure. Not documented.

---

### Bug 7: mint() built-in unavailable
```bash
# Try to compile:
silex compile tests/bugs/07_mint_unavailable.slx
# Expected output: ERROR — "unknown function: mint"
```
**Bug**: The `mint(amount, asset_hash)` built-in for creating native confidential assets is not exposed in Silex. Cannot create new asset types from contracts.

---

### Bonus: Cross-contract call array indexing
```bash
# Deploy once
silex compile tests/bugs/08_cross_contract_array_index.slx
# Deploy to devnet, then call call_test with self-reference
```
**Bug**: `Contract.call()` returns `any[]`, but `result[0]` may return "invalid array call".
