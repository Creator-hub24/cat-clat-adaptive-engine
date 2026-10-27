import datetime as dt
from unittest.mock import MagicMock

import guard
import store


def test_ist_day_boundary():
    # 18:29 UTC = 23:59 IST same day; 18:31 UTC = next IST day
    assert guard.ist_today(dt.datetime(2026, 10, 27, 18, 29, tzinfo=dt.timezone.utc)) == "2026-10-27"
    assert guard.ist_today(dt.datetime(2026, 10, 27, 18, 31, tzinfo=dt.timezone.utc)) == "2026-10-28"


def test_pro_cap_counts_only_today():
    now = dt.datetime(2026, 10, 27, 6, 0, tzinfo=dt.timezone.utc)
    assert guard.ai_used_today({"ai_day": "2026-10-27", "ai_used": 100}, now) == 100
    assert guard.ai_used_today({"ai_day": "2026-10-26", "ai_used": 100}, now) == 0
    assert guard.ai_used_today(None, now) == 0
    assert guard.PRO_DAILY_AI_CAP == 100
    assert not guard.pro_cap_reached(99) and guard.pro_cap_reached(100)


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
    assert guard.FAIR_USE_NOTE == ("Pro includes up to 100 fresh AI questions per day; "
                                   "question-bank practice is unlimited.")
