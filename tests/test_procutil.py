from __future__ import annotations

import os
import unittest

from codex_auto_resume.procutil import process_running


class ProcessTests(unittest.TestCase):
    def test_current_pid_is_running(self) -> None:
        self.assertTrue(process_running(os.getpid()))

    def test_missing_pid_is_not_running(self) -> None:
        self.assertFalse(process_running(None))
        self.assertFalse(process_running(1_000_000_001))
