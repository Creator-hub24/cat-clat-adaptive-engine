import datetime as dt
import json
import pathlib
from unittest.mock import MagicMock

import pytest

import engine
import families
import payments
import prompts
import store
from scripts import build_bank

ROOT = pathlib.Path(__file__).resolve().parents[1]
SARKARI = json.loads((ROOT / "data/sample_bank_sarkari.json").read_text())["questions"]
SARKARI_TOPICS = families.family_topics("sarkari")


# ---------- config selection
def test_default_family_is_mgmt_law_and_unchanged(monkeypatch):
    monkeypatch.delenv("EXAM_FAMILY", raising=False)
    f = families.get_family()
    assert f["key"] == "mgmt_law" and f["accent"] is None and families.theme_css(f) == ""
    assert f["title"] == "CAT/CLAT Adaptive Mock Test & Analytics Engine" and f["icon"] == "🎯"
    assert f["sections"] == prompts.SECTIONS
    assert list(prompts.SECTIONS) == ["CAT", "CLAT", "IPMAT"]
    assert families.resolve_family("nonsense") == families.resolve_family("") == "mgmt_law"


def test_family_selected_by_env(monkeypatch):
    monkeypatch.setenv("EXAM_FAMILY", " Sarkari ")
    f = families.get_family()
    assert f["key"] == "sarkari" and f["icon"] == "🏛️" and "#FF9933" in families.theme_css(f)
    assert families.get_family("medical")["icon"] == "🩺" and families.get_family("medical")["coming_soon"]
    assert families.get_family("engineering")["icon"] == "⚙️" and families.get_family("engineering")["coming_soon"]
    assert all(t == [] for t in families.get_family("medical")["sections"].values())


def test_topics_unique_across_families_and_ai_prefixes_unique():
    all_topics = [t for k in families.FAMILIES for t in families.family_topics(k)]
    assert len(all_topics) == len(set(all_topics))
    assert all(families.topic_family(t) for t in all_topics)
    prefixes = [build_bank.topic_prefix(t) for t in all_topics]
    assert len(prefixes) == len(set(prefixes))
    assert all(t in prompts.TOPIC_RULES for t in SARKARI_TOPICS)


# ---------- sarkari bank validity
def test_sarkari_bank_valid():
    ids = [q["id"] for q in SARKARI]
    assert len(ids) == len(set(ids)) == 16
    main = json.loads((ROOT / "data/sample_bank.json").read_text())["questions"]
    assert not set(ids) & {q["id"] for q in main}
    for q in SARKARI:
        assert q["topic"] in SARKARI_TOPICS and q["difficulty"] in engine.DIFFICULTIES
        assert set(q["options"]) == set("ABCD") and q["correct_answer"] in "ABCD"
        assert len(set(q["options"].values())) == 4
        assert engine.REQUIRED_KEYS <= q.keys()
    for t in SARKARI_TOPICS:
        assert {q["difficulty"] for q in SARKARI if q["topic"] == t} == set(engine.DIFFICULTIES)


def test_sarkari_quant_verified_by_code():
    quant = [q for q in SARKARI if q["topic"] == "Sarkari Quantitative Aptitude"]
    assert len(quant) == 4
    for q in quant:
        val = engine.run_verify_code(q["verify_code"])
        assert engine.answer_matches_key(val, q["options"], q["correct_answer"]), q["id"]


def test_sarkari_general_awareness_grounded_never_ai():
    t = "Sarkari General Awareness"
    assert t in engine.NO_AI_GENERATION_TOPICS
    gk = [q for q in SARKARI if q["topic"] == t]
    assert len(gk) == 4
    assert all(q["source_url"].startswith("https://") and len(q["as_of"]) == 10 for q in gk)
    import llm
    with pytest.raises(RuntimeError):
        llm.generate_verified(None, [], t, "Easy", "p", "s")
    assert t not in [x for x in [t2 for s in prompts.SECTIONS.values() for t2 in s]]


