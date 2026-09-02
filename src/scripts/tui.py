#!/usr/bin/env python3
"""
============================================================================
 XELIS Vault — Interactive Terminal Menu (shared library)
============================================================================
Arrow-key navigation, Enter to select, no typing numbers.
Works on Linux, macOS, and Windows.
============================================================================
"""
import os
import sys

# ── ANSI Colors ─────────────────────────────────────────────────────────────
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    BRIGHT = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_CYAN = "\033[96m"
    GRAY = "\033[90m"
    BG_CYAN = "\033[46m"

_UNICODE = True

def _detect_unicode_support():
    global _UNICODE
    try:
        encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
        if encoding and ("utf" in encoding or "utf" in (sys.getdefaultencoding() or "")):
            _UNICODE = True
            return
        if os.name == "nt":
            import locale
            loc = (locale.getpreferredencoding() or "").lower()
            if loc.startswith(("cp", "ascii")):
                _UNICODE = False
                return
        _UNICODE = True
    except Exception:
        _UNICODE = False

_detect_unicode_support()

if not _UNICODE:
    _BOX_TL = "+"
    _BOX_TR = "+"
    _BOX_BL = "+"
    _BOX_BR = "+"
    _BOX_H = "-"
    _BOX_V = "|"
    _BLOCK_FULL = "#"
    _BLOCK_EMPTY = "."
    _PILL_LEFT = "["
    _PILL_RIGHT = "]"
else:
    _BOX_TL = "╭"
    _BOX_TR = "╮"
    _BOX_BL = "╰"
    _BOX_BR = "╯"
    _BOX_H = "─"
    _BOX_V = "│"
    _BLOCK_FULL = "█"
    _BLOCK_EMPTY = "░"
    _PILL_LEFT = "["
    _PILL_RIGHT = "]"

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def hide_cursor():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

def show_cursor():
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()

# ── Cross-platform key reader ───────────────────────────────────────────────
def _read_key_unix():
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(2)
            if ch2 == "[A": return "UP"
            if ch2 == "[B": return "DOWN"
            if ch2 == "[C": return "RIGHT"
            if ch2 == "[D": return "LEFT"
            return "ESC"
        if ch == "\r" or ch == "\n": return "ENTER"
        if ch == "\x03": return "CTRL_C"
        if ch == "\x04": return "CTRL_D"
        if ch == "q": return "Q"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def _read_key_windows():
    import msvcrt
    try:
        ch = msvcrt.getch()
    except Exception:
        return "UNKNOWN"
    if ch == b"\xe0" or ch == b"\x00":
        try:
            ch2 = msvcrt.getch()
        except Exception:
            return "UNKNOWN"
        if ch2 == b"H": return "UP"
        if ch2 == b"P": return "DOWN"
        if ch2 == b"M": return "RIGHT"
        if ch2 == b"K": return "LEFT"
        return "SPECIAL"
    if ch == b"\r": return "ENTER"
    if ch == b"\x03": return "CTRL_C"
    if ch == b"\x04": return "CTRL_D"
    if ch == b"\x1b": return "ESC"
    if ch == b"q": return "Q"
    try:
        return ch.decode("ascii", errors="ignore")
    except Exception:
        return "UNKNOWN"

def read_key():
    if os.name == "nt":
        return _read_key_windows()
    return _read_key_unix()

# ── Interactive Menu ────────────────────────────────────────────────────────
def menu(title, options, subtitle=""):
    if not options:
        return None
    normalized = []
    for opt in options:
        if isinstance(opt, tuple):
            normalized.append(opt)
        else:
            normalized.append((str(opt), opt))
    selected = 0
    total = len(normalized)
    hide_cursor()
    try:
        while True:
            clear()
            print(f"{C.CYAN}{C.BOLD}{title}{C.RESET}")
            if subtitle:
                print(f"{C.DIM}{subtitle}{C.RESET}")
            print(f"{C.GRAY}{'─' * 60}{C.RESET}")
            print()
            for i, (label, _) in enumerate(normalized):
                if i == selected:
                    print(f"  {C.BG_CYAN}{C.BOLD} ➤ {label} {C.RESET}")
                else:
                    print(f"  {C.DIM}   {label}{C.RESET}")
            print()
            print(f"{C.GRAY}{'─' * 60}{C.RESET}")
            print(f"{C.DIM}  ↑/↓ Navigate   ↵ Enter Select   q/Esc Back{C.RESET}")
            key = read_key()
            if key == "UP":
                selected = (selected - 1) % total
            elif key == "DOWN":
                selected = (selected + 1) % total
            elif key == "ENTER":
                return normalized[selected][1]
            elif key in ("Q", "ESC", "CTRL_C", "CTRL_D"):
                return None
    finally:
        show_cursor()

