from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _pick(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    if number is None:
        return None
    return int(number)


@dataclass(frozen=True)
class QuotaWindow:
    used_percent: float | None = None
    resets_at: int | None = None
    window_minutes: int | None = None

    @classmethod
    def from_mapping(cls, raw: Any) -> QuotaWindow | None:
        if not isinstance(raw, dict):
            return None
        return cls(
            used_percent=_as_float(_pick(raw, "usedPercent", "used_percent")),
            resets_at=_as_int(_pick(raw, "resetsAt", "resets_at")),
            window_minutes=_as_int(_pick(raw, "windowDurationMins", "window_minutes")),
        )


@dataclass(frozen=True)
class QuotaSnapshot:
    primary: QuotaWindow | None = None
    secondary: QuotaWindow | None = None
    ordinary_usage_allowed: bool | None = None
    rate_limit_reached_type: str | None = None
    spend_control_reached: bool | None = None
    plan_type: str | None = None
    source: str = ""
    fetched_at: float = 0.0

    @property
    def windows(self) -> list[QuotaWindow]:
        return [w for w in (self.primary, self.secondary) if w is not None]


def parse_quota_payload(payload: Any, *, source: str = "", fetched_at: float = 0.0) -> QuotaSnapshot | None:
    if not isinstance(payload, dict):
        return None
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    snapshot = result.get("rateLimits") if isinstance(result.get("rateLimits"), dict) else None
    if snapshot is None:
        snapshot = result.get("rate_limits") if isinstance(result.get("rate_limits"), dict) else result
    if not isinstance(snapshot, dict):
        return None
    by_id = result.get("rateLimitsByLimitId")
    if isinstance(by_id, dict) and by_id:
        snapshot = by_id.get("codex") or next(iter(by_id.values()))
        if not isinstance(snapshot, dict):
            return None
    reached = _pick(snapshot, "rateLimitReachedType", "rate_limit_reached_type")
    return QuotaSnapshot(
        primary=QuotaWindow.from_mapping(snapshot.get("primary")),
        secondary=QuotaWindow.from_mapping(snapshot.get("secondary")),
        ordinary_usage_allowed=_as_bool(_pick(result, "ordinaryUsageAllowed", "ordinary_usage_allowed")),
        rate_limit_reached_type=str(reached) if reached else None,
        spend_control_reached=_as_bool(_pick(snapshot, "spendControlReached", "spend_control_reached")),
        plan_type=_pick(snapshot, "planType", "plan_type") or _pick(result, "planType", "plan_type"),
        source=source,
        fetched_at=fetched_at,
    )


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def blocked_windows(snapshot: QuotaSnapshot, ready_used_percent: float) -> list[QuotaWindow]:
    blocked: list[QuotaWindow] = []
    for window in snapshot.windows:
        if window.used_percent is not None and window.used_percent >= ready_used_percent:
            blocked.append(window)
    return blocked


def hint_reset_at(snapshot: QuotaSnapshot, ready_used_percent: float) -> int | None:
    stamps = [w.resets_at for w in blocked_windows(snapshot, ready_used_percent) if w.resets_at]
    if stamps:
        return max(stamps)
    stamps = [w.resets_at for w in snapshot.windows if w.resets_at]
    return min(stamps) if stamps else None


def quota_available(snapshot: QuotaSnapshot, ready_used_percent: float, now: float) -> tuple[bool, str]:
    if snapshot.spend_control_reached is True:
        return False, "spend-control"
    if snapshot.ordinary_usage_allowed is False:
        return False, "ordinary-usage-blocked"
    if snapshot.rate_limit_reached_type:
        return False, f"reached:{snapshot.rate_limit_reached_type}"
    blocked = blocked_windows(snapshot, ready_used_percent)
    if not blocked:
        if snapshot.windows or snapshot.ordinary_usage_allowed is True:
            return True, "available"
        return False, "quota-unknown"
    still_waiting = []
    for window in blocked:
        if window.resets_at and now >= window.resets_at:
            continue
        still_waiting.append(window)
    if still_waiting:
        return False, "window-exhausted"
    return True, "reset-time-passed"


def quota_recovered(
    previous: QuotaSnapshot | None,
    current: QuotaSnapshot,
    *,
    ready_used_percent: float,
    recovery_drop_percent: float,
    now: float,
) -> tuple[bool, str]:
    available, reason = quota_available(current, ready_used_percent, now)
    if available:
        return True, reason
    if previous is None:
        return False, reason
    for before, after in (
        (previous.primary, current.primary),
        (previous.secondary, current.secondary),
    ):
        if (
            before
            and after
            and before.used_percent is not None
            and after.used_percent is not None
            and before.used_percent >= ready_used_percent
            and (before.used_percent - after.used_percent) >= recovery_drop_percent
        ):
            return True, "early-reset"
    return False, reason
