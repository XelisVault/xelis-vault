#!/usr/bin/env python3
"""silex_parse.py — shared lightweight Silex (.slx) source parser.

Used by lint_silex.py and verify_chunk_ids.py so both tools agree on ONE
definition of the Silex grammar (the CI must never have two parsers that
disagree about what a function is).

Grammar handled (XELIS Silex):
  - top-level items: const / fn / entry / pub fn / hook / struct / enum
  - blocks are brace-delimited; strings are double-quoted with backslash
    escapes; comments are `// ...` and `/* ... */`
  - chunk IDs (XELIS ABI): the *hook constructor* is chunk 0 and EVERY
    function (fn, entry, pub fn) gets the next chunk ID in source
    declaration order. This was validated against the compiled
    chunkmaps in legacy/build/chunkmap_*.txt (see verify_chunk_ids.py
    --validate-legacy).

This module does NOT validate anything: it only turns a .slx text into
structured facts (masked source, functions with spans, constants, string
literals) that the CI tools then check.

Public API:
    SilexFile.parse(path)        -> SilexFile
    sf.masked                    -> source with comments/strings blanked
                                    (same length/offsets, newlines kept)
    sf.functions                 -> [SilexFunction] in declaration order
    sf.consts                    -> {const_name: type}
    sf.strings                   -> [(start, end, content)]
    sf.function_at_line(line)    -> innermost function covering a line
    find_calls(masked, name)     -> [Call(start, open, end)]
    split_args(text)             -> top-level comma split
    assigned_var_before(...)     -> var name (or '_') a call is assigned to
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Declaration regexes (applied to the MASKED source so commented-out code,
# doc comments and string contents are never parsed as code).
# ---------------------------------------------------------------------------

# `entry foo(`, `pub fn foo(`, `fn foo(`, `hook constructor(` — the XELIS
# compile tool assigns one chunk per matched item, in this order.
DECL_RE = re.compile(r"^[ \t]*(entry|pub\s+fn|fn|hook)\s+(\w+)\s*[\(<]", re.MULTILINE)

CONST_RE = re.compile(r"^const\s+(\w+)\s*:\s*([\w\[\]<>, ]+)", re.MULTILINE)

KIND_MAP = {"pub fn": "pub_fn"}


@dataclass
class Call:
    """A syntactic call site `name(...)` found in masked source."""

    name: str
    start: int          # offset of the callee name
    open: int           # offset of the opening '('
    end: int            # offset just past the matching ')'


@dataclass
class SilexFunction:
    kind: str           # 'hook' | 'fn' | 'entry' | 'pub_fn'
    name: str
    decl_line: int      # 1-based line of the declaration keyword
    end_line: int       # 1-based line of the closing brace
    decl_start: int     # offset of the declaration keyword
    decl_end: int       # offset just past the name
    body_start: int     # offset of the opening '{'
    body_end: int       # offset of the matching '}'

    @property
    def is_public(self) -> bool:
        return self.kind in ("entry", "pub_fn")

    @property
    def is_constructor(self) -> bool:
        return self.kind == "hook"

    def covers_line(self, line: int) -> bool:
        return self.decl_line <= line <= self.end_line


@dataclass
class SilexFile:
    path: Path
    src: str
    masked: str
    strings: List[Tuple[int, int, str]] = field(default_factory=list)
    functions: List[SilexFunction] = field(default_factory=list)
    consts: dict = field(default_factory=dict)

    # -- lookups -----------------------------------------------------------

    @classmethod
    def parse(cls, path: Path) -> "SilexFile":
        src = Path(path).read_text(encoding="utf-8", errors="replace")
        masked, strings = mask_source(src)
        functions = parse_functions(masked)
        consts = {m.group(1): m.group(2).strip() for m in CONST_RE.finditer(masked)}
        return cls(path=Path(path), src=src, masked=masked, strings=strings,
                   functions=functions, consts=consts)

    def line_of_offset(self, offset: int) -> int:
        return self.masked.count("\n", 0, offset) + 1

    def line_text(self, line: int) -> str:
        lines = self.src.splitlines()
        return lines[line - 1].strip() if 0 < line <= len(lines) else ""

    def function_at_offset(self, offset: int) -> Optional[SilexFunction]:
        """Innermost function whose body contains `offset` (None outside)."""
        best = None
        for f in self.functions:
            if f.body_start <= offset <= f.body_end:
                if best is None or (f.body_end - f.body_start) < (best.body_end - best.body_start):
                    best = f
        return best

    def function_at_line(self, line: int) -> Optional[SilexFunction]:
        best = None
        for f in self.functions:
            if f.covers_line(line):
                if best is None or (f.end_line - f.decl_line) < (best.end_line - best.decl_line):
                    best = f
        return best

    def function_by_name(self, name: str) -> Optional[SilexFunction]:
        for f in self.functions:
            if f.name == name:
                return f
        return None

    def chunk_index(self, fn: SilexFunction) -> int:
        return self.functions.index(fn)

    def next_function_after_line(self, line: int) -> Optional[SilexFunction]:
        for f in self.functions:
            if f.decl_line > line:
                return f
        return None


# ---------------------------------------------------------------------------
# Masking: comments and string contents become spaces (offsets preserved)
# ---------------------------------------------------------------------------

def mask_source(src: str) -> Tuple[str, List[Tuple[int, int, str]]]:
    out = list(src)
    strings: List[Tuple[int, int, str]] = []
    i, n = 0, len(src)
    state = "code"
    str_start = 0
    while i < n:
        c = src[i]
        if state == "code":
            if c == "/" and i + 1 < n and src[i + 1] == "/":
                out[i] = out[i + 1] = " "
                state = "line"
                i += 2
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "*":
                out[i] = out[i + 1] = " "
                state = "block"
                i += 2
                continue
            if c == '"':
                out[i] = " "
                str_start = i
                state = "str"
                i += 1
                continue
            i += 1
        elif state == "line":
            if c == "\n":
                state = "code"
            elif c != "\t":
                out[i] = " "
            i += 1
        elif state == "block":
            if c == "*" and i + 1 < n and src[i + 1] == "/":
                out[i] = out[i + 1] = " "
                state = "code"
                i += 2
                continue
            if c != "\n":
                out[i] = " "
            i += 1
        else:  # str
            if c == "\\" and i + 1 < n:
                out[i] = " "
                if src[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
                continue
            if c == '"':
                out[i] = " "
                strings.append((str_start, i + 1, src[str_start + 1:i]))
                state = "code"
            else:
                out[i] = " "
            i += 1
    return "".join(out), strings


# ---------------------------------------------------------------------------
# Function extraction with brace matching
# ---------------------------------------------------------------------------

def parse_functions(masked: str) -> List[SilexFunction]:
    funcs: List[SilexFunction] = []
    matches = list(DECL_RE.finditer(masked))
    for idx, m in enumerate(matches):
        raw_kind = re.sub(r"\s+", " ", m.group(1))
        kind = KIND_MAP.get(raw_kind, raw_kind)
        name = m.group(2)
        # body = first balanced { } after the declaration
        b = masked.find("{", m.end())
        if b == -1:
            continue
        # the '{' must belong to THIS declaration (before the next one)
        if idx + 1 < len(matches) and b >= matches[idx + 1].start():
            continue
        depth = 0
        i = b
        end = len(masked)
        while i < len(masked):
            ch = masked[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
            i += 1
        funcs.append(SilexFunction(
            kind=kind,
            name=name,
            decl_line=masked.count("\n", 0, m.start()) + 1,
            end_line=masked.count("\n", 0, end) + 1,
            decl_start=m.start(),
            decl_end=m.end(),
            body_start=b,
            body_end=end,
        ))
    return funcs


# ---------------------------------------------------------------------------
# Call extraction helpers (operate on masked text)
# ---------------------------------------------------------------------------

def find_calls(masked: str, name: str) -> List[Call]:
    calls: List[Call] = []
    for m in re.finditer(rf"\b{re.escape(name)}\s*\(", masked):
        open_idx = m.end() - 1
        end = _match_paren(masked, open_idx)
        calls.append(Call(name=name, start=m.start(), open=open_idx, end=end))
    return calls


def _match_paren(masked: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    while i < len(masked):
        c = masked[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(masked)


def call_args(masked: str, call: Call) -> List[str]:
    """Top-level comma split of the argument list of `call`."""
    inner = masked[call.open + 1:call.end - 1]
    args: List[str] = []
    depth = 0
    cur: List[str] = []
    for ch in inner:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail or args:
        args.append(tail)
    return args


def assigned_var_before(masked: str, call_start: int) -> Optional[str]:
    """If the call is the RHS of an assignment on the same line, return the
    variable name ('_' for `let _ =`), else None."""
    line_begin = masked.rfind("\n", 0, call_start) + 1
    prefix = masked[line_begin:call_start]
    m = re.search(r"(?:let|var)\s+(_|[A-Za-z_]\w*)\s*(?::[^=]*)?\s*=\s*$", prefix)
    if m:
        return m.group(1)
    return None


def call_is_directly_in(masked: str, call: Call, outer_names: Tuple[str, ...]) -> bool:
    """True if `call` is an argument of a direct `name(...)` call."""
    for name in outer_names:
        for outer in find_calls(masked, name):
            if outer.open < call.start and call.end <= outer.end:
                return True
    return False