def text_input(prompt_text, default="", password=False):
    clear()
    print(f"{C.CYAN}{C.BOLD}XELIS Vault{C.RESET}")
    print(f"{C.GRAY}{'─' * 60}{C.RESET}")
    print()
    hint = f" {C.DIM}[{default}]{C.RESET}" if default else ""
    print(f"  {C.BOLD}{prompt_text}{C.RESET}{hint}")
    print()
    try:
        if password:
            import getpass
            value = getpass.getpass(f"  {C.DIM}> {C.RESET}")
        else:
            value = input(f"  {C.CYAN}> {C.RESET}")
        return value.strip() if value.strip() else default
    except (EOFError, KeyboardInterrupt):
        return default

def confirm(prompt_text, default_yes=True):
    selected = 0 if default_yes else 1
    hide_cursor()
    try:
        while True:
            clear()
            print(f"{C.CYAN}{C.BOLD}XELIS Vault{C.RESET}")
            print(f"{C.GRAY}{'─' * 60}{C.RESET}")
            print()
            print(f"  {C.BOLD}{prompt_text}{C.RESET}")
            print()
            labels = ["Yes", "No"]
            for i, label in enumerate(labels):
                if i == selected:
                    print(f"  {C.BG_CYAN}{C.BOLD} > {label} {C.RESET}")
                else:
                    print(f"  {C.DIM}   {label}{C.RESET}")
            print()
            print(f"{C.DIM}  Left/Right Select   Enter Confirm{C.RESET}")
            key = read_key()
            if key in ("UP", "LEFT"):
                selected = (selected - 1) % 2
            elif key in ("DOWN", "RIGHT"):
                selected = (selected + 1) % 2
            elif key == "ENTER":
                return selected == 0
            elif key in ("Q", "ESC", "CTRL_C", "CTRL_D"):
                return False
    finally:
        show_cursor()

def info_box(title, lines, color=C.CYAN):
    try:
        clear()
        body = render_panel(title, list(lines), border_color=color)
        print(body)
        print()
        print(f"{C.DIM}  Press Enter to continue...{C.RESET}")
        read_key()
    finally:
        show_cursor()

def progress_bar(current, maximum, width=30):
    if maximum == 0:
        return f"[{'?' * width}]"
    pct = min(current / maximum, 1.0)
    filled = int(pct * width)
    color = C.GREEN if pct > 0.5 else C.YELLOW if pct > 0.25 else C.RED
    return f"[{color}{'#' * filled}{'.' * (width - filled)}{C.RESET}]"


# ── Non-blocking key check (for auto-refresh) ───────────────────────────────
def kbhit():
    """Check if a key is available without blocking. Returns True/False."""
    if os.name == "nt":
        import msvcrt
        return msvcrt.kbhit()
    else:
        import select
        return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

def read_key_timeout(timeout_sec=1.0):
    """Read a key with timeout. Returns key string or None if timeout."""
    if os.name == "nt":
        import msvcrt
        import time
        start = time.time()
        while time.time() - start < timeout_sec:
            try:
                if msvcrt.kbhit():
                    return read_key()
            except Exception:
                return None
            time.sleep(0.05)
        return None
    else:
        import select
        r, _, _ = select.select([sys.stdin], [], [], timeout_sec)
        if r:
            return read_key()
        return None


BANNER = f"""{C.CYAN}{C.BOLD}
 ██████  ██      ██   ██ ██ ███████  ██████ ████████ ██  ██████  ███    ██
██    ██ ██      ██  ██  ██ ██      ██         ██    ██ ██    ██ ████   ██
██    ██ ██      █████   ██ █████   ██         ██    ██ ██    ██ ██ ██  ██
██    ██ ██      ██  ██  ██ ██      ██         ██    ██ ██    ██ ██  ██ ██
 ██████  ███████ ██   ██ ██ ███████  ██████    ██    ██  ██████  ██   ████
{C.RESET}{C.DIM}              Privacy-First DeFi on XELIS BlockDAG{C.RESET}"""


# ============================================================================
# Professional rendering layer (rich when available, ANSI fallback otherwise)
# ----------------------------------------------------------------------------
# Everything returns a plain string so screens can print it normally and stay
# portable. `rich` is auto-detected; when absent every function degrades to a
# hand-rolled ANSI/Unicode equivalent. No hard dependency.
# ============================================================================
try:  # pragma: no cover - detection only
    from rich.console import Console as _RichConsole
    from rich.panel import Panel as _RichPanel
    from rich.table import Table as _RichTable
    from rich.text import Text as _RichText
    from rich.columns import Columns as _RichColumns
    from rich import box as _RichBox
    _RICH = True
except Exception:  # nocover
    _RICH = False

_stdout_console = None


def _console():
    global _stdout_console
    if _RICH:
        try:
            if _stdout_console is None:
                _stdout_console = _RichConsole(force_terminal=True,
                                               soft_wrap=False)
            return _stdout_console
        except Exception:
            return None
    return None


def _strip_rich(s: str) -> str:
    """Remove ANSI codes so a rendered string can be safely padded/measured."""
    import re as _re
    return _re.sub(r"\x1b\[[0-9;]*m", "", s)


def has_rich() -> bool:
    return _RICH


