from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_auto_resume.state import load_state, save_state, upsert_thread


class StateTests(unittest.TestCase):
    def test_roundtrip_and_write_ahead_fields(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = load_state(root)
            upsert_thread(state, "abc", phase="submitting", status="resuming", resumes=0)
            save_state(root, state)
            again = load_state(root)
            self.assertEqual(again.threads["abc"].phase, "submitting")
            self.assertEqual(again.threads["abc"].status, "resuming")


if __name__ == "__main__":
    unittest.main()
