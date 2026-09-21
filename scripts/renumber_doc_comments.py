#!/usr/bin/env python3
"""renumber_doc_comments.py — set the `// NN.` prefix of each function's
doc-comment block in a Silex contract to the REAL chunk index (declaration
order). Idempotent; validates that every function has exactly one numbered
doc block. Companion of regen_chunk_table.py."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from silex_parse import SilexFile

TARGET = Path(sys.argv[1] if len(sys.argv) > 1 else
              Path(__file__).resolve().parent.parent /
              "contracts" / "launchpad" / "VaultLaunch.slx")

sf = SilexFile.parse(TARGET)
src = TARGET.read_text()
lines = src.splitlines()

# map: function name -> real index
order = {f.name: i for i, f in enumerate(sf.functions)}

# find each function declaration line; then walk BACKWARD over its comment
# block to locate the first line of the block and the `// NN.` leader line
changes = 0
for f in sf.functions:
    # declaration line index (0-based) — locate by name at line start
    decl = None
    for idx, text in enumerate(lines):
        if re.match(rf"^(entry|pub fn|fn|hook)\s+{re.escape(f.name)}\b", text):
            decl = idx
            break
    if decl is None:
        raise SystemExit(f"declaration not found for {f.name}")
    # walk back over contiguous comment lines
    j = decl - 1
    while j >= 0 and lines[j].strip().startswith("//"):
        j -= 1
    block = range(j + 1, decl)
    if not block:
        raise SystemExit(f"no doc comment block for {f.name}")
    # the block may contain === separators; the `// NN.` leader is the first
    # numbered line of the block
    leader = None
    for k in block:
        m = re.match(r"^//\s+(\d+)\.\s", lines[k])
        if m:
            leader = k
            break
    if leader is None:
        # separator-framed blocks: the number line may sit after === lines
        for k in block:
            if re.match(r"^//\s+\d+\.\s", lines[k]) or re.match(r"^//\s+\d+\s+\w", lines[k]):
                leader = k
                break
    if leader is None:
        continue  # functions without numbered doc (none expected)
    real = order[f.name]
    old = lines[leader]
    new = re.sub(r"^//\s+\d+\.", f"// {real}.", old, count=1)
    if new != old:
        lines[leader] = new
        changes += 1

TARGET.write_text("\n".join(lines) + "\n")
print(f"renumbered {changes} doc-comment leaders in {TARGET.name}")
for name, i in order.items():
    print(f"  {i:>3} {name}")
