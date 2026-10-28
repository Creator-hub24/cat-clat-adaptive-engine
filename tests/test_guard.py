import datetime as dt
from unittest.mock import MagicMock

import guard
import store


def test_ist_day_boundary():
    # 18:29 UTC = 23:59 IST same day; 18:31 UTC = next IST day
    assert guard.ist_today(dt.datetime(2026, 10, 27, 18, 29, tzinfo=dt.timezone.utc)) == "2026-10-27"
    assert guard.ist_today(dt.datetime(2026, 10, 27, 18, 31, tzinfo=dt.timezone.utc)) == "2026-10-28"


def test_no_pro_ai_cap_any_more():
    assert not hasattr(guard, "PRO_DAILY_AI_CAP") and not hasattr(guard, "CAP_MESSAGE")


def test_speed_check():
    assert guard.too_fast([1000 + i * 6 for i in range(8)], 1042)        # 8 in 60 s
    assert not guard.too_fast([1000 + i * 9 for i in range(7)], 1054)    # human pace
    assert guard.too_fast([1000, 1002, 1004, 1006, 1008], 1008)          # 4 gaps < 5 s
    assert not guard.too_fast([1000, 1002, 1010, 1012, 1014], 1014)
    until = guard.cooldown_until(1000)
    assert until == 1600 and guard.in_cooldown(until, 1599) and not guard.in_cooldown(until, 1601)
    assert not guard.in_cooldown(None, 0)
    iso = dt.datetime.fromtimestamp(2000, dt.timezone.utc).isoformat()
    assert guard.in_cooldown(iso, 1999) and not guard.in_cooldown(iso, 2001)


def test_session_takeover():
    assert guard.session_is_current("a", "a")
    assert not guard.session_is_current("b", "a")
    assert guard.session_is_current(None, "a")      # table missing / no row -> degrade gracefully
    assert guard.new_session_token() != guard.new_session_token()


def test_memory_store_guard_per_family():
    law, sk = store.MemoryStore("mgmt_law"), store.MemoryStore("sarkari")
    law.save_guard("u", {"session_token": "t1", "ai_day": "2026-10-27", "ai_used": 5, "junk": 1})
    assert law.load_guard("u") == {"session_token": "t1", "ai_day": "2026-10-27", "ai_used": 5}
    assert sk.load_guard("u") is None
    law.log_abuse("u", "speed")
    assert law.abuse[0]["exam_family"] == "mgmt_law"
    law.delete_all("u")
    assert law.load_guard("u") is None and not law.abuse


def test_supabase_guard_degrades_when_tables_missing():
    db = MagicMock()
    db.table.side_effect = Exception("relation usage_guard does not exist")
    st = store.SupabaseStore("u", "k", client=db, family="sarkari")
    assert st.load_guard("u") is None
    assert st.save_guard("u", {"ai_used": 1}) is False
    assert st.log_abuse("u", "speed") is False


def test_wording_mentions_fair_use():
    src = open("app.py").read()
    assert "unlimited AI questions" not in src and "unlimited fresh questions" not in src
    assert "Unlimited practice" in src
    assert guard.PRO_PITCH == "Unlimited verified practice + fresh questions added every day"
    assert guard.PRO_NOTE == "Pro: Unlimited verified practice + fresh questions added every day."
    for doc in ("app.py", "guard.py", "README.md", "PRD.md"):
        text = open(doc, encoding="utf-8").read()
        assert "50 fresh AI" not in text and "up to 50" not in text and "10 AI questions" not in text, doc
    assert guard.FREE_NOTE == "Free: 10 questions/day."
    assert "10 AI questions" not in src


# ---------------------------------------------------------------- free tier: 10 bank questions / IST day
def test_free_counter_counts_only_today():
    now = dt.datetime(2026, 10, 28, 6, 0, tzinfo=dt.timezone.utc)
    assert guard.free_used_today("2026-10-28", 7, now) == 7
    assert guard.free_used_today("2026-10-27", 7, now) == 0
    assert guard.free_used_today(None, None, now) == 0
    assert guard.FREE_DAILY_QUESTION_CAP == 10
    assert not guard.free_cap_reached(9) and guard.free_cap_reached(10)


def test_free_cap_is_10_total_then_message():
    served, used = [], 0
    for i in range(12):
        q, used, note = guard.serve_free(used, bank=lambda i=i: {"id": f"B{i}"}, fallback=lambda: {"id": "F"})
        served.append(q)
    assert [q["id"] for q in served[:10]] == [f"B{i}" for i in range(10)]
    assert served[10] is None and served[11] is None and used == 10
    q, used2, note = guard.serve_free(10, bank=lambda: {"id": "x"}, fallback=lambda: {"id": "y"})
    assert q is None and used2 == 10 and note == guard.FREE_CAP_MESSAGE
    assert guard.FREE_CAP_MESSAGE.startswith("You've used today's 10 free questions.")


def test_free_fallback_counts_once_and_bank_not_called_after_cap():
    calls = []
    q, used, note = guard.serve_free(3, bank=lambda: None, fallback=lambda: {"id": "other-level"})
    assert q["id"] == "other-level" and used == 4 and note == "level_exhausted"
    q, used, note = guard.serve_free(4, bank=lambda: None, fallback=lambda: None)
    assert q is None and used == 4  # nothing served, nothing counted
    guard.serve_free(10, bank=lambda: calls.append("b"), fallback=lambda: calls.append("f"))
    assert calls == []


def test_no_live_ai_at_runtime():
    import inspect
    import os
    assert set(inspect.signature(guard.serve_free).parameters) == {"used_today", "bank", "fallback", "cap"}
    src = open("app.py").read()
    for live in ("import llm", "llm.", "generate_verified", "make_client", "GEMINI_API_KEY", "prefetch",
                 "generate_ai_question", "FREE_DAILY_AI_LIMIT", "build_prompt"):
        assert live not in src, live
    assert not os.path.exists("prefetch.py")


def test_pro_exhausted_level_message_and_gate_only_for_pro():
    src = open("app.py").read()
    pro_branch = src[src.index("        if pro:\n            gate_msg = serve_gate()"):src.index("q, s.ai_used, note = guard.serve_free(")]
    assert "guard.PRO_LEVEL_DONE_MESSAGE" in pro_branch and "seed_question(" in pro_branch
    assert "ai_used" not in pro_branch  # Pro never touches the free counter
    assert guard.PRO_LEVEL_DONE_MESSAGE.startswith("You've done every question at this level.")
