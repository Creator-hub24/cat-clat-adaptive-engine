"""CUET app: family config, the curated AptiSetu CUET import, separate Pro, generation wiring and an app boot."""
import datetime as dt
import json
import pathlib
import re
from collections import Counter
from unittest.mock import MagicMock

import pytest

import bank
import engine
import families
import payments
import prompts
import store
from scripts import build_bank
from scripts import import_aptisetu as imp

ROOT = pathlib.Path(__file__).resolve().parents[1]
CUR = ROOT / "data" / "aptisetu_curation" / "cuet"
BANK = json.loads(bank.APTISETU_CUET_PATH.read_text(encoding="utf-8"))["questions"]
BY_ID = {q["id"]: q for q in BANK}
SERVED = bank.servable_imports(BANK)
SNAP = json.loads((ROOT / "tests/fixtures/aptisetu_cuet_source_keys.json").read_text(encoding="utf-8"))
SOURCE = pathlib.Path("/workspace/aptisetu_verify/src/data/cuet.json")   # local AptiSetu checkout, absent in CI
CUET_TOPICS = families.family_topics("cuet")
SECTIONS = {
    "General Test": ["CUET Quantitative Reasoning", "CUET General Mental Ability",
                     "CUET Logical & Analytical Reasoning", "CUET General Knowledge"],
    "English": ["CUET English Reading Comprehension", "CUET English Verbal Ability"],
    "Mathematics": ["CUET Maths Section A", "CUET Maths Section B1"],
}
HTML = re.compile(r"</?[A-Za-z][^<>]*>")


def _texts(q):
    return [q["question_text"], q["pedagogical_explanation"], *q["options"].values()]


# ---------- family config
def test_cuet_family_config(monkeypatch):
    f = families.FAMILIES["cuet"]
    assert f["name"] == "CUET Adaptive Engine" and f["icon"] == "🎓"
    assert f["accent"] == "#D97706" and f["accent2"]
    assert f["tagline"] == ("CUET UG General Test, English and Maths practice: verified questions, named traps, "
                            "speed tracking.")
    assert f["sections"] == SECTIONS and not f.get("coming_soon")
    assert f["level_labels"]["CAT-Level"] == "Exam-Level"
    monkeypatch.setenv("EXAM_FAMILY", "CUET")
    assert families.get_family()["key"] == "cuet"
    assert families.resolve_family(None) == "cuet"
    for t in CUET_TOPICS:
        assert families.topic_family(t) == "cuet" and t in prompts.TOPIC_RULES
    assert prompts.sections_for("cuet") == SECTIONS


def test_cuet_topics_and_prefixes_unique_across_families():
    others = set().union(*(families.family_topics(k) for k in families.FAMILIES if k != "cuet"))
    assert not CUET_TOPICS & others
    all_topics = sorted(set().union(*(families.family_topics(k) for k in families.FAMILIES)))
    prefixes = [build_bank.topic_prefix(t) for t in all_topics]
    assert len(set(prefixes)) == len(prefixes)
    assert all(build_bank.topic_prefix(t).startswith("CU") for t in CUET_TOPICS)


def test_cuet_engine_rules():
    assert "CUET General Knowledge" in engine.NO_AI_GENERATION_TOPICS
    assert "CUET English Reading Comprehension" in engine.RC_TOPICS
    assert "CUET Quantitative Reasoning" in engine.QUANT_TOPICS
    assert {"CUET Maths Section A", "CUET Maths Section B1"} <= engine.COMPUTABLE_TOPICS
    assert "CUET General Knowledge" not in build_bank.family_topics_to_generate("cuet")
    assert set(build_bank.family_topics_to_generate("cuet")) == CUET_TOPICS - {"CUET General Knowledge"}


# ---------- import: counts, curation
def test_cuet_import_counts():
    assert len(BANK) == 408 and len(SERVED) == 407
    assert all(q["exam"] == "CUET" and q["topic"] in CUET_TOPICS for q in BANK)
    served = Counter(q["topic"] for q in SERVED)
    assert served == {"CUET Quantitative Reasoning": 122, "CUET General Mental Ability": 79,
                      "CUET Logical & Analytical Reasoning": 71, "CUET General Knowledge": 15,
                      "CUET English Reading Comprehension": 32, "CUET English Verbal Ability": 29,
                      "CUET Maths Section A": 33, "CUET Maths Section B1": 26}
    per_section = {s: sum(served[t] for t in ts) for s, ts in SECTIONS.items()}
    assert per_section == {"General Test": 287, "English": 61, "Mathematics": 59}