def render_bar(frac: float, width: int = 22,
               good: tuple = (0.6, 1.0)) -> str:
    """Colored horizontal bar scaled to frac (0..1). Returns an ANSI string."""
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    c = C.GREEN if frac >= good[0] else (C.YELLOW if frac >= good[1] else C.RED)
    b = ""
    b += f"{C.DIM}[{C.RESET}"
    b += f"{c}{_BLOCK_FULL * filled}{C.RESET}"
    b += f"{C.DIM}{_BLOCK_EMPTY * (width - filled)}{C.RESET}"
    b += f"{C.DIM}]{C.RESET}"
    return b


def render_badge(text: str, color: str = C.CYAN, filled: bool = False) -> str:
    """Pill/badge like `[ label ]` with optional background fill."""
    t = f" {text.strip()} "
    if filled:
        return f"{color}{C.BOLD}▌{color} {t} {C.RESET}"
    return f"{color}{C.BOLD}{_PILL_LEFT}{C.RESET}{color}{t}{C.RESET}{color}{C.BOLD}{_PILL_RIGHT}{C.RESET}"


def render_panel(title: str, lines, border_color: str = C.CYAN,
                 width: int = 66, accent: str = "█") -> str:
    """Draw a labeled panel. `lines` may be str or iterable of str.

    When rich is present a true rounded panel is rendered; otherwise an ANSI
    box with the same visual intent (portable everywhere).
    """
    if isinstance(lines, str):
        lines = lines.split("\n")
    lines = [str(x) for x in lines]
    if _RICH:
        try:
            con = _console()
            body = "\n".join(lines)
            panel = _RichPanel(
                _RichText.from_ansi(body),
                title=title, border_style=_ansi_to_rich(border_color),
                box=_RichBox.ROUNDED, padding=(0, 1), expand=False,
            )
            with con.capture() as cap:
                con.print(panel)
            return cap.get()
        except Exception:
            pass
    # --- ANSI fallback: rounded box with colored title bar ---
    inner = width - 4
    bp = border_color
    s = []
    s.append(f"{bp}{_BOX_TL}{_BOX_H * (width - 2)}{_BOX_TR}{C.RESET}")
    s.append(f"{bp}{_BOX_V} {title:<{inner}} {_BOX_V}{C.RESET}")
    s.append(f"{bp}{_BOX_V}{_BOX_H * (width - 2)}{_BOX_V}{C.RESET}")
    for ln in lines:
        show = _strip_rich(str(ln))
        if len(show) > inner:
            show = show[:inner - 1] + "…"
        pad = inner - len(show)
        s.append(f"{bp}{_BOX_V} {C.RESET}{show}{' ' * pad}{bp} {_BOX_V}{C.RESET}")
    s.append(f"{bp}{_BOX_BL}{_BOX_H * (width - 2)}{_BOX_BR}{C.RESET}")
    return "\n".join(s)


def _rich_markup_safe(s: str) -> bool:
    return "[" not in s and "]" not in s


def _ansi_to_rich(color: str) -> str:
    if color in (C.CYAN, "cyan"):
        return "cyan"
    if color in (C.GREEN, "green"):
        return "green"
    if color in (C.YELLOW, "yellow"):
        return "yellow"
    if color in (C.RED, "red"):
        return "red"
    if color in (C.MAGENTA, "magenta"):
        return "magenta"
    if color in (C.BLUE, "blue"):
        return "blue"
    if color in (C.WHITE, "white"):
        return "white"
    return "cyan"


def render_metrics(rows, title: str = "", border_color: str = C.CYAN,
                   width: int = 66) -> str:
    """A two-column key/value block, optionally wrapped in a titled panel.

    `rows`: list of (label, value) where value is already styled ANSI text.
    """
    if not rows:
        lines = ["(no data)"]
    else:
        inner = width - 6
        max_k = min(24, max((len(_strip_rich(str(k))) for k, _ in rows), default=0))
        lines = []
        for k, v in rows:
            v_show = _strip_rich(str(v))
            dot = max_k - len(_strip_rich(str(k)))
            lines.append(f"{C.BOLD}{k}{C.RESET}{' ' * dot}  {v}")
    if title:
        return render_panel(title, lines, border_color=border_color, width=width)
    return "\n".join(lines) if not _RICH else "\n".join(lines)


def render_hint(txt: str) -> str:
    return f"{C.DIM}  {txt}{C.RESET}"


def render_ok(txt: str) -> str:
    return f"{C.GREEN}● {txt}{C.RESET}"


def render_warn(txt: str) -> str:
    return f"{C.YELLOW}● {txt}{C.RESET}"


def render_error(txt: str) -> str:
    return f"{C.RED}● {txt}{C.RESET}"


def render_status(ok: bool, label: str) -> str:
    if ok:
        return f"{C.GREEN}● {label}{C.RESET}"
    return f"{C.RED}○ {label}{C.RESET}"


def render_arrow(selected: bool, label: str, color=C.BG_CYAN) -> str:
    if selected:
        return f"  {color}{C.BOLD}➤ {label} {C.RESET}"
    return f"  {C.DIM}  {label}{C.RESET}"
