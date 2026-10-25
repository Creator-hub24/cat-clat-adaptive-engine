import datetime as dt
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import payments
import store


def test_hash_is_stable_case_insensitive_and_peppered():
    a = store.user_id_hash("Arun@Example.com ", "pep")
    assert a == store.user_id_hash("arun@example.com", "pep")
    assert a != store.user_id_hash("arun@example.com", "other")
    assert len(a) == 64 and "arun" not in a


def test_hash_requires_pepper():
    import pytest
    with pytest.raises(ValueError):
        store.user_id_hash("a@b.com", "")


def test_clean_attempt_drops_personal_fields():
    a = store.clean_attempt({"id": "Q1", "topic": "CAT Quant", "difficulty": "Easy", "correct": 1,
                             "email": "x@y.com", "name": "X"})
    assert set(a) == set(store.ATTEMPT_FIELDS) and a["correct"] is True


def test_memory_store_roundtrip_export_delete():
    m, uid = store.MemoryStore(), "u" * 64
    m.save_profile(uid, {"streak": 3, "email": "leak@x.com", "review_queue": {"Q1": {"stage": 0}}})
    m.add_attempt(uid, {"id": "Q1", "topic": "T", "difficulty": "Easy", "correct": False})
    m.add_attempt("v" * 64, {"id": "Q2", "topic": "T", "difficulty": "Easy", "correct": True})
    prof, att = m.load(uid)
    assert prof["streak"] == 3 and "email" not in prof and len(att) == 1
    exp = store.export_data(m, uid)
    assert "leak@x.com" not in str(exp)
    m.delete_all(uid)
    prof, att = m.load(uid)
    assert att == [] and prof["streak"] == 0
    assert len(m.attempts) == 1  # other user untouched


def test_supabase_store_calls_are_scoped_to_user():
    client = MagicMock()
    s = store.SupabaseStore(None, None, client=client)
    s.save_profile("u" * 64, {"streak": 1, "name": "X"})
    row = client.table.return_value.upsert.call_args[0][0]
    assert row["user_id"] == "u" * 64 and "name" not in row
    s.delete_all("u" * 64)
    eq_calls = [c.args for c in client.table.return_value.delete.return_value.eq.call_args_list]
    assert eq_calls == [("user_id", "u" * 64)] * 2


def test_is_pro_and_extend():
    p = payments.extend_pro({"pro_until": None}, today=dt.date(2026, 1, 1))
    assert p["pro_until"] == "2026-01-31" and p["plan"] == "pro"
    p = payments.extend_pro(p, today=dt.date(2026, 1, 10))  # stacks on remaining time
    assert p["pro_until"] == "2026-03-02"
    assert store.is_pro(p, dt.date(2026, 3, 2)) and not store.is_pro(p, dt.date(2026, 3, 3))


def test_reference_and_verify():
    ref = payments.make_reference("a" * 64)
    assert len(ref) <= 40
    http = MagicMock()
    http.get.return_value.json.return_value = {"payment_links": [{"reference_id": ref, "status": "paid"}]}
    assert payments.verify_paid("k", "s", ref, http=http)
    http.get.return_value.json.return_value = {"payment_links": [{"reference_id": ref, "status": "created"}]}
    assert not payments.verify_paid("k", "s", ref, http=http)
