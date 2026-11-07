import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


APP_NAME = "<3Eevee's Koth Calculator<3"
STATE_FILE_NAME = ".koth_calculator_state.json"
STATE_VERSION = 3

_DEBUG_LOG_FN: Optional[Callable[[str], None]] = None


def _dbg(message: str) -> None:
    fn = _DEBUG_LOG_FN
    if fn is None:
        return
    try:
        fn(str(message))
    except Exception:
        pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _save_json(path: str, data: dict[str, Any]) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _extract_ints(text: str) -> list[int]:
    return [int(m.group(0)) for m in re.finditer(r"-?\d+", text)]


_ONES: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}

_TENS: dict[str, int] = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

_SCALES: dict[str, int] = {"hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}


def _words_to_int(tokens: list[str]) -> Optional[int]:
    current = 0
    total = 0
    saw_any = False

    for tok in tokens:
        if tok in ("and",):
            continue
        if tok in _ONES:
            current += _ONES[tok]
            saw_any = True
            continue
        if tok in _TENS:
            current += _TENS[tok]
            saw_any = True
            continue
        if tok in _SCALES:
            scale = _SCALES[tok]
            if scale == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * scale
                current = 0
            saw_any = True
            continue
        if tok.isdigit() or (tok.startswith("-") and tok[1:].isdigit()):
            current += int(tok)
            saw_any = True
            continue
        return None

    if not saw_any:
        return None
    return total + current


def _parse_first_number(text: str) -> Optional[int]:
    raw = text.strip()
    lower = raw.lower()
    sign = 1
    if lower.startswith("minus ") or lower.startswith("negative "):
        sign = -1
        lower = lower.split(None, 1)[1] if len(lower.split(None, 1)) == 2 else ""
        raw = lower
    _dbg(f"_parse_first_number raw={raw!r} sign={sign}")

    m = re.search(r"\b(to|too|two)\s+(t|tee|tea|ty)\b", raw.lower())
    if m:
        _dbg(f"_parse_first_number tens_like={m.group(0)!r} -> 20")
        return sign * 20
    m = re.search(r"\b(free|tree|three)\s+(t|tee|tea|ty)\b", raw.lower())
    if m:
        _dbg(f"_parse_first_number tens_like={m.group(0)!r} -> 30")
        return sign * 30
    m = re.search(r"\b(for|fore|four|fower)\s+(t|tee|tea|ty)\b", raw.lower())
    if m:
        _dbg(f"_parse_first_number tens_like={m.group(0)!r} -> 40")
        return sign * 40

    comma_number = re.search(r"(?<!\d)\d{1,3}(?:,\s*\d{3})+(?!\d)", raw)
    if comma_number:
        compact = re.sub(r"[,\s]", "", comma_number.group(0))
        if compact.isdigit():
            _dbg(f"_parse_first_number comma_number={comma_number.group(0)!r} -> {compact}")
            return sign * int(compact)

    spaced_digits = re.search(r"(?<!\d)(?:\d\s+){1,}\d(?!\d)", raw)
    if spaced_digits:
        digits = re.findall(r"\d", spaced_digits.group(0))
        if digits:
            _dbg(f"_parse_first_number spaced_digits={spaced_digits.group(0)!r} -> {''.join(digits)}")
            return sign * int("".join(digits))

    ints = _extract_ints(raw)
    if ints:
        _dbg(f"_parse_first_number ints={ints} -> {ints[0]}")
        return sign * ints[0]

    cleaned = re.sub(r"[^a-zA-Z\s-]", " ", raw.lower()).replace("-", " ")
    tokens = [t for t in cleaned.split() if t]
    homophones: dict[str, str] = {
        "o": "zero",
        "oh": "zero",
        "owe": "zero",
        "won": "one",
        "to": "two",
        "too": "two",
        "free": "three",
        "tree": "three",
        "for": "four",
        "fore": "four",
        "fower": "four",
        "ate": "eight",
        "sex": "six",
    }
    tokens = [homophones.get(t, t) for t in tokens]
    if not tokens:
        return None
    tokens2: list[str] = []
    for i, t in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if t == "a" and nxt in _SCALES:
            tokens2.append("one")
            continue
        tokens2.append(t)
    tokens = tokens2
    digit_words: dict[str, str] = {
        "zero": "0",
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
    }
    if len(tokens) >= 2 and all((t in digit_words) for t in tokens):
        _dbg(f"_parse_first_number digit_words={' '.join(tokens[:20])} -> {''.join(digit_words[t] for t in tokens)}")
        return sign * int("".join(digit_words[t] for t in tokens))

    best: Optional[int] = None
    best_span = 0
    for i in range(len(tokens)):
        for j in range(i + 1, min(len(tokens), i + 20) + 1):
            val = _words_to_int(tokens[i:j])
            if val is None:
                continue
            span = j - i
            if span > best_span:
                best_span = span
                best = sign * val
                if best_span >= len(tokens):
                    _dbg(f"_parse_first_number words_to_int={' '.join(tokens[:20])} -> {best}")
                    return best
    if best is not None:
        _dbg(f"_parse_first_number words_to_int={' '.join(tokens[:20])} -> {best}")
    return best


def _parse_input(text: str) -> tuple[str, Optional[int]]:
    raw = text.strip()
    if not raw:
        return ("noop", None)

    lower = raw.lower().strip()
    if lower in ("add", "add hp", "hp"):
        return ("noop", None)
    if lower in ("q", "quit", "exit"):
        return ("quit", None)
    if lower in ("r", "reset", "new", "next", "clear"):
        return ("reset", None)
    if lower in ("u", "undo", "back"):
        return ("undo", None)
    if lower in ("h", "high", "hi", "score"):
        return ("show_high", None)
    if lower in ("s", "status"):
        return ("status", None)

    if lower.startswith("set "):
        return ("set_total", _parse_first_number(lower[4:]))
    if lower.startswith("add "):
        return ("add", _parse_first_number(lower[4:]))
    if lower.startswith("+"):
        return ("add", _parse_first_number(lower[1:]))

    n = _parse_first_number(lower)
    if n is not None:
        return ("add", n)
    return ("unknown", None)


@dataclass
class PackRecord:
    pack_no: int
    total: int
    ended_at: str


@dataclass
class PlayerState:
    name: str
    current_total: int = 0
    best_pack_total: int = 0
    best_pack_at: Optional[str] = None
    additions: list[int] = field(default_factory=list)
    packs: list[PackRecord] = field(default_factory=list)

    def maybe_update_best(self) -> bool:
        if self.current_total > self.best_pack_total:
            self.best_pack_total = self.current_total
            self.best_pack_at = _utc_now_iso()
            return True
        return False


@dataclass
class AppState:
    players: dict[str, PlayerState] = field(default_factory=dict)
    selected_player: str = ""
    celebration_enabled: bool = False
    celebration_monitor: int = 0
    celebration_seconds: float = 5.0
    celebration_fireworks_gif: str = ""
    bg_sync_enabled: bool = False
    bg_sync_layout_path: str = ""
    bg_sync_monitor: int = 0
    bg_sync_top1_layer_id: int = 0
    bg_sync_top2_layer_id: int = 0
    bg_sync_top3_layer_id: int = 0

    def normalize_selection(self) -> None:
        if self.selected_player and self.selected_player in self.players:
            return
        if self.players:
            self.selected_player = next(iter(self.players.keys()))
        else:
            self.selected_player = ""

    def get_selected(self) -> Optional[PlayerState]:
        self.normalize_selection()
        if not self.selected_player:
            return None
        return self.players.get(self.selected_player)

    def first_place(self) -> tuple[str, int]:
        self.normalize_selection()
        if not self.players:
            return ("", 0)
        best_name = ""
        best_total = -10**18
        for name, p in self.players.items():
            if p.current_total > best_total:
                best_total = p.current_total
                best_name = name
        return (best_name, int(best_total))

    def best_pack_overall(self) -> tuple[str, int, Optional[str]]:
        if not self.players:
            return ("", 0, None)
        best_name = ""
        best_total = -10**18
        best_at: Optional[str] = None
        for name, p in self.players.items():
            if p.best_pack_total > best_total:
                best_total = p.best_pack_total
                best_name = name
                best_at = p.best_pack_at
        return (best_name, int(best_total if best_total != -10**18 else 0), best_at)


def _state_from_disk(state_path: str) -> AppState:
    data = _load_json(state_path)

    if "players" not in data and ("current_total" in data or "high_score" in data):
        p = PlayerState(
            name="Player 1",
            current_total=int(data.get("current_total", 0) or 0),
            best_pack_total=int(data.get("high_score", 0) or 0),
            best_pack_at=data.get("high_score_at", None) if isinstance(data.get("high_score_at", None), str) else None,
            additions=[int(x) for x in data.get("additions", []) if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()],
        )
        st = AppState(players={"Player 1": p}, selected_player="Player 1")
        st.normalize_selection()
        return st

    players_raw = data.get("players", {})
    players: dict[str, PlayerState] = {}
    if isinstance(players_raw, dict):
        for name, pdata in players_raw.items():
            if not isinstance(name, str) or not isinstance(pdata, dict):
                continue
            current_total = int(pdata.get("current_total", 0) or 0)
            best_pack_total = int(pdata.get("best_pack_total", 0) or 0)
            best_pack_at = pdata.get("best_pack_at", None)
            additions_raw = pdata.get("additions", [])
            additions: list[int] = []
            if isinstance(additions_raw, list):
                for x in additions_raw:
                    try:
                        additions.append(int(x))
                    except Exception:
                        pass
            packs_raw = pdata.get("packs", [])
            packs: list[PackRecord] = []
            if isinstance(packs_raw, list):
                for rec in packs_raw:
                    if not isinstance(rec, dict):
                        continue
                    total_raw = rec.get("total", None)
                    ended_at_raw = rec.get("ended_at", None)
                    try:
                        total_int = int(total_raw)
                    except Exception:
                        continue
                    ended_at = ended_at_raw if isinstance(ended_at_raw, str) else ""
                    packs.append(PackRecord(pack_no=0, total=total_int, ended_at=ended_at))
            players[name] = PlayerState(
                name=name,
                current_total=current_total,
                best_pack_total=best_pack_total,
                best_pack_at=best_pack_at if isinstance(best_pack_at, str) else None,
                additions=additions,
                packs=packs,
            )

    for p in players.values():
        for i, rec in enumerate(p.packs, start=1):
            rec.pack_no = int(i)

    selected_player = data.get("selected_player", "")
    celebration_enabled_raw = data.get("celebration_enabled", False)
    celebration_enabled = celebration_enabled_raw if isinstance(celebration_enabled_raw, bool) else False
    celebration_monitor_raw = data.get("celebration_monitor", 0)
    celebration_monitor = int(celebration_monitor_raw) if isinstance(celebration_monitor_raw, int) else 0
    celebration_seconds_raw = data.get("celebration_seconds", 5.0)
    celebration_seconds = float(celebration_seconds_raw) if isinstance(celebration_seconds_raw, (int, float)) else 5.0
    if celebration_seconds < 1.0:
        celebration_seconds = 1.0
    if celebration_seconds > 30.0:
        celebration_seconds = 30.0
    celebration_fireworks_gif_raw = data.get("celebration_fireworks_gif", "")
    celebration_fireworks_gif = celebration_fireworks_gif_raw if isinstance(celebration_fireworks_gif_raw, str) else ""

    bg_sync_enabled_raw = data.get("bg_sync_enabled", False)
    bg_sync_enabled = bg_sync_enabled_raw if isinstance(bg_sync_enabled_raw, bool) else False
    bg_sync_layout_path = data.get("bg_sync_layout_path", "")
    bg_sync_layout_path = bg_sync_layout_path if isinstance(bg_sync_layout_path, str) else ""
    # Treat layout path as layout name if it doesn't look like a path
    bg_sync_layout_name = bg_sync_layout_path 

    bg_sync_monitor_raw = data.get("bg_sync_monitor", 0)
    try:
        bg_sync_monitor = int(bg_sync_monitor_raw)
    except Exception:
        bg_sync_monitor = 0
    if bg_sync_monitor < 0:
        bg_sync_monitor = 0

    def _coerce_layer_id(value: Any) -> int:
        try:
            v = int(value)
        except Exception:
            v = 0
        if v < 0:
            return 0
        return v

    bg_sync_top1_layer_id = _coerce_layer_id(data.get("bg_sync_top1_layer_id", 0))
    bg_sync_top2_layer_id = _coerce_layer_id(data.get("bg_sync_top2_layer_id", 0))
    bg_sync_top3_layer_id = _coerce_layer_id(data.get("bg_sync_top3_layer_id", 0))
    st = AppState(
        players=players,
        selected_player=selected_player if isinstance(selected_player, str) else "",
        celebration_enabled=celebration_enabled,
        celebration_monitor=celebration_monitor,
        celebration_seconds=celebration_seconds,
        celebration_fireworks_gif=celebration_fireworks_gif,
        bg_sync_enabled=bg_sync_enabled,
        bg_sync_layout_path=bg_sync_layout_path,
        bg_sync_monitor=bg_sync_monitor,
        bg_sync_top1_layer_id=bg_sync_top1_layer_id,
        bg_sync_top2_layer_id=bg_sync_top2_layer_id,
        bg_sync_top3_layer_id=bg_sync_top3_layer_id,
    )
    # We repurpose bg_sync_layout_path to store the layout name for backward compatibility in config
    st.bg_sync_layout_path = bg_sync_layout_name
    st.normalize_selection()
    return st


def _state_to_disk(state_path: str, st: AppState) -> None:
    st.normalize_selection()
    _save_json(
        state_path,
        {
            "app": APP_NAME,
            "version": STATE_VERSION,
            "saved_at": _utc_now_iso(),
            "selected_player": st.selected_player,
            "celebration_enabled": bool(st.celebration_enabled),
            "celebration_monitor": int(st.celebration_monitor),
            "celebration_seconds": float(st.celebration_seconds),
            "celebration_fireworks_gif": str(st.celebration_fireworks_gif or ""),
            "bg_sync_enabled": bool(st.bg_sync_enabled),
            "bg_sync_layout_path": str(st.bg_sync_layout_path or ""),
            "bg_sync_monitor": int(st.bg_sync_monitor),
            "bg_sync_top1_layer_id": int(st.bg_sync_top1_layer_id),
            "bg_sync_top2_layer_id": int(st.bg_sync_top2_layer_id),
            "bg_sync_top3_layer_id": int(st.bg_sync_top3_layer_id),
            "players": {
                name: {
                    "current_total": p.current_total,
                    "best_pack_total": p.best_pack_total,
                    "best_pack_at": p.best_pack_at,
                    "additions": p.additions,
                    "packs": [{"pack_no": r.pack_no, "total": r.total, "ended_at": r.ended_at} for r in p.packs],
                }
                for name, p in st.players.items()
            },
        },
    )


def _ensure_cli_defaults(st: AppState) -> None:
    if not st.players:
        st.players["Player 1"] = PlayerState(name="Player 1")
    st.normalize_selection()


def _add_hp(st: AppState, player_name: str, value: int) -> bool:
    if player_name not in st.players:
        st.players[player_name] = PlayerState(name=player_name)
    p = st.players[player_name]
    p.current_total += int(value)
    p.additions.append(int(value))
    return p.maybe_update_best()


def _set_total(st: AppState, player_name: str, value: int) -> bool:
    if player_name not in st.players:
        st.players[player_name] = PlayerState(name=player_name)
    p = st.players[player_name]
    p.current_total = int(value)
    p.additions = []
    return p.maybe_update_best()


def _undo(st: AppState, player_name: str) -> Optional[int]:
    p = st.players.get(player_name)
    if not p or not p.additions:
        return None
    last = p.additions.pop()
    p.current_total -= last
    return last


def _reset_pack(st: AppState, player_name: str) -> bool:
    p = st.players.get(player_name)
    if not p:
        return False
    updated = p.maybe_update_best()
    p.packs.append(PackRecord(pack_no=(len(p.packs) + 1), total=int(p.current_total), ended_at=_utc_now_iso()))
    p.current_total = 0
    p.additions = []
    return updated


def _run_cli(state_path: str) -> int:
    st = _state_from_disk(state_path)
    _ensure_cli_defaults(st)
    _state_to_disk(state_path, st)
    return _keyboard_loop_cli(state_path, st)


def _keyboard_loop_cli(state_path: str, st: AppState) -> int:
    print(APP_NAME)
    print("CLI mode. Commands: reset, undo, status, high, set N, quit")
    while True:
        p = st.get_selected()
        hs_at = p.best_pack_at or "n/a"
        print(f"Player: {p.name} | Pack: {p.current_total} | Best: {p.best_pack_total} ({hs_at})")
        try:
            line = input("> ")
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            break

        action, value = _parse_input(line)
        if action == "quit":
            _state_to_disk(state_path, st)
            return 0
        if action == "reset":
            updated = _reset_pack(st, p.name)
            _state_to_disk(state_path, st)
            if updated:
                print("New best pack saved.")
            continue
        if action == "undo":
            last = _undo(st, p.name)
            _state_to_disk(state_path, st)
            if last is None:
                print("Nothing to undo.")
            else:
                print(f"Undid: {last}")
            continue
        if action == "show_high":
            print(f"Best pack: {p.best_pack_total} ({p.best_pack_at or 'n/a'})")
            continue
        if action == "set_total":
            if value is None:
                print("Could not parse a number.")
                continue
            updated = _set_total(st, p.name, value)
            _state_to_disk(state_path, st)
            if updated:
                print("New best pack saved.")
            continue
        if action == "add":
            if value is None:
                print("Could not parse a number.")
                continue
            updated = _add_hp(st, p.name, value)
            _state_to_disk(state_path, st)
            if updated:
                print("New best pack saved.")
            continue
        if action == "status":
            continue
        print("Unrecognized input. Try a number, or: reset/undo/status/high/set/quit")

    _state_to_disk(state_path, st)
    return 0




def _run_gui(state_path: str) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    st = _state_from_disk(state_path)
    st.normalize_selection()
    _state_to_disk(state_path, st)

    root = tk.Tk()
    root.title(APP_NAME)
    root.minsize(980, 620)
    icon_image: Optional[tk.PhotoImage] = None
    is_frozen = bool(getattr(sys, "frozen", False))
    runtime_dir = os.path.dirname(sys.executable) if is_frozen else os.path.dirname(os.path.abspath(__file__))
    bundled_dir = getattr(sys, "_MEIPASS", runtime_dir) if is_frozen else runtime_dir
    asset_dirs = [os.path.join(runtime_dir, "assets"), runtime_dir, bundled_dir]
    icon_path: Optional[str] = None
    for base in asset_dirs:
        for candidate in ("eevee.ico", "app.ico", "icon.ico"):
            p = os.path.join(base, candidate)
            if os.path.isfile(p):
                icon_path = p
                break
        if icon_path is not None:
            break
    if icon_path is None:
        try:
            for base in asset_dirs:
                for fn in os.listdir(base):
                    if fn.lower().endswith(".ico"):
                        icon_path = os.path.join(base, fn)
                        break
                if icon_path is not None:
                    break
        except Exception:
            icon_path = None
    try:
        if icon_path is not None and icon_path.lower().endswith(".ico"):
            root.iconbitmap(default=os.path.abspath(icon_path))
        else:
            for base in asset_dirs:
                for candidate in ("eevee.png", "app.png", "icon.png"):
                    p = os.path.join(base, candidate)
                    if os.path.isfile(p):
                        icon_image = tk.PhotoImage(file=p)
                        root.iconphoto(True, icon_image)
                        break
                if icon_image is not None:
                    break
    except Exception:
        pass

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    base_font = ("Segoe UI", 11)
    header_font = ("Segoe UI Semibold", 16)
    big_font = ("Segoe UI Semibold", 22)
    mono_font = ("Consolas", 10)

    root.option_add("*Font", base_font)

    toast_text = tk.StringVar(value="")
    toast_after: dict[str, Optional[str]] = {"id": None}
    toast_labels: list[ttk.Label] = []

    def show_toast(message: str, kind: str = "info") -> None:
        color = "#7c3aed"
        if kind == "ok":
            color = "#6d28d9"
        elif kind == "warn":
            color = "#a855f7"
        elif kind == "error":
            color = "#c026d3"
        toast_text.set(message)
        for lbl in toast_labels:
            try:
                lbl.configure(foreground=color)
            except Exception:
                pass
        if toast_after["id"] is not None:
            try:
                root.after_cancel(toast_after["id"])
            except Exception:
                pass
        toast_after["id"] = root.after(2200, lambda: toast_text.set(""))

    def _list_monitors() -> list[dict[str, Any]]:
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class RECT(ctypes.Structure):
                    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

                class MONITORINFO(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", RECT),
                        ("rcWork", RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]

                user32 = ctypes.windll.user32
                monitors: list[dict[str, Any]] = []

                def callback(hMonitor: wintypes.HMONITOR, hdcMonitor: wintypes.HDC, lprcMonitor: ctypes.POINTER(RECT), dwData: wintypes.LPARAM) -> int:
                    mi = MONITORINFO()
                    mi.cbSize = ctypes.sizeof(MONITORINFO)
                    if user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
                        r = mi.rcMonitor
                        w = int(r.right - r.left)
                        h = int(r.bottom - r.top)
                        monitors.append(
                            {
                                "x": int(r.left),
                                "y": int(r.top),
                                "w": w,
                                "h": h,
                                "primary": bool(mi.dwFlags & 1),
                            }
                        )
                    return 1

                MonitorEnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)
                user32.EnumDisplayMonitors(None, None, MonitorEnumProc(callback), 0)
                monitors.sort(key=lambda m: (0 if m.get("primary") else 1, m.get("x", 0), m.get("y", 0)))
                if monitors:
                    return monitors
            except Exception:
                pass

        try:
            sw = int(root.winfo_screenwidth())
            sh = int(root.winfo_screenheight())
        except Exception:
            sw, sh = 1920, 1080
        return [{"x": 0, "y": 0, "w": sw, "h": sh, "primary": True}]

    monitors = _list_monitors()

    def _monitor_labels(ms: list[dict[str, Any]]) -> list[str]:
        labels: list[str] = []
        for i, m in enumerate(ms, start=1):
            tag = " (Primary)" if m.get("primary") else ""
            labels.append(f"{i}: {int(m.get('w', 0))}x{int(m.get('h', 0))} @ ({int(m.get('x', 0))},{int(m.get('y', 0))}){tag}")
        if not labels:
            labels.append("1: 0x0 @ (0,0)")
        return labels

    def _celebration_monitor_rect() -> tuple[int, int, int, int]:
        nonlocal monitors
        if not monitors:
            monitors = _list_monitors()
        idx = int(st.celebration_monitor) if isinstance(st.celebration_monitor, int) else 0
        if idx < 0:
            idx = 0
        if idx >= len(monitors):
            idx = 0
        st.celebration_monitor = idx
        m = monitors[idx]
        return (int(m.get("x", 0)), int(m.get("y", 0)), int(m.get("w", 0)), int(m.get("h", 0)))

    fireworks_cache: dict[str, Any] = {"path": None, "w": None, "h": None, "frames": [], "delays": []}
    fireworks_runtime: dict[str, Any] = {"win": None, "cv": None, "img_item": None, "frames": [], "delays": [], "frame_index": 0, "w": 0, "h": 0, "path": None, "after_id": None}

    def _resolve_fireworks_path() -> Optional[str]:
        choice = str(getattr(st, "celebration_fireworks_gif", "") or "").strip()
        if choice and choice != "Auto":
            try:
                if os.path.isfile(choice):
                    return choice
            except Exception:
                pass
            base_name = os.path.basename(choice)
            for base in asset_dirs:
                p = os.path.join(base, base_name)
                if os.path.isfile(p):
                    return p
                try:
                    for fn in os.listdir(base):
                        if str(fn).lower() == base_name.lower():
                            p2 = os.path.join(base, fn)
                            if os.path.isfile(p2):
                                return p2
                except Exception:
                    pass

        for base in asset_dirs:
            for candidate in ("firework.gif", "fireworks.gif", "celebrate.gif", "celebration.gif", "party.gif"):
                p = os.path.join(base, candidate)
                if os.path.isfile(p):
                    return p
        for base in asset_dirs:
            try:
                for fn in os.listdir(base):
                    lower = str(fn).lower()
                    if lower.endswith(".gif") and ("firework" in lower or "celebrat" in lower or "party" in lower):
                        p = os.path.join(base, fn)
                        if os.path.isfile(p):
                            return p
            except Exception:
                pass
        return None

    def _load_fireworks_frames(fireworks_path: str, w: int, h: int) -> tuple[list[Any], list[int]]:
        frames: list[Any] = []
        delays: list[int] = []
        cache_ok = (
            fireworks_cache.get("path") == fireworks_path
            and fireworks_cache.get("w") == w
            and fireworks_cache.get("h") == h
            and isinstance(fireworks_cache.get("frames"), list)
            and isinstance(fireworks_cache.get("delays"), list)
            and bool(fireworks_cache.get("frames"))
        )
        if cache_ok:
            return (fireworks_cache["frames"], fireworks_cache["delays"])

        try:
            from PIL import Image, ImageOps, ImageSequence, ImageTk  # type: ignore

            im = Image.open(fireworks_path)
            pil_frames: list[Any] = []
            pil_delays: list[int] = []
            composed = None
            for frame in ImageSequence.Iterator(im):
                rgba = frame.convert("RGBA")
                if composed is None:
                    composed = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
                try:
                    composed.alpha_composite(rgba)
                except Exception:
                    composed.paste(rgba, (0, 0), rgba)
                pil_frames.append(composed.copy())
                duration = int(frame.info.get("duration", 90))
                duration = max(10, min(duration, 5000))
                pil_delays.append(duration)
            if pil_frames:
                try:
                    resampling = getattr(Image, "Resampling", None)
                    method = resampling.LANCZOS if resampling is not None else Image.LANCZOS
                except Exception:
                    method = Image.BICUBIC
                frames = [ImageTk.PhotoImage(ImageOps.fit(f, (w, h), method=method)) for f in pil_frames]
                delays = pil_delays[:] if len(pil_delays) == len(frames) else [90] * len(frames)
        except Exception:
            try:
                i = 0
                while True:
                    try:
                        frames.append(tk.PhotoImage(file=fireworks_path, format=f"gif -index {i}"))
                        delays.append(90)
                        i += 1
                    except tk.TclError:
                        break
                if not frames:
                    frames = [tk.PhotoImage(file=fireworks_path)]
                    delays = [90]
            except Exception:
                frames = []
                delays = []

        if frames:
            fireworks_cache["path"] = fireworks_path
            fireworks_cache["w"] = w
            fireworks_cache["h"] = h
            fireworks_cache["frames"] = frames
            fireworks_cache["delays"] = delays
        return (frames, delays)

    def _swap_running_fireworks() -> None:
        win = fireworks_runtime.get("win")
        if win is None:
            return
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return

        w = int(fireworks_runtime.get("w") or 0)
        h = int(fireworks_runtime.get("h") or 0)
        if w <= 10 or h <= 10:
            return

        fireworks_path = _resolve_fireworks_path()
        if fireworks_path is None:
            show_toast("Missing firework(s).gif (put it next to the exe or in assets).", "warn")
            return

        frames, delays = _load_fireworks_frames(fireworks_path, w, h)
        if not frames:
            show_toast("firework(s).gif failed to load.", "warn")
            return

        fireworks_runtime["frames"] = frames
        fireworks_runtime["delays"] = delays
        fireworks_runtime["frame_index"] = 0
        fireworks_runtime["path"] = fireworks_path
        cv = fireworks_runtime.get("cv")
        img_item = fireworks_runtime.get("img_item")
        try:
            if cv is not None and img_item is not None:
                cv.itemconfigure(img_item, image=frames[0])
        except Exception:
            pass

    def show_fireworks(actor: str, rank: int) -> None:
        if not st.celebration_enabled:
            return
        fireworks_path = _resolve_fireworks_path()
        if fireworks_path is None:
            show_toast("Missing firework(s).gif (put it next to the exe or in assets).", "warn")
            return

        x, y, w, h = _celebration_monitor_rect()
        if w <= 10 or h <= 10:
            return

        win = tk.Toplevel(root)
        try:
            win.overrideredirect(True)
        except Exception:
            pass
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        try:
            win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass
        win.configure(background="#0b0614")
        try:
            win.lift()
            win.focus_force()
        except Exception:
            pass

        cv = tk.Canvas(win, width=w, height=h, highlightthickness=0, bd=0, background="#0b0614")
        cv.pack(fill="both", expand=True)

        img_item = cv.create_image(w // 2, h // 2, anchor="center")
        headline = f"{actor}"
        subline = f"took #{int(rank)} on Top 3 Best Packs!"
        base_headline_size = max(30, min(96, int(h * 0.10)))
        base_subline_size = max(18, min(54, int(h * 0.05)))
        try:
            import tkinter.font as tkfont

            head_size = int(base_headline_size)
            while head_size > 22:
                f = tkfont.Font(family="Segoe UI Semibold", size=head_size)
                if f.measure(headline) <= int(w * 0.90):
                    break
                head_size -= 2
            sub_size = int(base_subline_size)
            while sub_size > 14:
                f = tkfont.Font(family="Segoe UI Semibold", size=sub_size)
                if f.measure(subline) <= int(w * 0.92):
                    break
                sub_size -= 1
        except Exception:
            head_size = int(base_headline_size)
            sub_size = int(base_subline_size)

        top_margin = int(h * 0.14)
        bottom_margin = int(h * 0.08)
        gap = max(18, int(h * 0.03))

        headline_ids: tuple[int, int] | None = None
        subline_ids: tuple[int, int] | None = None
        text_width = int(w * 0.92)

        attempt = 0
        while attempt < 10:
            if headline_ids is not None:
                try:
                    cv.delete(headline_ids[0])
                    cv.delete(headline_ids[1])
                except Exception:
                    pass
                headline_ids = None
            if subline_ids is not None:
                try:
                    cv.delete(subline_ids[0])
                    cv.delete(subline_ids[1])
                except Exception:
                    pass
                subline_ids = None

            headline_shadow = cv.create_text(
                w // 2 + 3,
                top_margin + 3,
                text=headline,
                fill="#0b0614",
                font=("Segoe UI Semibold", int(head_size)),
                anchor="n",
                justify="center",
                width=text_width,
            )
            headline_main = cv.create_text(
                w // 2,
                top_margin,
                text=headline,
                fill="#f5f3ff",
                font=("Segoe UI Semibold", int(head_size)),
                anchor="n",
                justify="center",
                width=text_width,
            )
            headline_ids = (headline_shadow, headline_main)

            hb = None
            try:
                hb = cv.bbox(headline_main)
            except Exception:
                hb = None
            if not hb:
                hb = (0, top_margin, w, top_margin + int(head_size))

            sub_y = int(hb[3] + gap)
            sub_shadow = cv.create_text(
                w // 2 + 2,
                sub_y + 2,
                text=subline,
                fill="#0b0614",
                font=("Segoe UI Semibold", int(sub_size)),
                anchor="n",
                justify="center",
                width=text_width,
            )
            sub_main = cv.create_text(
                w // 2,
                sub_y,
                text=subline,
                fill="#ddd6fe",
                font=("Segoe UI Semibold", int(sub_size)),
                anchor="n",
                justify="center",
                width=text_width,
            )
            subline_ids = (sub_shadow, sub_main)

            sb = None
            try:
                sb = cv.bbox(sub_main)
            except Exception:
                sb = None

            if sb and sb[3] <= (h - bottom_margin):
                break

            head_size = max(22, int(head_size * 0.90))
            sub_size = max(14, int(sub_size * 0.92))
            attempt += 1

        keep_on_top_after: dict[str, Optional[str]] = {"id": None}

        def close() -> None:
            if keep_on_top_after["id"] is not None:
                try:
                    win.after_cancel(keep_on_top_after["id"])
                except Exception:
                    pass
                keep_on_top_after["id"] = None
            after_id = fireworks_runtime.get("after_id")
            if after_id is not None:
                try:
                    win.after_cancel(after_id)
                except Exception:
                    pass
                fireworks_runtime["after_id"] = None
            if fireworks_runtime.get("win") is win:
                fireworks_runtime["win"] = None
                fireworks_runtime["cv"] = None
                fireworks_runtime["img_item"] = None
                fireworks_runtime["frames"] = []
                fireworks_runtime["delays"] = []
            try:
                win.destroy()
            except Exception:
                pass

        def keep_on_top() -> None:
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return
            try:
                win.attributes("-topmost", True)
                win.lift()
            except Exception:
                pass
            keep_on_top_after["id"] = win.after(350, keep_on_top)

        keep_on_top()

        win.bind("<Escape>", lambda e: close())
        win.bind("<Button-1>", lambda e: close())

        frames, delays = _load_fireworks_frames(fireworks_path, w, h)
        if not frames:
            close()
            show_toast("firework(s).gif failed to load.", "warn")
            return

        fireworks_runtime["win"] = win
        fireworks_runtime["cv"] = cv
        fireworks_runtime["img_item"] = img_item
        fireworks_runtime["frames"] = frames
        fireworks_runtime["delays"] = delays
        fireworks_runtime["frame_index"] = 0
        fireworks_runtime["w"] = w
        fireworks_runtime["h"] = h
        fireworks_runtime["path"] = fireworks_path
        fireworks_runtime["after_id"] = None

        def step() -> None:
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return
            cur_frames = fireworks_runtime.get("frames") or []
            if not cur_frames:
                fireworks_runtime["after_id"] = win.after(90, step)
                return
            idx = int(fireworks_runtime.get("frame_index") or 0) % len(cur_frames)
            try:
                cv.itemconfigure(img_item, image=cur_frames[idx])
            except Exception:
                pass
            delay = 90
            cur_delays = fireworks_runtime.get("delays") or []
            if cur_delays and len(cur_delays) == len(cur_frames):
                delay = int(cur_delays[idx])
            fireworks_runtime["frame_index"] = idx + 1
            fireworks_runtime["after_id"] = win.after(max(10, delay), step)

        step()

        ms = int(max(1000, min(30000, int(float(st.celebration_seconds) * 1000))))
        win.after(ms, close)

    bg_color = "#0f0a1a"
    card_color = "#f5f3ff"
    text_color = "#2e1065"
    accent_color = "#c4b5fd"

    root.configure(background=bg_color)
    style.configure("TFrame", background=card_color)
    style.configure("TLabel", background=card_color, foreground=text_color)
    style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground=text_color, rowheight=28)
    style.map("Treeview", background=[("selected", "#ddd6fe")], foreground=[("selected", text_color)])
    style.configure("Treeview.Heading", background=card_color, foreground=text_color)
    style.map("TButton", background=[("active", "#ddd6fe")])
    style.configure("Accent.TButton", background=accent_color, foreground=text_color, padding=(10, 7))
    style.map("Accent.TButton", background=[("active", "#ddd6fe"), ("pressed", "#c4b5fd")])

    canvas = tk.Canvas(root, background=bg_color, highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    bg_image: Optional[tk.PhotoImage] = None
    bg_frames: list[tk.PhotoImage] = []
    bg_frame_delays: list[int] = []
    bg_frame_index = 0
    bg_item: Optional[int] = None
    bg_after_id: Optional[str] = None
    bg_pil_frames: list[Any] = []
    bg_pil_delays: list[int] = []
    bg_pil_static: Optional[Any] = None
    bg_resize_after_id: Optional[str] = None
    pillow: dict[str, Any] = {}

    preferred_files = ["background.gif", "background.png", "eeveelutions.gif", "eeveelutions.png"]
    fallback_files: list[str] = []
    try:
        candidates: list[tuple[int, str]] = []
        for base_idx, base in enumerate(asset_dirs):
            try:
                for fn in os.listdir(base):
                    lower = fn.lower()
                    if lower.endswith((".gif", ".png")):
                        candidates.append((base_idx, os.path.join(base, fn)))
            except Exception:
                continue

        def _fallback_key(item: tuple[int, str]) -> tuple[int, int, float, str]:
            base_idx, path = item
            name = os.path.basename(path).lower()
            name_score = 9
            if "background" in name:
                name_score = 0
            elif "eeveelutions" in name:
                name_score = 1
            elif "eevee" in name:
                name_score = 2
            try:
                mtime = float(os.path.getmtime(path))
            except Exception:
                mtime = 0.0
            return (base_idx, name_score, -mtime, name)

        candidates.sort(key=_fallback_key)
        fallback_files = [p for _, p in candidates]
    except Exception:
        fallback_files = []

    bg_file: Optional[str] = None
    for candidate in preferred_files:
        for base in asset_dirs:
            p = os.path.join(base, candidate)
            if os.path.isfile(p):
                bg_file = p
                break
        if bg_file is not None:
            break
    if bg_file is None:
        for p in fallback_files:
            if os.path.isfile(p):
                bg_file = p
                break

    if bg_file is not None:
        try:
            pillow_ok = False
            try:
                from PIL import Image, ImageOps, ImageSequence, ImageTk  # type: ignore

                pillow["Image"] = Image
                pillow["ImageOps"] = ImageOps
                pillow["ImageSequence"] = ImageSequence
                pillow["ImageTk"] = ImageTk
                pillow_ok = True
            except Exception:
                pillow_ok = False

            if pillow_ok and bg_file.lower().endswith(".gif"):
                try:
                    Image = pillow["Image"]
                    ImageSequence = pillow["ImageSequence"]
                    im = Image.open(bg_file)
                    composed = None
                    for frame in ImageSequence.Iterator(im):
                        rgba = frame.convert("RGBA")
                        if composed is None:
                            composed = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
                        try:
                            composed.alpha_composite(rgba)
                        except Exception:
                            composed.paste(rgba, (0, 0), rgba)
                        bg_pil_frames.append(composed.copy())
                        duration = int(frame.info.get("duration", 90))
                        duration = max(10, min(duration, 5000))
                        bg_pil_delays.append(duration)
                except Exception as e:
                    bg_pil_frames = []
                    bg_pil_delays = []
                    show_toast(f"GIF load failed: {e}", "warn")
            elif pillow_ok and bg_file.lower().endswith(".png"):
                try:
                    Image = pillow["Image"]
                    bg_pil_static = Image.open(bg_file).convert("RGBA")
                except Exception as e:
                    bg_pil_static = None
                    show_toast(f"Background image failed to load: {e}", "warn")
            else:
                if bg_file.lower().endswith(".gif"):
                    i = 0
                    while True:
                        try:
                            bg_frames.append(tk.PhotoImage(file=bg_file, format=f"gif -index {i}"))
                            bg_frame_delays.append(90)
                            i += 1
                        except tk.TclError:
                            break
                    if bg_frames:
                        bg_image = bg_frames[0]
                    else:
                        bg_image = tk.PhotoImage(file=bg_file)
                    show_toast("Tip: install Pillow for smoother GIF colors/frames.", "info")
                else:
                    bg_image = tk.PhotoImage(file=bg_file)
        except Exception as e:
            bg_image = None
            bg_frames = []
            bg_frame_delays = []
            show_toast(f"Background image failed to load: {e}", "warn")

    def rebuild_background(target_w: int, target_h: int) -> None:
        nonlocal bg_image, bg_frames, bg_frame_delays, bg_frame_index
        if target_w <= 2 or target_h <= 2:
            return

        if bg_pil_frames:
            Image = pillow.get("Image")
            ImageOps = pillow.get("ImageOps")
            ImageTk = pillow.get("ImageTk")
            if Image is None or ImageOps is None or ImageTk is None:
                return
            try:
                resampling = getattr(Image, "Resampling", None)
                method = resampling.LANCZOS if resampling is not None else Image.LANCZOS
            except Exception:
                method = Image.BICUBIC

            frames: list[tk.PhotoImage] = []
            for frame in bg_pil_frames:
                fitted = ImageOps.fit(frame, (target_w, target_h), method=method)
                frames.append(ImageTk.PhotoImage(fitted))
            bg_frames = frames
            bg_frame_delays = bg_pil_delays[:] if len(bg_pil_delays) == len(bg_frames) else [90] * len(bg_frames)
            if bg_frames:
                bg_frame_index = min(bg_frame_index, len(bg_frames) - 1)
                bg_image = bg_frames[bg_frame_index]
                if bg_item is not None:
                    canvas.itemconfigure(bg_item, image=bg_image)
            return

        if bg_pil_static is not None:
            Image = pillow.get("Image")
            ImageOps = pillow.get("ImageOps")
            ImageTk = pillow.get("ImageTk")
            if Image is None or ImageOps is None or ImageTk is None:
                return
            try:
                resampling = getattr(Image, "Resampling", None)
                method = resampling.LANCZOS if resampling is not None else Image.LANCZOS
            except Exception:
                method = Image.BICUBIC
            fitted = ImageOps.fit(bg_pil_static, (target_w, target_h), method=method)
            bg_frames = []
            bg_frame_delays = []
            bg_image = ImageTk.PhotoImage(fitted)
            if bg_item is not None:
                canvas.itemconfigure(bg_item, image=bg_image)

    if bg_pil_frames:
        bg_frame_delays = bg_pil_delays[:] if len(bg_pil_delays) == len(bg_pil_frames) else [90] * len(bg_pil_frames)
        bg_image = None
    elif bg_pil_static is not None:
        bg_image = None

    if bg_image is not None:
        bg_item = canvas.create_image(0, 0, image=bg_image, anchor="center")

        if len(bg_frames) > 1:
            def animate_bg() -> None:
                nonlocal bg_frame_index, bg_after_id
                if bg_item is None:
                    return
                bg_frame_index = (bg_frame_index + 1) % len(bg_frames)
                canvas.itemconfigure(bg_item, image=bg_frames[bg_frame_index])
                delay = 90
                if bg_frame_delays and len(bg_frame_delays) == len(bg_frames):
                    delay = bg_frame_delays[bg_frame_index]
                bg_after_id = root.after(delay, animate_bg)

            animate_bg()
    elif bg_pil_frames or bg_pil_static is not None:
        bg_item = canvas.create_image(0, 0, anchor="center")
        root.after(0, lambda: rebuild_background(int(canvas.winfo_width()), int(canvas.winfo_height())))
        if bg_pil_frames:
            def animate_bg() -> None:
                nonlocal bg_frame_index, bg_after_id
                if bg_item is None or not bg_frames:
                    bg_after_id = root.after(90, animate_bg)
                    return
                bg_frame_index = (bg_frame_index + 1) % len(bg_frames)
                canvas.itemconfigure(bg_item, image=bg_frames[bg_frame_index])
                delay = 90
                if bg_frame_delays and len(bg_frame_delays) == len(bg_frames):
                    delay = bg_frame_delays[bg_frame_index]
                bg_after_id = root.after(delay, animate_bg)

            animate_bg()

    card_win = tk.Toplevel(root)
    card_win.withdraw()
    try:
        card_win.overrideredirect(True)
    except Exception:
        pass
    try:
        card_win.transient(root)
    except Exception:
        pass
    try:
        card_win.attributes("-alpha", 0.97)
    except Exception:
        pass
    try:
        card_win.attributes("-toolwindow", True)
    except Exception:
        pass

    card = ttk.Frame(card_win, padding=16)
    card.pack(fill="both", expand=True)
    card.columnconfigure(0, weight=1)
    card.columnconfigure(1, weight=2)
    card.rowconfigure(1, weight=1)

    card_suspend: dict[str, int] = {"count": 0}

    def _with_card_hidden(fn: Any) -> Any:
        try:
            card_suspend["count"] += 1
            card_win.withdraw()
            root.update_idletasks()
        except Exception:
            pass
        try:
            return fn()
        finally:
            try:
                card_suspend["count"] = max(0, int(card_suspend["count"]) - 1)
            except Exception:
                card_suspend["count"] = 0
            if card_suspend["count"] == 0:
                try:
                    card_win.deiconify()
                    card_win.lift()
                    root.lift()
                except Exception:
                    pass
                try:
                    schedule_sync()
                except Exception:
                    pass

    def on_canvas_resize(event: Any) -> None:
        nonlocal bg_resize_after_id
        w = int(event.width)
        h = int(event.height)
        if bg_item is not None:
            canvas.coords(bg_item, w // 2, h // 2)
        if bg_pil_frames or bg_pil_static is not None:
            if bg_resize_after_id is not None:
                try:
                    root.after_cancel(bg_resize_after_id)
                except Exception:
                    pass
            bg_resize_after_id = root.after(120, lambda: rebuild_background(w, h))

    canvas.bind("<Configure>", on_canvas_resize)

    pending_sync: dict[str, Optional[str]] = {"id": None}

    def sync_card_geometry() -> None:
        if card_suspend["count"] > 0:
            try:
                card_win.withdraw()
            except Exception:
                pass
            return
        try:
            if root.state() == "iconic":
                card_win.withdraw()
                return
        except Exception:
            pass

        try:
            w = int(root.winfo_width())
            h = int(root.winfo_height())
            x = int(root.winfo_rootx())
            y = int(root.winfo_rooty())
        except Exception:
            return

        card_w = max(820, min(w - 120, 1100))
        card_h = max(520, min(h - 120, 760))
        card_x = x + max(0, (w - card_w) // 2)
        card_y = y + max(0, (h - card_h) // 2)
        try:
            card_win.geometry(f"{card_w}x{card_h}+{card_x}+{card_y}")
            card_win.deiconify()
        except Exception:
            pass

    def schedule_sync() -> None:
        if pending_sync["id"] is not None:
            return
        pending_sync["id"] = root.after(0, run_sync)

    def run_sync() -> None:
        pending_sync["id"] = None
        sync_card_geometry()

    root.bind("<Configure>", lambda event: schedule_sync())

    header = ttk.Frame(card)
    header.grid(row=0, column=0, columnspan=2, sticky="ew")
    header.columnconfigure(0, weight=1)

    title = ttk.Label(header, text=APP_NAME, font=header_font, foreground="#6d28d9")
    title.grid(row=0, column=0, sticky="w")

    opacity_row = ttk.Frame(header)
    opacity_row.grid(row=1, column=0, sticky="w", pady=(8, 0))
    ttk.Label(opacity_row, text="Card opacity").grid(row=0, column=0, sticky="w", padx=(0, 8))
    opacity_var = tk.DoubleVar(value=0.97)
    opacity_value = tk.StringVar(value="97%")

    def on_opacity_changed(value: str) -> None:
        try:
            v = float(value)
        except Exception:
            return
        pct = max(0.0, min(1.0, v))
        opacity_value.set(f"{int(round(pct * 100))}%")
        try:
            card_win.attributes("-alpha", pct)
        except Exception:
            pass

    opacity_scale = ttk.Scale(opacity_row, from_=0.2, to=1.0, variable=opacity_var, command=on_opacity_changed)
    opacity_scale.grid(row=0, column=1, sticky="w")
    ttk.Label(opacity_row, textvariable=opacity_value).grid(row=0, column=2, sticky="w", padx=(8, 0))

    top1_name = tk.StringVar(value="—")
    top1_total = tk.StringVar(value="0")
    top2_name = tk.StringVar(value="—")
    top2_total = tk.StringVar(value="0")
    top3_name = tk.StringVar(value="—")
    top3_total = tk.StringVar(value="0")

    leaderboard_box = ttk.Frame(header, padding=(12, 6))
    leaderboard_box.grid(row=0, column=1, sticky="e")
    leaderboard_box.columnconfigure(0, weight=1)
    leaderboard_box.columnconfigure(1, weight=0)
    ttk.Label(leaderboard_box, text="🏆 Top 3 Best Packs").grid(row=0, column=0, columnspan=2, sticky="e")

    ttk.Label(leaderboard_box, text="1.").grid(row=1, column=0, sticky="e", padx=(0, 8))
    ttk.Label(leaderboard_box, textvariable=top1_name, font=("Segoe UI Semibold", 12)).grid(row=1, column=1, sticky="e")
    ttk.Label(leaderboard_box, textvariable=top1_total, font=("Segoe UI Semibold", 14)).grid(row=2, column=1, sticky="e")

    ttk.Label(leaderboard_box, text="2.").grid(row=3, column=0, sticky="e", padx=(0, 8))
    ttk.Label(leaderboard_box, textvariable=top2_name).grid(row=3, column=1, sticky="e")
    ttk.Label(leaderboard_box, textvariable=top2_total).grid(row=4, column=1, sticky="e")

    ttk.Label(leaderboard_box, text="3.").grid(row=5, column=0, sticky="e", padx=(0, 8))
    ttk.Label(leaderboard_box, textvariable=top3_name).grid(row=5, column=1, sticky="e")
    ttk.Label(leaderboard_box, textvariable=top3_total).grid(row=6, column=1, sticky="e")

    left = ttk.Frame(card)
    left.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
    left.rowconfigure(1, weight=1)
    left.columnconfigure(0, weight=1)

    ttk.Label(left, text="👥 Players").grid(row=0, column=0, sticky="w", pady=(0, 8))

    players_tree = ttk.Treeview(
        left,
        columns=("name", "pack", "best"),
        show="headings",
        selectmode="browse",
        height=16,
    )
    players_tree.heading("name", text="Player")
    players_tree.heading("pack", text="Pack HP")
    players_tree.heading("best", text="Best Pack")
    players_tree.column("name", width=220, anchor="w")
    players_tree.column("pack", width=90, anchor="e")
    players_tree.column("best", width=90, anchor="e")
    players_tree.grid(row=1, column=0, sticky="nsew")

    vsb = ttk.Scrollbar(left, orient="vertical", command=players_tree.yview)
    players_tree.configure(yscrollcommand=vsb.set)
    vsb.grid(row=1, column=1, sticky="ns")

    controls = ttk.Frame(left)
    controls.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    for i in range(4):
        controls.columnconfigure(i, weight=1)

    player_sort: dict[str, Any] = {"col": "pack", "desc": True}

    def _top3_names_with_override(override: Optional[tuple[str, int]] = None) -> list[str]:
        items: list[tuple[str, int]] = []
        for name, p in st.players.items():
            best = int(p.best_pack_total)
            if override is not None and name == override[0]:
                best = int(override[1])
            items.append((name, best))
        items.sort(key=lambda x: (-x[1], x[0].lower()))
        return [name for name, _ in items[:3]]

    def _confirm_top_spot_takeover(actor: str, new_best: int) -> bool:
        old_top3 = _top3_names_with_override(None)
        new_top3 = _top3_names_with_override((actor, int(new_best)))

        if actor not in new_top3:
            return True

        old_rank = old_top3.index(actor) + 1 if actor in old_top3 else None
        new_rank = new_top3.index(actor) + 1
        if old_rank is not None and new_rank >= old_rank:
            return True

        displaced = None
        if 1 <= new_rank <= len(old_top3):
            displaced = old_top3[new_rank - 1]
            if displaced == actor:
                displaced = None

        dlg = tk.Toplevel(card_win)
        dlg.title("Top Spot Alert")
        try:
            dlg.transient(card_win)
        except Exception:
            pass
        try:
            dlg.lift()
        except Exception:
            pass

        result: dict[str, bool] = {"ok": False}

        wrapper = ttk.Frame(dlg, padding=14)
        wrapper.pack(fill="both", expand=True)
        wrapper.columnconfigure(0, weight=1)

        msg = f"{actor} is about to take #{new_rank} with Best Pack {int(new_best)}."
        if displaced:
            msg = f"{msg}\nDisplacing: {displaced}"

        ttk.Label(wrapper, text=msg, wraplength=420, justify="left").grid(row=0, column=0, sticky="w")

        btns = ttk.Frame(wrapper)
        btns.grid(row=1, column=0, sticky="e", pady=(12, 0))

        def take() -> None:
            result["ok"] = True
            try:
                dlg.destroy()
            except Exception:
                pass

        def deny() -> None:
            result["ok"] = False
            try:
                dlg.destroy()
            except Exception:
                pass

        ttk.Button(btns, text="❌ Deny", command=deny).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btns, text="✅ Take", command=take, style="Accent.TButton").grid(row=0, column=1)

        try:
            dlg.grab_set()
        except Exception:
            pass
        try:
            dlg.wait_window(dlg)
        except Exception:
            pass
        if result["ok"]:
            try:
                root.after(0, lambda: show_fireworks(actor, new_rank))
            except Exception:
                pass
        return bool(result["ok"])

    def update_top3_display() -> None:
        items = [(name, p.best_pack_total) for name, p in st.players.items()]
        items.sort(key=lambda x: (-x[1], x[0].lower()))
        winners = items[:3]
        while len(winners) < 3:
            winners.append(("—", 0))
        (n1, t1), (n2, t2), (n3, t3) = winners
        top1_name.set(n1)
        top1_total.set(str(int(t1)))
        top2_name.set(n2)
        top2_total.set(str(int(t2)))
        top3_name.set(n3)
        top3_total.set(str(int(t3)))

    def apply_player_sort(col: str) -> None:
        if player_sort["col"] == col:
            player_sort["desc"] = not bool(player_sort["desc"])
        else:
            player_sort["col"] = col
            player_sort["desc"] = True
        refresh_players(select_name=selected_player_name())

    players_tree.heading("name", text="Player", command=lambda: apply_player_sort("name"))
    players_tree.heading("pack", text="Pack HP", command=lambda: apply_player_sort("pack"))
    players_tree.heading("best", text="Best Pack", command=lambda: apply_player_sort("best"))

    def refresh_players(select_name: Optional[str] = None) -> None:
        for item in players_tree.get_children():
            players_tree.delete(item)

        items: list[tuple[str, PlayerState]] = list(st.players.items())
        col = str(player_sort.get("col", "pack"))
        desc = bool(player_sort.get("desc", True))
        if col == "name":
            items.sort(key=lambda kv: kv[0].lower(), reverse=desc)
        elif col == "best":
            items.sort(key=lambda kv: (kv[1].best_pack_total, kv[0].lower()), reverse=desc)
        else:
            items.sort(key=lambda kv: (kv[1].current_total, kv[0].lower()), reverse=desc)

        for name, p in items:
            players_tree.insert("", "end", iid=name, values=(name, p.current_total, p.best_pack_total))

        if select_name and select_name in st.players:
            st.selected_player = select_name
        st.normalize_selection()

        if st.selected_player:
            players_tree.selection_set(st.selected_player)
            players_tree.focus(st.selected_player)
        else:
            players_tree.selection_remove(players_tree.selection())
            players_tree.focus("")

        update_top3_display()
        try:
            _sync_background_top3(force=False)
        except Exception:
            try:
                bg_sync_status.set("Background sync failed.")
            except Exception:
                pass

    def persist() -> None:
        _state_to_disk(state_path, st)

    def selected_player_name() -> str:
        sel = players_tree.selection()
        if sel:
            return sel[0]
        return st.selected_player

    def set_selected(name: str) -> None:
        if name in st.players:
            st.selected_player = name
        elif not name:
            st.selected_player = ""
        else:
            return
        persist()

    def add_player() -> None:
        name = _with_card_hidden(lambda: simpledialog.askstring(APP_NAME, "New player name:", parent=root))
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in st.players:
            show_toast("That player already exists.", "warn")
            return
        st.players[name] = PlayerState(name=name)
        st.selected_player = name
        persist()
        refresh_players(select_name=name)
        players_tree.event_generate("<<TreeviewSelect>>")

    def rename_player() -> None:
        old = selected_player_name()
        if old not in st.players:
            return
        name = _with_card_hidden(lambda: simpledialog.askstring(APP_NAME, "Rename player to:", initialvalue=old, parent=root))
        if not name:
            return
        name = name.strip()
        if not name or name == old:
            return
        if name in st.players:
            show_toast("That name is already used.", "warn")
            return
        p = st.players.pop(old)
        p.name = name
        st.players[name] = p
        if st.selected_player == old:
            st.selected_player = name
        persist()
        refresh_players(select_name=name)
        players_tree.event_generate("<<TreeviewSelect>>")

    def remove_player() -> None:
        name = selected_player_name()
        if name not in st.players:
            return
        if not _with_card_hidden(lambda: messagebox.askyesno(APP_NAME, f"Remove {name}?", parent=root)):
            return
        st.players.pop(name, None)
        if st.selected_player == name:
            st.selected_player = ""
        st.normalize_selection()
        persist()
        refresh_players()
        refresh_packs_view()
        players_tree.event_generate("<<TreeviewSelect>>")

    def clear_all_players() -> None:
        if not st.players:
            return
        if not _with_card_hidden(lambda: messagebox.askyesno(APP_NAME, "Clear all players and start a new KOTH?", parent=root)):
            return
        st.players = {}
        st.selected_player = ""
        persist()
        refresh_players()
        refresh_packs_view()
        players_tree.event_generate("<<TreeviewSelect>>")

    def reset_selected_pack() -> None:
        name = selected_player_name()
        if not name or name not in st.players:
            return
        p = st.players.get(name)
        if p and int(p.current_total) > int(p.best_pack_total):
            if not _confirm_top_spot_takeover(name, int(p.current_total)):
                show_toast("Denied.", "warn")
                return
        updated = _reset_pack(st, name)
        persist()
        refresh_players(select_name=name)
        refresh_packs_view()
        if updated:
            show_toast("New best pack saved.", "ok")
        else:
            show_toast("Pack reset.", "info")

    def undo_selected() -> None:
        name = selected_player_name()
        if not name or name not in st.players:
            return
        last = _undo(st, name)
        persist()
        refresh_players(select_name=name)
        if last is None:
            show_toast("Nothing to undo.", "warn")
        else:
            show_toast(f"Undid {last}.", "info")

    packs_win: Optional[tk.Toplevel] = None
    packs_tree: Optional[ttk.Treeview] = None
    packs_total = tk.StringVar(value="")

    def refresh_packs_view() -> None:
        nonlocal packs_tree
        if packs_tree is None:
            return
        for item in packs_tree.get_children():
            packs_tree.delete(item)
        sel_name = selected_player_name()
        p = st.players.get(sel_name)
        if not p:
            packs_total.set("Pack history: no player selected")
            return
        rows: list[tuple[int, int, str]] = []
        for r in p.packs:
            rows.append((int(r.pack_no), int(r.total), str(r.ended_at)))
        rows.sort(key=lambda x: x[0])
        for pack_no, total, ended_at in rows:
            packs_tree.insert("", "end", iid=str(pack_no), values=(pack_no, total, ended_at))
        packs_total.set(f"Pack history for {sel_name}: {len(rows)} packs")

    def open_packs_window() -> None:
        nonlocal packs_win, packs_tree
        if packs_win is not None:
            try:
                if packs_win.winfo_exists():
                    packs_win.lift()
                    packs_win.focus_force()
                    refresh_packs_view()
                    return
            except Exception:
                packs_win = None
                packs_tree = None

        packs_win = tk.Toplevel(card_win)
        packs_win.title("Pack History")
        packs_win.minsize(640, 420)
        try:
            packs_win.transient(card_win)
        except Exception:
            pass
        try:
            packs_win.lift()
        except Exception:
            pass

        def on_close_packs() -> None:
            nonlocal packs_win, packs_tree
            try:
                packs_win.destroy()
            except Exception:
                pass
            packs_win = None
            packs_tree = None

        packs_win.protocol("WM_DELETE_WINDOW", on_close_packs)

        wrapper = ttk.Frame(packs_win, padding=12)
        wrapper.pack(fill="both", expand=True)
        wrapper.rowconfigure(1, weight=1)
        wrapper.columnconfigure(0, weight=1)

        ttk.Label(wrapper, textvariable=packs_total).grid(row=0, column=0, sticky="w", pady=(0, 10))

        packs_tree = ttk.Treeview(
            wrapper,
            columns=("pack_no", "total", "ended_at"),
            show="headings",
            selectmode="browse",
        )
        packs_tree.heading("pack_no", text="Pack #")
        packs_tree.heading("total", text="Total")
        packs_tree.heading("ended_at", text="Ended At (UTC)")
        packs_tree.column("pack_no", width=80, anchor="e")
        packs_tree.column("total", width=80, anchor="e")
        packs_tree.column("ended_at", width=320, anchor="w")
        packs_tree.grid(row=1, column=0, sticky="nsew")

        packs_vsb = ttk.Scrollbar(wrapper, orient="vertical", command=packs_tree.yview)
        packs_tree.configure(yscrollcommand=packs_vsb.set)
        packs_vsb.grid(row=1, column=1, sticky="ns")

        refresh_packs_view()

    add_player_btn = ttk.Button(controls, text="➕ Add", command=add_player, style="Accent.TButton")
    rename_player_btn = ttk.Button(controls, text="✏ Rename", command=rename_player)
    remove_player_btn = ttk.Button(controls, text="🗑 Remove", command=remove_player)
    clear_all_btn = ttk.Button(controls, text="🧹 Clear All", command=clear_all_players)
    add_player_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    rename_player_btn.grid(row=0, column=1, sticky="ew", padx=(0, 6))
    remove_player_btn.grid(row=0, column=2, sticky="ew", padx=(0, 6))
    clear_all_btn.grid(row=0, column=3, sticky="ew")

    pack_controls = ttk.Frame(left)
    pack_controls.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    pack_controls.columnconfigure(0, weight=1)
    pack_controls.columnconfigure(1, weight=1)
    pack_controls.columnconfigure(2, weight=1)
    reset_pack_btn = ttk.Button(pack_controls, text="🆕 New Pack", command=reset_selected_pack)
    undo_btn = ttk.Button(pack_controls, text="↩ Undo", command=undo_selected)
    packs_btn = ttk.Button(pack_controls, text="📦 Packs", command=open_packs_window)
    reset_pack_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    undo_btn.grid(row=0, column=1, sticky="ew", padx=(0, 6))
    packs_btn.grid(row=0, column=2, sticky="ew")

    right = ttk.Frame(card)
    right.grid(row=1, column=1, sticky="nsew")
    right.rowconfigure(1, weight=1)
    right.columnconfigure(0, weight=1)

    ttk.Label(right, text="Mode").grid(row=0, column=0, sticky="w", pady=(0, 8))

    notebook = ttk.Notebook(right)
    notebook.grid(row=1, column=0, sticky="nsew")

    keyboard_tab = ttk.Frame(notebook, padding=14)
    celebration_tab = ttk.Frame(notebook, padding=14)
    sync_tab = ttk.Frame(notebook, padding=14)
    notebook.add(keyboard_tab, text="⌨ Keyboard")
    notebook.add(celebration_tab, text="🎆 Celebration")
    notebook.add(sync_tab, text="🔄 Background Sync")

    keyboard_tab.columnconfigure(0, weight=1)
    keyboard_tab.columnconfigure(1, weight=0)

    active_player_label = tk.StringVar(value="")
    ttk.Label(keyboard_tab, textvariable=active_player_label).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

    entry = ttk.Entry(keyboard_tab)
    entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))
    entry.insert(0, "Type HP and press Add")

    status_line = tk.StringVar(value="")
    status = ttk.Label(keyboard_tab, textvariable=status_line, font=mono_font)
    status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

    toast_label_keyboard = ttk.Label(
        keyboard_tab,
        textvariable=toast_text,
        foreground="#7c3aed",
        wraplength=720,
    )
    toast_label_keyboard.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
    toast_labels.append(toast_label_keyboard)

    celebration_tab.columnconfigure(0, weight=1)
    celebration_tab.columnconfigure(1, weight=0)

    celebration_enabled_var = tk.BooleanVar(value=bool(st.celebration_enabled))
    celebration_seconds_var = tk.DoubleVar(value=float(st.celebration_seconds))
    celebration_seconds_label = tk.StringVar(value=f"{int(round(float(st.celebration_seconds)))}s")
    celebration_monitor_var = tk.StringVar(value="")
    celebration_fireworks_var = tk.StringVar(value=(str(st.celebration_fireworks_gif or "").strip() or "Auto"))

    last_bg_sync_top3: Optional[list[str]] = None
    bg_sync_status = tk.StringVar(value="")
    bg_sync_enabled_var = tk.BooleanVar(value=bool(st.bg_sync_enabled))
    bg_sync_layout_name_var = tk.StringVar(value=str(st.bg_sync_layout_path or ""))
    bg_sync_monitor_var = tk.StringVar(value=str(int(st.bg_sync_monitor)))
    bg_sync_top1_var = tk.StringVar(value=str(int(st.bg_sync_top1_layer_id)) if int(st.bg_sync_top1_layer_id) else "")
    bg_sync_top2_var = tk.StringVar(value=str(int(st.bg_sync_top2_layer_id)) if int(st.bg_sync_top2_layer_id) else "")
    bg_sync_top3_var = tk.StringVar(value=str(int(st.bg_sync_top3_layer_id)) if int(st.bg_sync_top3_layer_id) else "")
    bg_creator_proc: Optional[subprocess.Popen] = None

    layout_monitor_keys: list[str] = []
    layout_text_layer_values: dict[str, list[str]] = {}
    
    # Store layouts loaded from cycle file: monitor_idx -> [ {name, payload} ]
    available_layouts: dict[int, list[dict]] = {}

    def _get_bg_creator_app_data_path() -> Optional[str]:
        base = os.environ.get("APPDATA")
        if base:
            root = os.path.join(base, "BackgroundCreator")
        else:
            root = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "BackgroundCreator")
        
        if os.path.isdir(root):
            return root
        return None

    def _load_available_layouts() -> None:
        nonlocal available_layouts
        available_layouts = {}
        root = _get_bg_creator_app_data_path()
        if not root:
            return
        
        cycles_path = os.path.join(root, "layout_cycles.json")
        if not os.path.isfile(cycles_path):
            return
            
        try:
            data = _load_json(cycles_path)
            monitors = data.get("monitors", {})
            if isinstance(monitors, dict):
                for k, v in monitors.items():
                    try:
                        midx = int(k)
                    except:
                        continue
                    
                    layouts_raw = v.get("layouts", [])
                    if not isinstance(layouts_raw, list):
                        continue
                        
                    loaded_list = []
                    for l in layouts_raw:
                        if not isinstance(l, dict):
                            continue
                        name = str(l.get("name", "Layout"))
                        payload = l.get("payload", {})
                        loaded_list.append({"name": name, "payload": payload})
                    
                    if loaded_list:
                        available_layouts[midx] = loaded_list
        except Exception:
            pass

    def _top3_payload() -> list[str]:
        items = [(name, p.best_pack_total) for name, p in st.players.items()]
        items.sort(key=lambda x: (-x[1], x[0].lower()))
        winners = items[:3]
        while len(winners) < 3:
            winners.append(("—", 0))
        return [
            f"{str(winners[0][0])} - {int(winners[0][1])}",
            f"{str(winners[1][0])} - {int(winners[1][1])}",
            f"{str(winners[2][0])} - {int(winners[2][1])}",
        ]

    def _parse_leading_int(text: str) -> int:
        m = re.match(r"\s*(-?\d+)", str(text))
        if not m:
            return 0
        try:
            v = int(m.group(1))
        except Exception:
            return 0
        return v if v > 0 else 0

    def _layout_monitors_map(layout: dict[str, Any]) -> dict[str, dict[str, Any]]:
        monitors_raw = layout.get("monitors", {})
        if isinstance(monitors_raw, dict):
            out: dict[str, dict[str, Any]] = {}
            for k, v in monitors_raw.items():
                if not isinstance(v, dict):
                    continue
                key = str(k).strip()
                if key:
                    out[key] = v
            return out
        if isinstance(monitors_raw, list):
            out2: dict[str, dict[str, Any]] = {}
            for m in monitors_raw:
                if not isinstance(m, dict):
                    continue
                idx = m.get("index", None)
                if isinstance(idx, bool):
                    continue
                try:
                    idx_int = int(idx)
                except Exception:
                    continue
                out2[str(idx_int)] = m
            return out2
        return {}

    def _layout_text_layer_choices(layout: dict[str, Any], monitor_key: str) -> list[str]:
        monitors_map = _layout_monitors_map(layout)
        mdata = monitors_map.get(str(monitor_key), None)
        if not isinstance(mdata, dict):
            return []
        layers = mdata.get("layers", [])
        if not isinstance(layers, list):
            return []
        out: list[str] = []
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            kind = str(layer.get("kind", "") or layer.get("type", "") or "").lower()
            if kind != "text":
                continue
            lid = layer.get("id", None)
            try:
                lid_int = int(lid)
            except Exception:
                continue
            if lid_int <= 0:
                continue
            preview = str(layer.get("text", "") or "")
            preview = preview.replace("\n", " ").strip()
            if len(preview) > 36:
                preview = preview[:36].rstrip() + "…"
            out.append(f"{lid_int} — {preview}")
        out.sort(key=lambda s: _parse_leading_int(s))
        return out

    def _find_text_layer(layout: dict[str, Any], monitor_key: str, layer_id: int) -> Optional[dict[str, Any]]:
        monitors_map = _layout_monitors_map(layout)
        mdata = monitors_map.get(str(monitor_key), None)
        if not isinstance(mdata, dict):
            return None
        layers = mdata.get("layers", [])
        if not isinstance(layers, list):
            return None
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            kind = str(layer.get("kind", "") or layer.get("type", "") or "").lower()
            if kind != "text":
                continue
            try:
                lid = int(layer.get("id", 0))
            except Exception:
                continue
            if lid == int(layer_id):
                return layer
        return None

    def _refresh_bg_sync_layout_info() -> None:
        nonlocal layout_monitor_keys, layout_text_layer_values
        
        # 1. Reload layouts from disk
        _load_available_layouts()
        
        layout_monitor_keys = []
        layout_text_layer_values = {}
        
        # 2. Populate monitor keys from available_layouts
        keys = []
        if available_layouts:
            for k in available_layouts.keys():
                keys.append(str(k))
        keys.sort(key=lambda s: int(s))
        
        if not keys:
            bg_sync_status.set("No layouts found in BackgroundCreator cycle config.")
            bg_monitor_combo.configure(values=[])
            bg_layout_combo.configure(values=[])
            bg_top1_combo.configure(values=[])
            bg_top2_combo.configure(values=[])
            bg_top3_combo.configure(values=[])
            return

        layout_monitor_keys = keys
        bg_monitor_combo.configure(values=layout_monitor_keys)
        
        # 3. Ensure valid monitor selection
        cur_m = str(int(st.bg_sync_monitor))
        if cur_m not in layout_monitor_keys:
            cur_m = layout_monitor_keys[0]
            st.bg_sync_monitor = int(cur_m)
            bg_sync_monitor_var.set(cur_m)
            persist()
        try:
            bg_monitor_combo.set(cur_m)
        except Exception:
            pass

        # 4. Populate layout dropdown for this monitor
        monitor_idx = int(cur_m)
        layouts_list = available_layouts.get(monitor_idx, [])
        layout_names = [l["name"] for l in layouts_list]
        bg_layout_combo.configure(values=layout_names)
        
        # 5. Ensure valid layout selection
        cur_layout_name = str(st.bg_sync_layout_path or "")
        if cur_layout_name not in layout_names and layout_names:
            # Try to keep current if it matches fuzzily? Or just default to first?
            # User wants to "choose the one i want to edit", so let's default to first if invalid
            cur_layout_name = layout_names[0]
            st.bg_sync_layout_path = cur_layout_name
            bg_sync_layout_name_var.set(cur_layout_name)
            persist()
        elif not layout_names:
            cur_layout_name = ""
            st.bg_sync_layout_path = ""
            bg_sync_layout_name_var.set("")
            persist()
            
        try:
            bg_layout_combo.set(cur_layout_name)
        except Exception:
            pass

        # 6. Get layers from the selected layout payload
        target_layout = None
        for l in layouts_list:
            if l["name"] == cur_layout_name:
                target_layout = l["payload"]
                break
        
        if not target_layout:
             # Layout payload missing?
             bg_top1_combo.configure(values=[])
             bg_top2_combo.configure(values=[])
             bg_top3_combo.configure(values=[])
             return

        # Use dummy layout wrapper to reuse existing helper
        # helper expects layout -> monitors -> key -> layers
        # But we have the monitor payload directly (which has 'layers' key usually at root of payload in some versions,
        # or it is the monitor object itself). 
        # BackgroundCreator _serialize_monitor_layout returns: { "background": ..., "layers": [...] }
        # So we can wrap it.
        dummy_layout = {
            "monitors": {
                cur_m: target_layout
            }
        }

        choices = _layout_text_layer_choices(dummy_layout, cur_m)
        layout_text_layer_values[cur_m] = choices
        bg_top1_combo.configure(values=choices)
        bg_top2_combo.configure(values=choices)
        bg_top3_combo.configure(values=choices)

        def _set_combo_from_id(combo: Any, var: tk.StringVar, layer_id: int) -> None:
            if layer_id <= 0:
                var.set("")
                try:
                    combo.set("")
                except Exception:
                    pass
                return
            target = None
            for s in choices:
                if _parse_leading_int(s) == int(layer_id):
                    target = s
                    break
            if target is None:
                var.set("")
                try:
                    combo.set("")
                except Exception:
                    pass
                return
            var.set(target)
            try:
                combo.set(target)
            except Exception:
                pass

        _set_combo_from_id(bg_top1_combo, bg_sync_top1_var, int(st.bg_sync_top1_layer_id))
        _set_combo_from_id(bg_top2_combo, bg_sync_top2_var, int(st.bg_sync_top2_layer_id))
        _set_combo_from_id(bg_top3_combo, bg_sync_top3_var, int(st.bg_sync_top3_layer_id))

        bg_sync_status.set("Ready.")

    def _bg_creator_script_path(layout_path: str) -> Optional[str]:
        if bool(getattr(sys, "frozen", False)):
            return None
        layout_dir = os.path.dirname(os.path.abspath(str(layout_path)))
        candidates = [
            os.path.join(layout_dir, "desktop_background_creator.py"),
            os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "BackgroundCreator", "desktop_background_creator.py")),
        ]
        for p in candidates:
            if p and os.path.isfile(p):
                return p
        return None

    def _restart_bg_creator(layout_path: str, monitor_index: int) -> tuple[bool, str]:
        nonlocal bg_creator_proc
        script_path = _bg_creator_script_path(layout_path)
        if not script_path:
            return False, "Background auto-update unavailable (desktop_background_creator.py not found)."

        cmd = [
            sys.executable,
            script_path,
            "run",
            "--layout",
            str(layout_path),
            "--desktop",
            "--monitor",
            str(int(monitor_index)),
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

        try:
            if bg_creator_proc is not None and bg_creator_proc.poll() is None:
                try:
                    bg_creator_proc.terminate()
                except Exception:
                    pass
                try:
                    bg_creator_proc.wait(timeout=1.5)
                except Exception:
                    try:
                        bg_creator_proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            bg_creator_proc = subprocess.Popen(
                cmd,
                cwd=os.path.dirname(script_path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception:
            bg_creator_proc = None
            return False, "Failed to start Background Creator run mode."

        return True, "OK"

    def _send_bg_creator_ipc(message: str) -> bool:
        try:
            from PySide6.QtNetwork import QLocalSocket
        except Exception:
            return False

        sock = QLocalSocket()
        sock.connectToServer("Eevees_BG_Creator_single_instance")
        if not sock.waitForConnected(150):
            return False
        try:
            msg = f"{message}\n".encode("utf-8", errors="ignore")
            sock.write(msg)
            sock.flush()
            sock.waitForBytesWritten(150)
        except Exception:
            try:
                sock.disconnectFromServer()
            except Exception:
                pass
            return False
        try:
            sock.disconnectFromServer()
        except Exception:
            pass
        return True

    def _reload_bg_creator_preview(layout_path: str) -> bool:
        return _send_bg_creator_ipc(f"load_layout {str(layout_path)}")

    def _sync_background_top3(force: bool = False) -> None:
        nonlocal last_bg_sync_top3
        if not bool(st.bg_sync_enabled):
            bg_sync_status.set("Disabled.")
            return
        
        path_or_name = str(st.bg_sync_layout_path or "").strip()
        if not path_or_name:
            bg_sync_status.set("Select a layout.")
            return
            
        top3 = _top3_payload()
        if not force and last_bg_sync_top3 == top3:
            return
            
        monitor_key = str(int(st.bg_sync_monitor))
        monitor_idx = int(st.bg_sync_monitor)
        
        layout = None
        is_file = False
        
        # Try to find in available_layouts first (cycle layout)
        found_cycle_layout = None
        if available_layouts:
            layouts_list = available_layouts.get(monitor_idx, [])
            for l in layouts_list:
                if l["name"] == path_or_name:
                    found_cycle_layout = l
                    break
        
        if found_cycle_layout:
            # Construct a layout object structure that matches what _find_text_layer expects
            # _find_text_layer expects: layout -> monitors -> key -> layers
            # found_cycle_layout['payload'] is the monitor payload
            layout = {
                "monitors": {
                    monitor_key: found_cycle_layout["payload"]
                }
            }
        elif os.path.isfile(path_or_name):
            is_file = True
            layout = _load_json(path_or_name)
        else:
            bg_sync_status.set("Layout not found.")
            return

        if not isinstance(layout, dict):
            bg_sync_status.set("Layout could not be loaded.")
            return

        targets: list[tuple[int, str]] = [
            (int(st.bg_sync_top1_layer_id), top3[0]),
            (int(st.bg_sync_top2_layer_id), top3[1]),
            (int(st.bg_sync_top3_layer_id), top3[2]),
        ]
        
        changed = False
        missing: list[str] = []
        updates_list: list[dict[str, Any]] = []

        for layer_id, text in targets:
            if layer_id <= 0:
                continue
            layer = _find_text_layer(layout, monitor_key, int(layer_id))
            if layer is None:
                missing.append(str(layer_id))
                continue
            
            cur = str(layer.get("text", "") or "")
            if cur != str(text):
                layer["text"] = str(text)
                changed = True
            
            # Add to updates list for IPC
            updates_list.append({"id": layer_id, "text": text})
            
        if missing:
            bg_sync_status.set(f"Missing text layer(s): {', '.join(missing)}")
            return
            
        should_refresh_bg = bool(changed) or bool(force)
        
        if changed:
            if is_file:
                try:
                    _save_json(path_or_name, layout)
                except Exception:
                    bg_sync_status.set("Failed to write layout JSON.")
                    return

            try:
                update_payload = {
                    "layout_path": str(path_or_name),
                    "monitor": int(st.bg_sync_monitor),
                    "updates": updates_list
                }
                
                cmd = f"update_text_layers {json.dumps(update_payload)}"
                _send_bg_creator_ipc(cmd)
            except Exception:
                pass

            bg_sync_status.set(f"Synced at {_utc_now_iso()}")
        else:
            bg_sync_status.set("No changes needed.")
            
        if should_refresh_bg and is_file:
            if not _reload_bg_creator_preview(path_or_name):
                should_restart_bg = (bg_creator_proc is None) or (bg_creator_proc.poll() is not None)
                if should_restart_bg:
                    ok, err = _restart_bg_creator(path_or_name, int(st.bg_sync_monitor))
                    if not ok:
                        bg_sync_status.set(err)
        
        last_bg_sync_top3 = list(top3)

    def _reset_bg_sync_snapshot_and_sync() -> None:
        nonlocal last_bg_sync_top3
        last_bg_sync_top3 = None
        _sync_background_top3(force=True)

    def refresh_celebration_monitors() -> None:
        nonlocal monitors
        monitors = _list_monitors()
        labels = _monitor_labels(monitors)
        monitor_combo.configure(values=labels)
        idx = int(st.celebration_monitor) if isinstance(st.celebration_monitor, int) else 0
        if idx < 0:
            idx = 0
        if idx >= len(labels):
            idx = 0
        st.celebration_monitor = idx
        try:
            monitor_combo.current(idx)
        except Exception:
            pass

    fireworks_choice_to_path: dict[str, str] = {}

    def refresh_celebration_fireworks() -> None:
        nonlocal fireworks_choice_to_path
        choices = ["Auto"]
        mapping: dict[str, str] = {}
        seen: set[str] = set()
        for base in asset_dirs:
            try:
                for fn in os.listdir(base):
                    name = str(fn)
                    lower = name.lower()
                    if not lower.endswith(".gif"):
                        continue
                    if "firework" not in lower and "celebrat" not in lower and "party" not in lower:
                        continue
                    p = os.path.join(base, fn)
                    if not os.path.isfile(p):
                        continue
                    if lower in seen:
                        continue
                    seen.add(lower)
                    choices.append(name)
                    mapping[name] = p
            except Exception:
                pass
        fireworks_choice_to_path = mapping
        fireworks_combo.configure(values=choices)

        cur = str(st.celebration_fireworks_gif or "").strip() or "Auto"
        match = "Auto"
        for c in choices:
            if str(c).lower() == cur.lower():
                match = str(c)
                break
        st.celebration_fireworks_gif = match
        celebration_fireworks_var.set(match)
        try:
            fireworks_combo.set(match)
        except Exception:
            pass

    def on_celebration_toggle() -> None:
        st.celebration_enabled = bool(celebration_enabled_var.get())
        persist()

    def on_celebration_seconds_changed(value: str) -> None:
        try:
            v = float(value)
        except Exception:
            return
        if v < 1.0:
            v = 1.0
        if v > 30.0:
            v = 30.0
        st.celebration_seconds = float(v)
        celebration_seconds_label.set(f"{int(round(v))}s")
        persist()

    def on_celebration_monitor_changed(event: Any) -> None:
        try:
            idx = int(monitor_combo.current())
        except Exception:
            idx = 0
        if idx < 0:
            idx = 0
        if idx >= len(monitors):
            idx = 0
        st.celebration_monitor = idx
        persist()

    def on_celebration_fireworks_changed(event: Any) -> None:
        picked = str(fireworks_combo.get() or "").strip() or "Auto"
        st.celebration_fireworks_gif = picked
        persist()
        _swap_running_fireworks()

    ttk.Label(celebration_tab, text="Celebration popup", font=("Segoe UI Semibold", 14)).grid(row=0, column=0, sticky="w")
    ttk.Checkbutton(celebration_tab, text="Enable fireworks on confirmed Top 3 takeover", variable=celebration_enabled_var, command=on_celebration_toggle).grid(row=1, column=0, sticky="w", pady=(8, 0))
    ttk.Label(celebration_tab, text="Put `fireworks.gif` next to the exe or in `assets`.", wraplength=680).grid(row=2, column=0, sticky="w", pady=(8, 0))

    monitor_row = ttk.Frame(celebration_tab)
    monitor_row.grid(row=3, column=0, sticky="ew", pady=(16, 0))
    monitor_row.columnconfigure(1, weight=1)
    ttk.Label(monitor_row, text="Monitor").grid(row=0, column=0, sticky="w", padx=(0, 10))
    monitor_combo = ttk.Combobox(monitor_row, state="readonly", textvariable=celebration_monitor_var)
    monitor_combo.grid(row=0, column=1, sticky="ew")
    monitor_combo.bind("<<ComboboxSelected>>", on_celebration_monitor_changed)
    ttk.Button(monitor_row, text="🔄 Refresh", command=refresh_celebration_monitors).grid(row=0, column=2, sticky="e", padx=(10, 0))

    fireworks_row = ttk.Frame(celebration_tab)
    fireworks_row.grid(row=4, column=0, sticky="ew", pady=(14, 0))
    fireworks_row.columnconfigure(1, weight=1)
    ttk.Label(fireworks_row, text="Fireworks GIF").grid(row=0, column=0, sticky="w", padx=(0, 10))
    fireworks_combo = ttk.Combobox(fireworks_row, state="readonly", textvariable=celebration_fireworks_var)
    fireworks_combo.grid(row=0, column=1, sticky="ew")
    fireworks_combo.bind("<<ComboboxSelected>>", on_celebration_fireworks_changed)
    ttk.Button(fireworks_row, text="🔄 Refresh", command=refresh_celebration_fireworks).grid(row=0, column=2, sticky="e", padx=(10, 0))

    dur_row = ttk.Frame(celebration_tab)
    dur_row.grid(row=5, column=0, sticky="ew", pady=(14, 0))
    dur_row.columnconfigure(1, weight=1)
    ttk.Label(dur_row, text="Duration").grid(row=0, column=0, sticky="w", padx=(0, 10))
    ttk.Scale(dur_row, from_=1.0, to=30.0, variable=celebration_seconds_var, command=on_celebration_seconds_changed).grid(row=0, column=1, sticky="ew")
    ttk.Label(dur_row, textvariable=celebration_seconds_label).grid(row=0, column=2, sticky="e", padx=(10, 0))

    def test_celebration() -> None:
        name = selected_player_name() or "Player"
        show_fireworks(name, 1)

    ttk.Button(celebration_tab, text="🎆 Test Celebration", command=test_celebration, style="Accent.TButton").grid(row=6, column=0, sticky="w", pady=(18, 0))
    refresh_celebration_monitors()
    refresh_celebration_fireworks()

    sync_tab.columnconfigure(0, weight=1)
    sync_tab.columnconfigure(1, weight=0)

    def on_bg_sync_toggle() -> None:
        st.bg_sync_enabled = bool(bg_sync_enabled_var.get())
        persist()
        _reset_bg_sync_snapshot_and_sync()

    def on_bg_sync_browse() -> None:
        initial = str(st.bg_sync_layout_path or "").strip()
        initial_dir = os.path.dirname(initial) if initial else os.path.dirname(os.path.abspath(state_path))
        picked = _with_card_hidden(
            lambda: filedialog.askopenfilename(
                parent=root,
                title="Choose Background Creator layout JSON",
                initialdir=initial_dir,
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
        )
        if not picked:
            return
        st.bg_sync_layout_path = str(picked)
        bg_sync_layout_name_var.set(str(picked))
        persist()
        _refresh_bg_sync_layout_info()
        _reset_bg_sync_snapshot_and_sync()

    def on_bg_sync_refresh() -> None:
        _refresh_bg_sync_layout_info()

    def on_bg_sync_now() -> None:
        _sync_background_top3(force=True)

    def on_bg_sync_monitor_changed(event: Any) -> None:
        key = str(bg_monitor_combo.get() or "").strip()
        try:
            m = int(key)
        except Exception:
            m = 0
        if m < 0:
            m = 0
        st.bg_sync_monitor = int(m)
        bg_sync_monitor_var.set(str(int(m)))
        # When monitor changes, layout selection might need reset if the new monitor has different layouts
        # _refresh_bg_sync_layout_info will handle repopulating layouts and picking a default if current invalid
        persist()
        _refresh_bg_sync_layout_info()
        _reset_bg_sync_snapshot_and_sync()

    def on_bg_sync_layout_changed(event: Any) -> None:
        # When user picks a layout from the dropdown
        picked = str(bg_layout_combo.get() or "")
        if picked != st.bg_sync_layout_path:
            st.bg_sync_layout_path = picked
            bg_sync_layout_name_var.set(picked)
            persist()
            _refresh_bg_sync_layout_info()
            _reset_bg_sync_snapshot_and_sync()

    def _apply_layer_choice(rank: int, choice: str) -> None:
        lid = _parse_leading_int(choice)
        if rank == 1:
            st.bg_sync_top1_layer_id = int(lid)
        elif rank == 2:
            st.bg_sync_top2_layer_id = int(lid)
        else:
            st.bg_sync_top3_layer_id = int(lid)
        persist()
        _reset_bg_sync_snapshot_and_sync()

    def on_bg_sync_top1_changed(event: Any) -> None:
        _apply_layer_choice(1, str(bg_top1_combo.get() or ""))

    def on_bg_sync_top2_changed(event: Any) -> None:
        _apply_layer_choice(2, str(bg_top2_combo.get() or ""))

    def on_bg_sync_top3_changed(event: Any) -> None:
        _apply_layer_choice(3, str(bg_top3_combo.get() or ""))

    ttk.Label(sync_tab, text="Background Creator JSON sync", font=("Segoe UI Semibold", 14)).grid(row=0, column=0, sticky="w")
    ttk.Checkbutton(sync_tab, text="Enable Top 3 name sync to layout JSON", variable=bg_sync_enabled_var, command=on_bg_sync_toggle).grid(
        row=1, column=0, sticky="w", pady=(8, 0)
    )
    ttk.Label(sync_tab, textvariable=bg_sync_status, wraplength=680).grid(row=2, column=0, sticky="w", pady=(8, 0))

    monitor_row2 = ttk.Frame(sync_tab)
    monitor_row2.grid(row=3, column=0, sticky="ew", pady=(12, 0))
    monitor_row2.columnconfigure(1, weight=1)
    ttk.Label(monitor_row2, text="Layout monitor").grid(row=0, column=0, sticky="w", padx=(0, 10))
    bg_monitor_combo = ttk.Combobox(monitor_row2, state="readonly", textvariable=bg_sync_monitor_var)
    bg_monitor_combo.grid(row=0, column=1, sticky="ew")
    bg_monitor_combo.bind("<<ComboboxSelected>>", on_bg_sync_monitor_changed)
    ttk.Button(monitor_row2, text="🔄 Refresh", command=on_bg_sync_refresh).grid(row=0, column=2, sticky="e", padx=(10, 0))

    path_row = ttk.Frame(sync_tab)
    path_row.grid(row=4, column=0, sticky="ew", pady=(16, 0))
    path_row.columnconfigure(1, weight=1)
    ttk.Label(path_row, text="Cycle Layout").grid(row=0, column=0, sticky="w", padx=(0, 10))
    # Replace Entry/Browse with ComboBox for layout name
    bg_layout_combo = ttk.Combobox(path_row, state="readonly", textvariable=bg_sync_layout_name_var)
    bg_layout_combo.grid(row=0, column=1, sticky="ew")
    bg_layout_combo.bind("<<ComboboxSelected>>", on_bg_sync_layout_changed)
    # ttk.Entry(path_row, textvariable=bg_sync_layout_path_var).grid(row=0, column=1, sticky="ew")
    # ttk.Button(path_row, text="📄 Browse", command=on_bg_sync_browse, style="Accent.TButton").grid(row=0, column=2, sticky="e", padx=(10, 0))

    layers_box = ttk.Frame(sync_tab)
    layers_box.grid(row=5, column=0, sticky="ew", pady=(12, 0))
    layers_box.columnconfigure(1, weight=1)
    layers_box.columnconfigure(3, weight=1)
    layers_box.columnconfigure(5, weight=1)

    ttk.Label(layers_box, text="#1 layer").grid(row=0, column=0, sticky="w", padx=(0, 10))
    bg_top1_combo = ttk.Combobox(layers_box, state="readonly", textvariable=bg_sync_top1_var)
    bg_top1_combo.grid(row=0, column=1, sticky="ew", padx=(0, 12))
    bg_top1_combo.bind("<<ComboboxSelected>>", on_bg_sync_top1_changed)

    ttk.Label(layers_box, text="#2 layer").grid(row=0, column=2, sticky="w", padx=(0, 10))
    bg_top2_combo = ttk.Combobox(layers_box, state="readonly", textvariable=bg_sync_top2_var)
    bg_top2_combo.grid(row=0, column=3, sticky="ew", padx=(0, 12))
    bg_top2_combo.bind("<<ComboboxSelected>>", on_bg_sync_top2_changed)

    ttk.Label(layers_box, text="#3 layer").grid(row=0, column=4, sticky="w", padx=(0, 10))
    bg_top3_combo = ttk.Combobox(layers_box, state="readonly", textvariable=bg_sync_top3_var)
    bg_top3_combo.grid(row=0, column=5, sticky="ew")
    bg_top3_combo.bind("<<ComboboxSelected>>", on_bg_sync_top3_changed)

    ttk.Button(sync_tab, text="🚀 Sync Now", command=on_bg_sync_now, style="Accent.TButton").grid(row=6, column=0, sticky="w", pady=(18, 0))
    _refresh_bg_sync_layout_info()
    if bool(st.bg_sync_enabled) and str(st.bg_sync_layout_path or "").strip():
        _sync_background_top3(force=True)

    def clear_entry_hint(event: Any) -> None:
        if entry.get().strip() == "Type HP and press Add":
            entry.delete(0, "end")

    entry.bind("<FocusIn>", clear_entry_hint)

    def set_active_labels() -> None:
        name = selected_player_name()
        p = st.players.get(name)
        if not p:
            active_player_label.set("Selected: —")
            status_line.set("")
            update_top3_display()
            return
        active_player_label.set(f"Selected: {p.name}")
        update_top3_display()
        hs_at = p.best_pack_at or "n/a"
        status_line.set(f"Pack: {p.current_total} | Best: {p.best_pack_total} ({hs_at})")

    def add_from_text(text: str) -> None:
        name = selected_player_name()
        p = st.players.get(name)
        action, value = _parse_input(text)
        if action == "add":
            if not p:
                show_toast("Add a player first.", "warn")
                return
            if value is None:
                show_toast("Could not parse a number.", "warn")
                return
            candidate_current = int(p.current_total) + int(value)
            if candidate_current > int(p.best_pack_total):
                if not _confirm_top_spot_takeover(name, candidate_current):
                    show_toast("Denied.", "warn")
                    return
            updated = _add_hp(st, name, value)
            persist()
            refresh_players(select_name=name)
            set_active_labels()
            if updated:
                show_toast("New best pack saved.", "ok")
            return
        if action == "set_total":
            if not p:
                show_toast("Add a player first.", "warn")
                return
            if value is None:
                show_toast("Could not parse a number.", "warn")
                return
            candidate_current = int(value)
            if candidate_current > int(p.best_pack_total):
                if not _confirm_top_spot_takeover(name, candidate_current):
                    show_toast("Denied.", "warn")
                    return
            updated = _set_total(st, name, value)
            persist()
            refresh_players(select_name=name)
            set_active_labels()
            if updated:
                show_toast("New best pack saved.", "ok")
            return
        if action == "reset":
            if not p:
                show_toast("Add a player first.", "warn")
                return
            reset_selected_pack()
            return
        if action == "undo":
            if not p:
                show_toast("Add a player first.", "warn")
                return
            undo_selected()
            return
        if action == "show_high":
            if not p:
                show_toast("Add a player first.", "warn")
                return
            show_toast(f"{p.name} best pack: {p.best_pack_total}", "info")
            return
        if action == "status":
            set_active_labels()
            return
        if action == "quit":
            root.destroy()
            return
        if action != "noop":
            show_toast("Try a number, or: reset/undo/status/high/set/quit", "warn")

    def on_add_clicked() -> None:
        text = entry.get().strip()
        if not text or text == "Type HP and press Add":
            return
        add_from_text(text)
        entry.delete(0, "end")

    def on_entry_enter(event: Any) -> None:
        on_add_clicked()

    entry.bind("<Return>", on_entry_enter)
    add_hp_btn = ttk.Button(keyboard_tab, text="➕ Add HP", command=on_add_clicked, style="Accent.TButton")
    add_hp_btn.grid(row=1, column=1, sticky="ew")

    def update_enabled_state() -> None:
        has_player = bool(st.players) and bool(st.players.get(selected_player_name()))
        rename_player_btn.configure(state=("normal" if has_player else "disabled"))
        remove_player_btn.configure(state=("normal" if has_player else "disabled"))
        reset_pack_btn.configure(state=("normal" if has_player else "disabled"))
        undo_btn.configure(state=("normal" if has_player else "disabled"))
        packs_btn.configure(state=("normal" if st.players else "disabled"))
        add_hp_btn.configure(state=("normal" if has_player else "disabled"))
        entry.configure(state=("normal" if has_player else "disabled"))
        clear_all_btn.configure(state=("normal" if st.players else "disabled"))

    def on_player_selected(event: Any) -> None:
        sel = selected_player_name()
        set_selected(sel)
        set_active_labels()
        refresh_packs_view()
        update_enabled_state()

    players_tree.bind("<<TreeviewSelect>>", on_player_selected)

    def on_close() -> None:
        nonlocal bg_creator_proc
        if bg_after_id is not None:
            try:
                root.after_cancel(bg_after_id)
            except Exception:
                pass
        if pending_sync["id"] is not None:
            try:
                root.after_cancel(pending_sync["id"])
            except Exception:
                pass
        if bg_resize_after_id is not None:
            try:
                root.after_cancel(bg_resize_after_id)
            except Exception:
                pass
        try:
            if bg_creator_proc is not None and bg_creator_proc.poll() is None:
                try:
                    bg_creator_proc.terminate()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            card_win.destroy()
        except Exception:
            pass
        persist()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    refresh_players()
    set_active_labels()
    update_enabled_state()
    root.after(0, schedule_sync)
    if st.players:
        entry.focus_set()
    root.mainloop()
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="koth_calculator", description=APP_NAME)
    parser.add_argument("--ui", choices=("gui", "cli"), default="gui", help="Run the GUI or CLI.")
    parser.add_argument(
        "--state-file",
        default=STATE_FILE_NAME,
        help="Path to JSON state file.",
    )
    args = parser.parse_args(argv)

    if bool(getattr(sys, "frozen", False)) and args.state_file == STATE_FILE_NAME:
        state_path = os.path.join(os.path.dirname(sys.executable), STATE_FILE_NAME)
    else:
        state_path = os.path.abspath(args.state_file)
    if args.ui == "cli":
        return _run_cli(state_path)
    return _run_gui(state_path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

