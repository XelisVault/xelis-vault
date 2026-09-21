#!/usr/bin/env python3
"""regen_chunk_table.py — regenerate the documented CHUNK TABLE comment in a
contract header from the real declaration order (same rule as
verify_chunk_ids.py). One-off maintenance tool for VaultLaunch v3."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from silex_parse import SilexFile
from verify_chunk_ids import format_table

TARGET = Path(sys.argv[1] if len(sys.argv) > 1 else
              Path(__file__).resolve().parent.parent /
              "contracts" / "launchpad" / "VaultLaunch.slx")

sf = SilexFile.parse(TARGET)
actual = [(str(i), f.name) for i, f in enumerate(sf.functions)]
# contract headers document the table as // comments (4-space indent inside)
new_table = "\n".join("//" + line for line in format_table(actual).splitlines())

lines = TARGET.read_text().splitlines()
marker = None
for i, text in enumerate(lines):
    if re.search(r"//.*?CHUNK TABLE", text, re.IGNORECASE):
        marker = i
        break
if marker is None:
    raise SystemExit("no CHUNK TABLE marker found")

# find the end of the old table block: walk comment lines after the marker,
# skipping separators; stop at the first prose line without N-name pairs
PAIR_RE = re.compile(r"(\d+)\s+([A-Za-z_]\w*)")
SEP_RE = re.compile(r"^//[\s\-=_]*$")
j = marker + 1
# skip the intro comment line(s) that contain no pairs and no prose? The v16
# table starts directly after the marker line with the table itself.
while j < len(lines):
    stripped = lines[j].strip()
    if not stripped.startswith("//"):
        break
    if SEP_RE.match(stripped):
        j += 1
        continue
    if PAIR_RE.findall(stripped[2:]):
        j += 1
        continue
    break

# the block between marker+1 and j is the old table (with separators)
old_block = lines[marker + 1:j]
# keep leading/trailing separator lines that frame the table
out = lines[:marker + 1] + old_block[:0] + new_table.splitlines() + lines[j - 1:]
# note: lines[j-1] is the last separator of the old block (or a pair line);
# safer: re-add a closing separator only if the old block ended with one
if old_block and SEP_RE.match(old_block[-1].strip()):
    out = lines[:marker + 1] + new_table.splitlines() + [old_block[-1]] + lines[j:]
else:
    out = lines[:marker + 1] + new_table.splitlines() + lines[j:]

TARGET.write_text("\n".join(out) + "\n")
print(f"regenerated chunk table for {TARGET.name}: {len(actual)} functions")
print(new_table)