def test_cuet_verified_flags_and_exclusion():
    ver = json.loads((CUR / "verified_ids.json").read_text(encoding="utf-8"))
    assert len(ver["ids"]) == 435 and ver["ambiguous"] == ["AS-CU-LAR-G-R92"]
    drops = {p["drop"] for p in json.loads((CUR / "duplicates.json").read_text(encoding="utf-8"))["pairs"]}
    shipped_verified = {q["id"] for q in BANK if q["verified"]}
    assert shipped_verified == set(ver["ids"]) - drops and len(shipped_verified) == 407
    assert all(q["verification"] == ["independent solve"] for q in BANK if q["verified"])
    g = BY_ID["AS-CU-LAR-G-R92"]
    assert not g["verified"] and g["excluded"]["category"] == "ambiguous" and "grandfather" in g["excluded"]["reason"]
    assert "AS-CU-LAR-G-R92" not in {q["id"] for q in SERVED}
    assert all(q["verified"] for q in SERVED)
    pool = bank.serving_pool([], [], BANK)
    assert len(pool) == 407 and all(q["source"] == "AptiSetu bank" and q["verified"] for q in pool)


def test_cuet_duplicates_dropped_one_kept_per_group():
    pairs = json.loads((CUR / "duplicates.json").read_text(encoding="utf-8"))["pairs"]
    drops, keeps = {p["drop"] for p in pairs}, {p["keep"] for p in pairs}
    assert len(pairs) == 28 and len(drops) == 28 and not drops & keeps
    assert not drops & set(BY_ID) and keeps <= set(BY_ID)
    assert SNAP["source_items"] == len(BANK) + len(drops)
    hashes = [q["text_hash"] for q in BANK]
    assert len(set(hashes)) == len(hashes) and len(BY_ID) == len(BANK)
    stems = Counter(re.sub(r"\W+", " ", q["question_text"]).strip().lower() for q in BANK)
    assert max(stems.values()) == 1


def test_cuet_html_cleaned_and_no_tables():
    for q in BANK:
        for t in _texts(q):
            assert not HTML.search(t), (q["id"], t[:80])
            assert not re.search(r"&(nbsp|amp|lt|gt|quot|#\d+);", t), q["id"]
            assert "|" not in t, q["id"]                     # '|A|' must never render as a markdown table
            assert not any(line.lstrip().startswith("|") for line in t.splitlines())
    assert any("∣" in t for q in BANK for t in _texts(q))  # determinants/modulus kept, as U+2223
    mx = [q for q in BANK if imp.MATRIX_NOTE in q["question_text"]]
    assert mx and all(re.search(r"[\[∣][^\]∣]*;", " ".join(_texts(q))) for q in mx)


def test_cuet_inline_conversions():
    m = ("<span class='mx'><span class='mx-r'><span>1</span><span>2</span></span>"
         "<span class='mx-r'><span>3</span><span>4</span></span></span>")
    assert imp.cuet_inline(f"A = {m}") == "A = [1, 2; 3, 4]"
    assert imp.cuet_inline(f"the determinant {m}") == "the determinant ∣1, 2; 3, 4∣"
    assert imp.cuet_inline("|x| &lt; 3 &amp; y") == "∣x∣ < 3 & y"
    assert imp.cuet_inline("a<br>b&nbsp;c", breaks=True) == "a\nb\nc"
    assert imp.cuet_stem("fill ____ here") == "fill \\_\\_\\_\\_ here"
    assert imp.ordinal_refs("the second option and The fourth option") == "Option B and Option D"
    assert imp.cuet_inline("<div class='x'>a <b>b</b> <sup>2</sup></div>") == "a **b** ^2"
    with pytest.raises(ValueError):                                  # anything the converter can't map fails loudly
        imp.cuet_inline("a <x-y>")


# ---------- import: keys
def test_cuet_keys_point_at_same_answer_text():
    assert set(SNAP["items"]) == set(BY_ID)
    for qid, s in SNAP["items"].items():
        q = BY_ID[qid]
        src_key_text = s["options"]["ABCD".index(s["source_key"])]
        assert q["options"][q["correct_answer"]] == src_key_text, qid
        assert sorted(q["options"].values()) == sorted(s["options"]), qid   # same options, only reordered


def test_cuet_fixed_items_untouched():
    fixed = {k for k, s in SNAP["items"].items() if s["fixed"]}
    assert len(fixed) == 45                                            # 46 in the source, one was a duplicate
    assert fixed == {q["id"] for q in BANK if q.get("options_fixed")}
    for qid in fixed:
        q, s = BY_ID[qid], SNAP["items"][qid]
        assert [q["options"][k] for k in "ABCD"] == s["options"] and q["correct_answer"] == s["source_key"]
    moved = sum(BY_ID[k]["correct_answer"] != s["source_key"] for k, s in SNAP["items"].items())
    assert moved > 100