# ---------- per-family Pro / pricing
def test_pro_and_intro_offer_are_per_family():
    uid = "u" * 64
    law, sk = store.MemoryStore("mgmt_law"), store.MemoryStore("sarkari")
    sk.profiles, sk.attempts = law.profiles, law.attempts          # same database
    sk.entitlements = law.entitlements
    p, _ = law.load(uid)
    assert payments.price_for(p) == payments.INTRO_PRICE_PAISE
    law.save_profile(uid, payments.extend_pro(p, today=dt.date(2026, 10, 27)))
    p_law, _ = law.load(uid)
    assert store.is_pro(p_law, dt.date(2026, 11, 1)) and payments.price_for(p_law) == payments.PRO_PRICE_PAISE
    p_sk, _ = sk.load(uid)
    assert not store.is_pro(p_sk, dt.date(2026, 11, 1))
    assert payments.price_for(p_sk) == payments.INTRO_PRICE_PAISE   # own first-ever offer
    sk.save_profile(uid, payments.extend_pro(p_sk, today=dt.date(2026, 10, 27)))
    assert law.profiles[uid]["pro_purchases"] == 1                  # sarkari never touches profiles' Pro


def test_attempts_are_per_family():
    uid = "u" * 64
    law, sk = store.MemoryStore("mgmt_law"), store.MemoryStore("sarkari")
    sk.attempts = law.attempts
    law.add_attempt(uid, {"id": "Q1", "topic": "CAT Quant", "difficulty": "Easy", "correct": True})
    sk.add_attempt(uid, {"id": "SQA-E-01", "topic": "Sarkari Quantitative Aptitude", "difficulty": "Easy",
                         "correct": False})
    assert [a["question_id"] for a in law.load(uid)[1]] == ["Q1"]
    assert [a["question_id"] for a in sk.load(uid)[1]] == ["SQA-E-01"]


def test_apply_entitlement_mgmt_law_merges_profile_and_table():
    p = store.clean_profile({"pro_until": "2026-11-26", "pro_purchases": 1, "plan": "pro"})
    assert store.apply_entitlement(p, None, "mgmt_law")["pro_until"] == "2026-11-26"   # table missing/empty
    m = store.apply_entitlement(p, {"pro_until": "2026-12-26", "pro_purchases": 2}, "mgmt_law")
    assert m["pro_until"] == "2026-12-26" and m["pro_purchases"] == 2
    o = store.apply_entitlement(p, None, "sarkari")
    assert o["pro_until"] is None and o["pro_purchases"] == 0 and o["plan"] == "free"
    assert "pro_until" not in store.shared_profile_row(p, "sarkari")
    assert store.shared_profile_row(p, "mgmt_law")["pro_until"] == "2026-11-26"


def test_supabase_missing_entitlements_table_falls_back():
    client = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "pro_entitlements":
            t.select.side_effect = Exception("relation public.pro_entitlements does not exist")
            t.upsert.side_effect = Exception("relation public.pro_entitlements does not exist")
        elif name == "profiles":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"user_id": "u" * 64, "pro_until": "2026-11-26", "pro_purchases": 1}]
        else:
            t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        return t
    client.table.side_effect = table
    law = store.SupabaseStore(None, None, client=client)
    p, _ = law.load("u" * 64)
    assert p["pro_until"] == "2026-11-26" and not law.entitlements_ok
    law.save_profile("u" * 64, p)                                   # no crash
    sk = store.SupabaseStore(None, None, client=client, family="sarkari")
    p2, _ = sk.load("u" * 64)
    assert p2["pro_until"] is None and not sk.entitlements_ok
    sk.save_profile("u" * 64, p2)                                   # free user: no crash


def test_payment_link_names_app_and_family_checked():
    class H:
        posted = None
        links = []

        def post(self, url, json, auth, timeout):
            H.posted = json
            r = MagicMock()
            r.json.return_value = {"short_url": "https://rzp.io/x"}
            return r

        def get(self, url, params, auth, timeout):
            r = MagicMock()
            r.json.return_value = {"payment_links": H.links}
            return r
    h = H()
    payments.create_link("k", "s", "u" * 64, payments.INTRO_PRICE_PAISE, http=h,
                         app_name="Sarkari Exam Adaptive Engine", exam_family="sarkari")
    assert H.posted["description"].startswith("Sarkari Exam Adaptive Engine")
    assert H.posted["notes"]["exam_family"] == "sarkari"
    link = {"status": "paid", "reference_id": "r", "amount": 49900, "amount_paid": 49900,
            "notes": {"exam_family": "sarkari"}}
    H.links = [link]
    assert payments.verify_paid("k", "s", "r", 49900, http=h, exam_family="sarkari")
    assert not payments.verify_paid("k", "s", "r", 49900, http=h, exam_family="mgmt_law")
    H.links = [{**link, "notes": []}]                              # old link, no note => mgmt_law
    assert payments.verify_paid("k", "s", "r", 49900, http=h, exam_family="mgmt_law")
