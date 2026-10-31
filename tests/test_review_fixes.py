import json
import pathlib
from unittest.mock import MagicMock

import pytest

import engine
import payments
import store

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ---------- 1. delete_all erases every user-keyed table, tolerating missing ones
def _fake_db(missing=()):
    db, deleted = MagicMock(), []

    def table(name):
        t = MagicMock()
        if name in missing:
            t.delete.side_effect = Exception(f'relation "public.{name}" does not exist')
        t.delete.return_value.eq.side_effect = lambda col, v: (deleted.append((name, col, v)), MagicMock())[1]
        return t
    db.table.side_effect = table
    return db, deleted


def test_supabase_delete_all_covers_all_user_tables():
    db, deleted = _fake_db()
    store.SupabaseStore("u", "k", client=db, family="sarkari").delete_all("uid1")
    tables = {t for t, col, v in deleted if col == "user_id" and v == "uid1"}
    assert tables >= {"attempts", "pro_entitlements", "usage_guard", "abuse_events", "consumed_payments", "profiles"}
    assert "question_reports" not in tables  # holds no user identifier
    assert deleted[-1][0] == "profiles"


def test_supabase_delete_all_tolerates_missing_tables():
    db, deleted = _fake_db(missing={"usage_guard", "abuse_events", "consumed_payments", "pro_entitlements"})
    store.SupabaseStore("u", "k", client=db).delete_all("uid1")
    assert {t for t, *_ in deleted} == {"attempts", "profiles"}


def test_memory_delete_all_clears_payments():
    m = store.MemoryStore()
    m.consume_payment("plink_1", "u")
    m.delete_all("u")
    assert m.consume_payment("plink_1", "u2") is True


# ---------- 2. a payment ref extends Pro only once
def _verify_and_extend(st, profile, ref):
    """Mirror of app.py: insert-before-extend."""
    if st.consume_payment(ref, "u") is False:
        profile["pending_payment_ref"] = None
        return profile, False
    return payments.extend_pro(profile), True


def test_two_sessions_same_ref_extend_once():
    shared = store.MemoryStore("mgmt_law")
    a = {"pro_until": None, "pending_payment_ref": "plink_X"}
    b = dict(a)
    a, ok_a = _verify_and_extend(shared, a, "plink_X")
    b, ok_b = _verify_and_extend(shared, b, "plink_X")
    assert (ok_a, ok_b) == (True, False)
    assert a["pro_purchases"] == 1 and b.get("pro_purchases") is None
    assert b["pending_payment_ref"] is None and b["pro_until"] is None
    # replay in the same session after success
    a2, ok = _verify_and_extend(shared, dict(a, pending_payment_ref="plink_X"), "plink_X")
    assert not ok and a2["pro_until"] == a["pro_until"]


def _sb(insert_exc=None):
    db = MagicMock()
    if insert_exc:
        db.table.return_value.insert.return_value.execute.side_effect = insert_exc
    return store.SupabaseStore("u", "k", client=db, family="sarkari"), db


def test_supabase_consume_payment_outcomes():
    st, db = _sb()
    assert st.consume_payment("plink_1", "u") is True
    row = db.table.return_value.insert.call_args[0][0]
    assert row == {"payment_ref": "plink_1", "user_id": "u", "exam_family": "sarkari"}
    dup = Exception('duplicate key value violates unique constraint "consumed_payments_pkey"')
    dup.code = "23505"
    assert _sb(dup)[0].consume_payment("plink_1", "u") is False
    assert _sb(Exception('relation "public.consumed_payments" does not exist'))[0].consume_payment("p", "u") is None


def test_app_inserts_before_extending():
    src = (ROOT / "app.py").read_text()
    i, j = src.index("apply_verified_payment(s.pending_ref, plan)"), src.index("prof = payments.extend_pro(")
    assert i < j


def test_migration_sql_idempotent_and_locked_down():
    sql = (ROOT / "supabase/migrations/2026-10-28_consumed_payments.sql").read_text()
    assert "create table if not exists public.consumed_payments" in sql
    assert "payment_ref text primary key" in sql
    assert "enable row level security" in sql and "revoke all on public.consumed_payments from anon, authenticated" in sql
    assert "consumed_payments" in (ROOT / "supabase/schema.sql").read_text()


# ---------- 3. CI workflow
def test_ci_workflow():
    wf = (ROOT / ".github/workflows/tests.yml").read_text()
    assert "pull_request" in wf and "branches: [main]" in wf and "pytest" in wf and "secrets." not in wf


# ---------- 4. sandbox hardening
@pytest.mark.parametrize("code", [
    "answer = '{0.__class__}'.format(1)",
    "answer = '{0.real}'.format(1)",
    "answer = '{x}'.format_map({'x': 1})",
    "f = 'format'\nanswer = '__class__'",
    "answer = f'{1}__x'",
    "x = '_' '_class_' '_'\nanswer = x",
    "answer = b'__import__'",
    "answer = str.format('{0}', 1)",
])
def test_sandbox_rejects_escape_strings(code):
    with pytest.raises(engine.UnsafeCode):
        engine.check_code(code)


def test_all_bank_verify_code_still_passes():
    n = 0
    for f in sorted((ROOT / "data").glob("*.json")):
        try:
            items = json.loads(f.read_text())
        except Exception:
            continue
        items = items.get("questions", []) if isinstance(items, dict) else items
        for q in items:
            if isinstance(q, dict) and q.get("verify_code"):
                engine.check_code(q["verify_code"])
                ans = engine.run_verify_code(q["verify_code"])
                assert engine.answer_matches_key(ans, q["options"], q["correct_answer"]), q.get("id")
                n += 1
    assert n > 0


def test_supabase_consume_payment_records_plan_and_tolerates_old_table():
    st, db = _sb()
    assert st.consume_payment("plink_1", "u", "launch") is True
    assert db.table.return_value.insert.call_args[0][0]["plan"] == "launch"
    calls = []

    def ins(row):
        calls.append(row)
        m = MagicMock()
        if "plan" in row:
            m.execute.side_effect = Exception("Could not find the 'plan' column of 'consumed_payments'")
        return m
    st2, db2 = _sb()
    db2.table.return_value.insert.side_effect = ins
    assert st2.consume_payment("plink_2", "u", "monthly") is True
    assert len(calls) == 2 and "plan" not in calls[1]


def test_supabase_launch_claims():
    st, db = _sb()
    q = db.table.return_value.select.return_value.eq.return_value.eq.return_value
    q.execute.return_value.count = 7
    assert st.launch_claims() == 7
    q.execute.side_effect = Exception("column consumed_payments.plan does not exist")
    assert st.launch_claims() is None


def test_launch_offer_migration():
    sql = (ROOT / "supabase/migrations/2026-10-31_launch_offer.sql").read_text()
    assert "add column if not exists plan text" in sql
