from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_auto_resume.procutil import claim_watch_pid, process_running, release_watch_pid


class ProcessTests(unittest.TestCase):
    def test_current_pid_is_running(self) -> None:
        self.assertTrue(process_running(os.getpid()))

    def test_missing_pid_is_not_running(self) -> None:
        self.assertFalse(process_running(None))
        self.assertFalse(process_running(1_000_000_001))

    def test_watch_pid_rejects_other_live_instance(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "watch.pid"
            path.write_text("8\n", encoding="utf-8")
            with patch("codex_auto_resume.procutil.process_running", return_value=True):
                self.assertFalse(claim_watch_pid(path))

    def test_watch_pid_takes_over_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "watch.pid"
            path.write_text("1000000001\n", encoding="utf-8")
            self.assertTrue(claim_watch_pid(path))
            release_watch_pid(path)
