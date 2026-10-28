"""Serving rules: free daily question cap, speed check and one session (no Streamlit import, unit-testable).

There is no live AI at runtime for anyone: every question comes from the verified bank, which the
scheduled routine (scripts/build_bank.py) tops up with fresh verified AI questions every day.
- Free: FREE_DAILY_QUESTION_CAP questions per IST day in total.
- Pro: unlimited bank questions.
- Speed check (Pro, the only unlimited tier): requests faster than a human could read a question trigger
  a temporary cooldown (never a permanent ban); each trigger is logged as an abuse event. This protects
  the bank from scripted scraping.
- One active session per (user, exam_family): a newer sign-in takes over; older sessions stop serving.
"""
from __future__ import annotations

import datetime as dt
import uuid

SPEED_WINDOW_S = 60
SPEED_MAX_IN_WINDOW = 8        # >= 8 question requests within 60 s
MIN_HUMAN_GAP_S = 5
FAST_GAPS_IN_A_ROW = 4         # 4 consecutive gaps under 5 s
COOLDOWN_S = 10 * 60
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

FREE_DAILY_QUESTION_CAP = 10

FREE_NOTE = "Free: 10 questions/day."
PRO_PITCH = "Unlimited verified practice + fresh questions added every day"
PRO_NOTE = "Pro: " + PRO_PITCH + "."
FREE_CAP_MESSAGE = ("You've used today's 10 free questions. Come back tomorrow (resets at midnight IST), or "
                    "upgrade to Pro for unlimited verified practice plus fresh questions added every day.")
PRO_LEVEL_DONE_MESSAGE = ("You've done every question at this level. New questions are added every day; "
                          "try another level or topic meanwhile.")
COOLDOWN_MESSAGE = ("Whoa, that's faster than anyone can read a question! New questions are paused for a few "
                    "minutes.")
OTHER_DEVICE_MESSAGE = ("Signed in on another device. This session no longer gets new questions. "
                        "Sign out and sign in again here to continue on this device.")

def ist_today(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return now.astimezone(IST).date().isoformat()


def free_used_today(usage_day, used, now: dt.datetime | None = None) -> int:
    """Free questions used today (IST) from the profiles row (usage_day / ai_used); an earlier day counts as 0."""
    return int(used or 0) if str(usage_day or "")[:10] == ist_today(now) else 0


def free_cap_reached(used_today: int, cap: int = FREE_DAILY_QUESTION_CAP) -> bool:
    return used_today >= cap


def serve_free(used_today: int, bank, fallback, cap: int = FREE_DAILY_QUESTION_CAP):
    """Free users: bank only (there is no live AI). Returns (question, used_today, note).
    question is None (and note is FREE_CAP_MESSAGE) once the daily cap is reached. bank() returns an unseen
    question for this topic+level (scheduled AI first) or None; fallback() serves one from another level.
    The counter goes up exactly once per question actually served."""
    if free_cap_reached(used_today, cap):
        return None, used_today, FREE_CAP_MESSAGE
    q, note = bank(), None
    if q is None:
        q, note = fallback(), "level_exhausted"
    if q is not None:
        used_today += 1
    return q, used_today, note


def too_fast(request_times: list[float], now: float) -> bool:
    """True if question requests (epoch seconds, including this one) come faster than a human could use them."""
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
