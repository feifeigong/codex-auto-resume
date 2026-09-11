from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from codex_auto_resume.config import AppConfig, DEFAULT_PROMPT, LEGACY_PROMPT, load_config
from codex_auto_resume.daemon import LiveQuota, tick
from codex_auto_resume.quota import parse_quota_payload, should_redeem_weekly_reset
from codex_auto_resume.redeem import try_redeem_weekly_reset
from codex_auto_resume.state import AppState
try:
    from fakes import FakeQuotaClient
except ImportError:  # pragma: no cover
    from tests.fakes import FakeQuotaClient

THREAD = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _iso(hours_ago: float = 1.0) -> str:
    stamp = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _cfg(root: Path, **overrides: object) -> AppConfig:
    cfg = AppConfig(
        codex_home=str(root / "codex"),
        state_dir=str(root / "state"),
        auto_discover=True,
        auto_redeem_weekly_reset=True,
        reset_credit_cooldown_seconds=600,
        ready_used_percent=99.0,
        recovery_drop_percent=20.0,
        max_auto_windows=1,
        lookback_hours=36,
        resume_prompt=DEFAULT_PROMPT,
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _write_waiting(codex_home: Path) -> None:
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    path = sessions / f"rollout-{THREAD}.jsonl"
    rows = [
        {
            "timestamp": _iso(2),
            "type": "session_meta",
            "payload": {"id": THREAD, "cwd": str(codex_home)},
        },
        {
            "timestamp": _iso(1),
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {
                        "used_percent": 100.0,
                        "window_minutes": 300,
                        "resets_at": 9_999_999_999,
                    },
                    "secondary": {
                        "used_percent": 100.0,
                        "window_minutes": 10080,
                        "resets_at": 9_999_999_999,
                    },
                },
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class FakeLiveQuota:
    def __init__(self, cfg: AppConfig, client: FakeQuotaClient) -> None:
        self.cfg = cfg
        self.client = client

    def read(self, now: float):
        return parse_quota_payload(
            self.client.read_rate_limits(include_credits=False),
            source="app-server",
            fetched_at=now,
        )

    def try_redeem(self, snapshot, state, now):
        return try_redeem_weekly_reset(
            cfg=self.cfg,
            snapshot=snapshot,
            state=state,
            now=now,
            client=self.client,
        )

    def close(self) -> None:
        return None


class RedeemDecisionTests(unittest.TestCase):
    def test_five_hour_full_weekly_remaining_does_not_redeem(self) -> None:
        snap = parse_quota_payload(
            {
                "rateLimits": {
                    "primary": {"usedPercent": 100, "windowDurationMins": 300},
                    "secondary": {"usedPercent": 31.4, "windowDurationMins": 10080},
                },
                "rateLimitResetCredits": {"availableCount": 2, "credits": [{"id": "c1", "status": "available"}]},
            }
        )
        assert snap is not None
        want, reason = should_redeem_weekly_reset(snap, 99.0)
        self.assertFalse(want)
        self.assertEqual(reason, "keep-weekly")

    def test_weekly_full_with_credit_wants_redeem(self) -> None:
        snap = parse_quota_payload(
            {
                "rateLimits": {
                    "primary": {"usedPercent": 100, "windowDurationMins": 300},
                    "secondary": {"usedPercent": 100, "windowDurationMins": 10080},
                },
                "rateLimitResetCredits": {"availableCount": 1, "credits": [{"id": "c1", "status": "available"}]},
            }
        )
        assert snap is not None
        want, reason = should_redeem_weekly_reset(snap, 99.0)
        self.assertTrue(want)
        self.assertEqual(reason, "weekly-exhausted")

    def test_weekly_full_without_credit_does_not_redeem(self) -> None:
        snap = parse_quota_payload(
            {
                "rateLimits": {
                    "primary": {"usedPercent": 100, "windowDurationMins": 300},
                    "secondary": {"usedPercent": 100, "windowDurationMins": 10080},
                },
                "rateLimitResetCredits": {"availableCount": 0, "credits": []},
            }
        )
        assert snap is not None
        want, reason = should_redeem_weekly_reset(snap, 99.0)
        self.assertFalse(want)
        self.assertEqual(reason, "weekly-exhausted-no-credit")

    def test_parse_reset_credits(self) -> None:
        snap = parse_quota_payload(
            {
                "rateLimits": {"primary": {"usedPercent": 10, "windowDurationMins": 300}},
                "rateLimitResetCredits": {
                    "availableCount": 2,
                    "credits": [{"id": "abc", "status": "available"}],
                },
            }
        )
        assert snap is not None
        self.assertEqual(snap.reset_credit_count, 2)
        self.assertEqual(snap.reset_credit_id, "abc")


class SimulatedRedeemTests(unittest.TestCase):
    def test_five_hour_only_never_calls_consume(self) -> None:
        client = FakeQuotaClient(primary_used=100, weekly_used=31.4, allow_consume=False)
        cfg = AppConfig(auto_redeem_weekly_reset=True)
        snap = parse_quota_payload(client.read_rate_limits(), source="fake", fetched_at=1)
        assert snap is not None
        after, note = try_redeem_weekly_reset(
            cfg=cfg,
            snapshot=snap,
            state=AppState(),
            now=10,
            client=client,
        )
        self.assertEqual(note, "")
        self.assertEqual(client.consume_calls, [])
        self.assertEqual(after.secondary.used_percent if after.secondary else None, 31.4)

    def test_tibo_already_reset_skips_consume(self) -> None:
        client = FakeQuotaClient(
            primary_used=100,
            weekly_used=100,
            allow_consume=False,
            tibo_on_credit_read=True,
        )
        cfg = AppConfig(auto_redeem_weekly_reset=True)
        snap = parse_quota_payload(client.read_rate_limits(), source="fake", fetched_at=1)
        assert snap is not None
        after, note = try_redeem_weekly_reset(
            cfg=cfg,
            snapshot=snap,
            state=AppState(),
            now=10,
            client=client,
        )
        self.assertEqual(note, "skip-tibo-already-reset")
        self.assertEqual(client.consume_calls, [])
        self.assertEqual(after.secondary.used_percent, 4.0)
        self.assertTrue(any(flag is True for flag in client.read_calls))

    def test_no_credit_skips_consume(self) -> None:
        client = FakeQuotaClient(primary_used=100, weekly_used=100, credits=0, allow_consume=False)
        cfg = AppConfig(auto_redeem_weekly_reset=True)
        snap = parse_quota_payload(client.read_rate_limits(), source="fake", fetched_at=1)
        assert snap is not None
        _after, note = try_redeem_weekly_reset(
            cfg=cfg,
            snapshot=snap,
            state=AppState(),
            now=10,
            client=client,
        )
        self.assertEqual(note, "skip-weekly-exhausted-no-credit")
        self.assertEqual(client.consume_calls, [])

    def test_weekly_exhausted_consumes_once_on_fake_client(self) -> None:
        client = FakeQuotaClient(primary_used=100, weekly_used=100, credits=1, allow_consume=True)
        cfg = AppConfig(auto_redeem_weekly_reset=True)
        state = AppState()
        snap = parse_quota_payload(client.read_rate_limits(), source="fake", fetched_at=1)
        assert snap is not None
        after, note = try_redeem_weekly_reset(
            cfg=cfg,
            snapshot=snap,
            state=state,
            now=10,
            client=client,
        )
        self.assertEqual(note, "redeemed:reset")
        self.assertEqual(client.consume_calls, ["sim-credit-1"])
        self.assertEqual(client.credits, 0)
        self.assertEqual(after.primary.used_percent, 0.0)
        self.assertEqual(after.secondary.used_percent, 0.0)
        self.assertEqual(state.last_reset_credit_id, "sim-credit-1")

        again, again_note = try_redeem_weekly_reset(
            cfg=cfg,
            snapshot=after,
            state=state,
            now=11,
            client=client,
        )
        self.assertEqual(again_note, "")
        self.assertEqual(len(client.consume_calls), 1)
        self.assertEqual(again.secondary.used_percent, 0.0)

    def test_failed_consume_enters_cooldown(self) -> None:
        client = FakeQuotaClient(
            primary_used=100,
            weekly_used=100,
            allow_consume=True,
            consume_error="simulated-deny",
        )
        cfg = AppConfig(reset_credit_cooldown_seconds=600)
        state = AppState()
        snap = parse_quota_payload(client.read_rate_limits(), source="fake", fetched_at=1)
        assert snap is not None
        _after, note = try_redeem_weekly_reset(
            cfg=cfg, snapshot=snap, state=state, now=100, client=client
        )
        self.assertTrue(note.startswith("redeem-failed:"))
        self.assertEqual(len(client.consume_calls), 1)

        _after, note = try_redeem_weekly_reset(
            cfg=cfg, snapshot=snap, state=state, now=200, client=client
        )
        self.assertEqual(note, "redeem-cooldown")
        self.assertEqual(len(client.consume_calls), 1)


class SimulatedDaemonTests(unittest.TestCase):
    @patch("codex_auto_resume.daemon.spawn_resume", side_effect=AssertionError("must not resume yet"))
    @patch("codex_auto_resume.daemon.process_running", return_value=False)
    def test_five_hour_wait_does_not_resume_or_consume(self, _running, _spawn) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            cfg = _cfg(root)
            _write_waiting(Path(cfg.codex_home))
            client = FakeQuotaClient(primary_used=100, weekly_used=40, allow_consume=False)
            state = tick(cfg, quota_reader=FakeLiveQuota(cfg, client))
            self.assertEqual(client.consume_calls, [])
            task = state.threads[THREAD]
            self.assertEqual(task.resumes, 0)
            self.assertNotEqual(task.status, "resumed")
            self.assertIsNone(state.last_quota.get("reset_credit_id"))

    @patch("codex_auto_resume.daemon.process_running", return_value=False)
    def test_weekly_redeem_then_resume_on_fake_client(self, _running) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            cfg = _cfg(root)
            _write_waiting(Path(cfg.codex_home))
            client = FakeQuotaClient(primary_used=100, weekly_used=100, credits=1, allow_consume=True)

            def fake_spawn(**kwargs):
                self.assertEqual(kwargs["thread_id"], THREAD)
                self.assertEqual(kwargs["prompt"], DEFAULT_PROMPT)
                self.assertNotIn("询问", kwargs["prompt"])
                return 4242, "exec-resume"

            with patch("codex_auto_resume.daemon.spawn_resume", side_effect=fake_spawn) as spawn:
                state = tick(cfg, quota_reader=FakeLiveQuota(cfg, client))

            self.assertEqual(client.consume_calls, ["sim-credit-1"])
            self.assertEqual(client.credits, 0)
            spawn.assert_called_once()
            task = state.threads[THREAD]
            self.assertEqual(task.status, "resumed")
            self.assertEqual(task.resumes, 1)
            self.assertEqual(state.last_reset_credit_note, "redeemed:reset")
            self.assertIsNone(state.last_quota.get("reset_credit_id"))

    def test_legacy_prompt_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "config.json"
            path.write_text(
                json.dumps({"resume_prompt": LEGACY_PROMPT, "codex_home": "D:/codex"}),
                encoding="utf-8",
            )
            cfg = load_config(path)
            self.assertEqual(cfg.resume_prompt, DEFAULT_PROMPT)
            self.assertNotIn("询问", cfg.resume_prompt)

    def test_live_quota_without_client_does_not_redeem(self) -> None:
        cfg = AppConfig()
        live = LiveQuota(cfg)
        self.assertIsNone(live.client)
        snap = parse_quota_payload(
            {
                "rateLimits": {
                    "primary": {"usedPercent": 100, "windowDurationMins": 300},
                    "secondary": {"usedPercent": 100, "windowDurationMins": 10080},
                }
            }
        )
        assert snap is not None
        after, note = live.try_redeem(snap, AppState(), 1)
        self.assertEqual(note, "")
        self.assertIs(after, snap)


if __name__ == "__main__":
    unittest.main()