def test_cuet_keys_balanced_per_topic():
    by_topic = {}
    for q in SERVED:
        by_topic.setdefault(q["topic"], Counter())[q["correct_answer"]] += 1
    for topic, c in by_topic.items():
        assert set(c) == set("ABCD") and max(c.values()) - min(c.values()) <= 2, (topic, c)


def test_cuet_explanation_refs_remapped():
    q = BY_ID["AS-CU-MA-UM1"]
    assert "The third" not in q["pedagogical_explanation"] and "Option" in q["pedagogical_explanation"]
    for q in BANK:   # every 'Option X' reference names a real letter
        assert set(re.findall(r"\bOption ([A-Z])\b", q["pedagogical_explanation"])) <= set("ABCD")


def test_cuet_shuffle_keeps_cat_path_and_skips_fixed():
    items = [{"id": f"AS-T-{i}", "options": dict(zip("ABCD", "pqrs")), "correct_answer": "A",
              "pedagogical_explanation": "Option A.", **({"options_fixed": True} if i < 3 else {})}
             for i in range(12)]
    imp.balanced_shuffle(items, ["AS-T-"], "seed")
    assert all(q["options"] == dict(zip("ABCD", "pqrs")) and q["correct_answer"] == "A" for q in items[:3])
    assert Counter(q["correct_answer"] for q in items) == {"A": 3, "B": 3, "C": 3, "D": 3}
    for q in items:
        assert q["options"][q["correct_answer"]] == "p"
        assert q["pedagogical_explanation"] == f"Option {q['correct_answer']}."


@pytest.mark.skipif(not SOURCE.exists(), reason="AptiSetu source checkout not available (CI)")
def test_cuet_snapshot_matches_source_and_reimport_is_stable(tmp_path):
    items, skipped = imp.convert_cuet(json.loads(SOURCE.read_text(encoding="utf-8")))
    assert not skipped and len(items) == SNAP["source_items"] == 436
    by = {q["id"]: q for q in items}
    for qid, s in SNAP["items"].items():
        assert [by[qid]["options"][k] for k in "ABCD"] == s["options"] and by[qid]["correct_answer"] == s["source_key"]
    out = tmp_path / "cuet.json"
    imp.main([str(SOURCE), "--family", "cuet", "--out", str(out)])
    assert json.loads(out.read_text(encoding="utf-8"))["questions"] == BANK


# ---------- separate Pro
def test_cuet_pro_is_separate():
    uid = "u" * 64
    law, cu = store.MemoryStore("mgmt_law"), store.MemoryStore("cuet")
    cu.profiles, cu.attempts, cu.entitlements = law.profiles, law.attempts, law.entitlements   # same database
    p, _ = law.load(uid)
    law.save_profile(uid, payments.extend_pro(p, today=dt.date(2026, 10, 27)))
    p_cu, _ = cu.load(uid)
    assert not store.is_pro(p_cu, dt.date(2026, 11, 1)) and payments.price_for(p_cu) == payments.INTRO_PRICE_PAISE
    cu.save_profile(uid, payments.extend_pro(p_cu, today=dt.date(2026, 10, 27)))
    assert store.is_pro(cu.load(uid)[0], dt.date(2026, 11, 1))
    assert law.profiles[uid]["pro_purchases"] == 1                 # CUET Pro lives only in pro_entitlements


def test_cuet_payment_link_and_verify_family():
    class H:
        posted, links = None, []

        def post(self, url, json, auth, timeout):
            H.posted = json
            r = MagicMock()
            r.json.return_value = {"short_url": "https://rzp.io/x"}
            return r

        def get(self, url, params, auth, timeout):
            r = MagicMock()
            r.json.return_value = {"payment_links": H.links}
            return r
    h, f = H(), families.FAMILIES["cuet"]
    payments.create_link("k", "s", "u" * 64, payments.INTRO_PRICE_PAISE, http=h, app_name=f["name"],
                         exam_family="cuet")
    assert H.posted["notes"]["exam_family"] == "cuet" and H.posted["description"].startswith("CUET Adaptive Engine")
    link = {"status": "paid", "reference_id": "r", "amount": 49900, "amount_paid": 49900,
            "notes": {"exam_family": "cuet"}}
    H.links = [link]
    assert payments.verify_paid("k", "s", "r", 49900, http=h, exam_family="cuet")
    for other in ("mgmt_law", "sarkari", "medical", "engineering"):
        assert not payments.verify_paid("k", "s", "r", 49900, http=h, exam_family=other)
    H.links = [{**link, "notes": {"exam_family": "sarkari"}}]
    assert not payments.verify_paid("k", "s", "r", 49900, http=h, exam_family="cuet")
    H.links = [{**link, "notes": {}}]                                # old link without a note = mgmt_law
    assert not payments.verify_paid("k", "s", "r", 49900, http=h, exam_family="cuet")


