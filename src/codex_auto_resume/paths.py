from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def home_dir() -> Path:
    return Path.home()


def default_codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    return home_dir() / ".codex"


def default_state_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (home_dir() / "AppData" / "Local"))
        return base / "vibcoding" / "codex-auto-resume"
    if sys.platform == "darwin":
        return home_dir() / "Library" / "Application Support" / "vibcoding" / "codex-auto-resume"
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(xdg).expanduser() if xdg else home_dir() / ".local" / "share"
    return root / "vibcoding" / "codex-auto-resume"


def sessions_dir(codex_home: Path) -> Path:
    return Path(codex_home) / "sessions"


def tool_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_codex_command(explicit: str | None = None) -> list[str]:
    if explicit:
        return _split_or_single(explicit)

    env_bin = os.environ.get("CODEX_BIN", "").strip()
    if env_bin:
        return _split_or_single(env_bin)

    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA") or (home_dir() / "AppData" / "Roaming"))
        cmd = appdata / "npm" / "codex.cmd"
        if cmd.exists():
            return [str(cmd)]
        js = appdata / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        node = shutil.which("node")
        if js.exists() and node:
            return [node, str(js)]

    which = shutil.which("codex")
    if which:
        if sys.platform == "win32" and which.lower().endswith(".ps1"):
            sibling = Path(which).with_suffix(".cmd")
            if sibling.exists():
                return [str(sibling)]
        return [which]

    mac_bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    if mac_bundled.exists():
        return [str(mac_bundled)]
    mac_codex_app = Path("/Applications/Codex.app/Contents/Resources/codex")
    if mac_codex_app.exists():
        return [str(mac_codex_app)]

    raise FileNotFoundError("找不到 codex 可执行文件，请把 Codex CLI 加入 PATH，或设置 CODEX_BIN")


def _split_or_single(value: str) -> list[str]:
    path = Path(value)
    if path.exists():
        return [str(path)]
    return [value]
