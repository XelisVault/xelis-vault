# build/ — compiled contracts (v12.1)

This directory holds the **compiled bytecode** (`deploy_<Name>.hex`, full
ContractModule: version byte `01` + V1 module, deploy as-is), the
**ABI json** (`deploy_<Name>.abi.json`) and the **chunk maps**
(`chunkmap_<Name>.txt`) for all 51 contracts.

- All 51/51 contracts compile — regenerate with `scripts/compile_all.py`
  (all contracts or a subset: `python3 scripts/compile_all.py
  AirdropTracker VaultChat`).
- `chunkmap_<Name>.txt` is the authoritative source for entry/chunk ids:
  `chunk N: <Access> <name> (M instructions)`.
- `../docs/entry_chunk_ids.json` is the machine-readable version
  (name + kind + instructions per chunk).
- **Byte-for-byte canonical**: the committed artifacts were rebuilt with a
  compiler wrapping the official `xelis-vm` **v1.3.0** crates
  (`silex-lexer/parser/compiler` + `build_environment::<MockStorageProvider>
  (ContractVersion::V1)` from `xelis_common`) and verified identical to the
  canonical Windows compiler output. Compilation is deterministic.

## The toolchain

`scripts/compile_all.py` looks for the `xelis_compile_tool` binary in:

1. `$XELIS_COMPILE_TOOL`
2. `/home/z/xelis-compile-tool/target/release/xelis_compile_tool`
3. `<repo>/tools/xelis_compile_tool`
4. `<repo parent>/xelis-compile-tool/target/release/xelis_compile_tool`

To build the tool once:

```bash
git clone --branch v1.3.0 https://github.com/xelis-project/xelis-vm
git clone https://github.com/xelis-project/xelis-blockchain
# cargo project:
#   [dependencies] xelis_common = { path = "../xelis-blockchain/xelis_common" }
#   silex-bytecode / silex-compiler / silex-lexer / silex-parser (path to
#   ../xelis-vm/<crate>)
#   [patch."https://github.com/xelis-project/xelis-vm"] <all silex crates as
#   path deps>   <- REQUIRED so xelis_common resolves to the same crates
# main.rs: Lexer -> Parser::with(tokens, &env) -> Compiler::new(
#     &program, env.environment()).with_enforce_public_parameters(true)
#   -> Module -> ContractModule { V1, module } -> Serializer::write -> hex
# chunk map + ABI printed/written from the module + function mapper.
cargo build --release
export XELIS_COMPILE_TOOL=$PWD/target/release/xelis_compile_tool
```

## Append-only guarantee

Silex chunk ids are the compiled index of each function. `compile_all.py`
mechanically verifies, after every recompile, that every previously existing
chunk keeps its **position, kind and name** — new functions must be appended
at the end of the contract source. Signatures of existing entries may be
extended only when every caller is updated in the same commit (v12.1 did
this once: `import_user_state`, and `finalize_migration`).

⚠️ The .hex files in this directory were compiled from the current sources;
before deploying on testnet, the owner may recompile with their own
`xelis_compile_tool` — outputs are byte-for-byte identical (deterministic
compiler), but always cross-check the chunk map stderr output.
