#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_auto_resume.cli import main
from codex_auto_resume.workspace_control import allow_background_watch

if __name__ == "__main__":
    if not allow_background_watch(sys.argv[1:]):
        raise SystemExit(0)
    raise SystemExit(main())
