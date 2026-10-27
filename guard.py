"""Fair use for live AI questions (no Streamlit import, unit-testable).

- Pro fair-use cap: PRO_DAILY_AI_CAP fresh AI questions per user per exam_family per IST day.
  Question-bank practice is never capped.
- Speed check: requests faster than a human could read a question trigger a temporary cooldown
  (never a permanent ban); each trigger is logged as an abuse event.
- One active session per (user, exam_family): a newer sign-in takes over; older sessions stop AI.
"""
from __future__ import annotations

import datetime as dt
import uuid

PRO_DAILY_AI_CAP = 100
SPEED_WINDOW_S = 60
SPEED_MAX_IN_WINDOW = 8        # >= 8 AI requests within 60 s
MIN_HUMAN_GAP_S = 5
FAST_GAPS_IN_A_ROW = 4         # 4 consecutive gaps under 5 s
COOLDOWN_S = 10 * 60
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

FAIR_USE_NOTE = "Pro includes up to 100 fresh AI questions per day; question-bank practice is unlimited."
CAP_MESSAGE = ("You've used today's 100 fresh AI questions (Pro fair use). Question-bank practice is still "
               "unlimited, so here is a verified bank question. Fresh AI questions are back after midnight IST.")
COOLDOWN_MESSAGE = ("Whoa, that's faster than anyone can read a question! Fresh AI questions are paused for a "
                    "few minutes. Bank questions keep coming meanwhile.")
OTHER_DEVICE_MESSAGE = ("Signed in on another device. This session no longer gets fresh AI questions. "
                        "Sign out and sign in again here to continue on this device.")


def ist_today(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return now.astimezone(IST).date().isoformat()


def ai_used_today(guard_row: dict | None, now: dt.datetime | None = None) -> int:
    """AI questions used today (IST) from a usage_guard row; a row from an earlier day counts as 0."""
    g = guard_row or {}
    return int(g.get("ai_used") or 0) if str(g.get("ai_day") or "")[:10] == ist_today(now) else 0


def pro_cap_reached(used_today: int, cap: int = PRO_DAILY_AI_CAP) -> bool:
    return used_today >= cap


def too_fast(request_times: list[float], now: float) -> bool:
    """True if AI requests (epoch seconds, including this one) come faster than a human could use them."""
    recent = [t for t in request_times if now - t <= SPEED_WINDOW_S]
    if len(recent) >= SPEED_MAX_IN_WINDOW:
        return True
    times = sorted(request_times)[-(FAST_GAPS_IN_A_ROW + 1):]
    gaps = [b - a for a, b in zip(times, times[1:])]
    return len(gaps) == FAST_GAPS_IN_A_ROW and all(g < MIN_HUMAN_GAP_S for g in gaps)


def cooldown_until(now: float) -> float:
    return now + COOLDOWN_S


def in_cooldown(until, now: float) -> bool:
    if not until:
        return False
    if isinstance(until, str):  # timestamptz from the DB
        until = dt.datetime.fromisoformat(until.replace("Z", "+00:00")).timestamp()
    return float(until) > now


def new_session_token() -> str:
    return uuid.uuid4().hex


def session_is_current(stored_token: str | None, my_token: str | None) -> bool:
    """No stored token (feature not set up / not signed in) => allowed: degrade gracefully."""
    return not stored_token or not my_token or stored_token == my_token