def test_cuet_in_entitlements_migration_and_schema():
    mig = (ROOT / "supabase/migrations/2026-10-28_cuet_family.sql").read_text(encoding="utf-8")
    assert "drop constraint if exists pro_entitlements_exam_family_check" in mig and "'cuet'" in mig
    assert "'cuet'" in (ROOT / "supabase/schema.sql").read_text(encoding="utf-8")


def test_cuet_supabase_unmigrated_check_disables_pro():
    """Before the migration the CHECK rejects exam_family='cuet': a pending payment ref can't be stored, so the
    store must report it (the app then hides the pay button) instead of silently dropping it."""
    client = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "pro_entitlements":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            t.upsert.side_effect = Exception('violates check constraint "pro_entitlements_exam_family_check"')
        else:
            t.select.return_value.eq.return_value.execute.return_value.data = []
            t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        return t
    client.table.side_effect = table
    cu = store.SupabaseStore(None, None, client=client, family="cuet")
    p, _ = cu.load("u" * 64)
    assert cu.entitlements_ok
    cu.save_profile("u" * 64, p)                                    # free user: no crash
    assert not cu.entitlements_ok
    with pytest.raises(Exception):
        cu.save_profile("u" * 64, {**p, "pending_payment_ref": "ref"})


# ---------- generation (scripts/build_bank.py; not run against an API here)
def test_build_bank_cuet_examples_and_prefixes():
    ex = build_bank.family_examples("cuet")
    assert len(ex) == 407 and {q["topic"] for q in ex} == CUET_TOPICS
    assert all(q["verified"] for q in ex)
    assert not {q["topic"] for q in build_bank.family_examples("mgmt_law")} & CUET_TOPICS
    for t in CUET_TOPICS:
        p = prompts.build_prompt(t, "Moderate", prompts.retrieve_examples(ex, t, "Moderate"))
        assert t in p and "∣" in prompts.TOPIC_RULES[t] and "Exam-Level" in prompts.TOPIC_RULES[t]


def test_build_bank_cuet_infers_family_and_prefix(tmp_path, monkeypatch):
    seen = {}

    def fake_generate(client, models, topic, difficulty, prompt, system, max_tries=2, log=None):
        seen.setdefault("prompts", []).append(prompt)
        return {"question_text": f"If 2x + 3 = 11, what is x? ({len(seen['prompts'])})", "topic": topic,
                "difficulty": difficulty, "exam": "CUET", "options": {"A": "3", "B": "4", "C": "5", "D": "6"},
                "correct_answer": "B", "trap_type": "-", "pedagogical_explanation": "2x = 8.",
                "concept_tag": "Linear equations", "verify_code": "", "source": "AI", "model": "fake",
                "verified": True, "verification": ["independent solve"]}
    monkeypatch.setattr(build_bank.llm, "generate_verified", fake_generate)
    out = tmp_path / "ai.json"
    data = build_bank.build(None, 1, out, topics=["CUET Maths Section A"], difficulties=["Easy"],
                            log=lambda *a: None)                     # family inferred from the topic
    assert [q["id"][:8] for q in data["questions"]] == ["AI-CUMA-"]
    assert "CUET Maths Section A" in seen["prompts"][0]
    assert any(q["question_text"][:40] in seen["prompts"][0] for q in build_bank.family_examples("cuet")
               if q["topic"] == "CUET Maths Section A")             # few-shot examples come from the CUET bank


# ---------- app boot
def test_app_boots_as_cuet(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("EXAM_FAMILY", "cuet")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert "CUET UG Adaptive Practice Engine" in [t.value for t in at.title]
    exam = next(r for r in at.sidebar.radio if r.label == "Exam")
    assert list(exam.options) == list(SECTIONS)
    next(b for b in at.button if b.label == "Next question").click().run()
    assert not at.exception
    answer = next(r for r in at.radio if r.label == "Your answer")
    assert len(answer.options) == 4
    next(b for b in at.button if b.label == "Daily micro-challenge").click().run()
    assert not at.exception
    assert any("Verified" in c.value for c in at.caption)
    exam = next(r for r in at.sidebar.radio if r.label == "Exam")
    exam.set_value("Mathematics").run()
    assert list(at.sidebar.selectbox[0].options) == SECTIONS["Mathematics"]
    assert not at.exception
