"""Claude-curated bank: importer output, schema, counts, stable ids, family isolation, serving and labels."""
import json
import random
import re
from collections import Counter

import pytest

import bank
import engine
import families
from scripts import import_claude_bank as imp

FAMS = ("mgmt_law", "sarkari", "cuet")
BANKS = {f: json.loads(bank.claude_bank_path(f).read_text(encoding="utf-8")) for f in FAMS}
ITEMS = {f: BANKS[f]["questions"] for f in FAMS}
ALL = [q for f in FAMS for q in ITEMS[f]]
BY_SOURCE = {q["source_ref"]: q for q in ALL}
ID_RE = re.compile(r"^CL-(ML|SK|CU)-[A-Z]+-(B1|F[1-5])-\d{3}$")
EXPECTED_TOPICS = {
    "mgmt_law": {"CAT DILR": 60, "CAT Quant": 53, "CAT VARC RC": 60, "CLAT Legal Reasoning": 119,
                 "CLAT Logical Reasoning": 57, "IPMAT Quant": 51, "IPMAT Verbal": 58},
    "sarkari": {"Sarkari English": 60, "Sarkari Quantitative Aptitude": 59, "Sarkari Reasoning": 60},
    "cuet": {"CUET English Reading Comprehension": 60, "CUET English Verbal Ability": 57,
             "CUET General Mental Ability": 52, "CUET Logical & Analytical Reasoning": 60,
             "CUET Maths Section A": 57, "CUET Maths Section B1": 60, "CUET Quantitative Reasoning": 55},
}


def test_counts_per_family_and_topic():
    assert len(ALL) == 1038
    for f in FAMS:
        assert dict(Counter(q["topic"] for q in ITEMS[f])) == EXPECTED_TOPICS[f]
        assert BANKS[f]["meta"]["count"] == len(ITEMS[f]) and BANKS[f]["meta"]["family"] == f
    assert {f: len(ITEMS[f]) for f in FAMS} == {"mgmt_law": 458, "sarkari": 179, "cuet": 401}


def test_schema_and_key_letters():
    for q in ALL:
        assert engine.REQUIRED_KEYS <= set(q), q["id"]
        assert sorted(q["options"]) == list("ABCD") and all(str(v).strip() for v in q["options"].values())
        assert len({str(v).strip() for v in q["options"].values()}) == 4, q["id"]
        assert q["correct_answer"] in ("A", "B", "C", "D"), q["id"]
        assert q["difficulty"] in engine.DIFFICULTIES
        assert q["exam"] in imp.EXAM_FAMILY and q["text_hash"] == bank.text_hash(q)
    # balanced keys across the bank (every source batch was 5/5/5/5)
    keys = Counter(q["correct_answer"] for q in ALL)
    assert max(keys.values()) - min(keys.values()) <= 10, keys


def test_ids_unique_stable_and_distinct_from_other_banks():
    ids = [q["id"] for q in ALL]
    assert len(ids) == len(set(ids)) and all(ID_RE.match(i) for i in ids)
    assert len({q["text_hash"] for q in ALL}) == len(ALL)
    others = [bank.SEED_PATH, bank.AI_BANK_PATH, *bank.IMPORT_PATHS, *sorted(bank.ROOT.glob("data/sample_bank_*.json"))]
    other_ids = {q["id"] for p in others for q in bank.load_json_bank(p)["questions"]}
    other_hashes = {bank.text_hash(q) for p in others for q in bank.load_json_bank(p)["questions"]}
    assert not set(ids) & other_ids and not {q["text_hash"] for q in ALL} & other_hashes
    # id comes from the source position: same item -> same id on every run
    assert imp.make_id("mgmt_law", "CLAT Legal Reasoning", "file-5 #7") == "CL-ML-CLLR-F5-007"
    assert imp.make_id("sarkari", "Sarkari Reasoning", "file-1 #62") == "CL-SK-SRE-F1-062"
    assert imp.make_id("cuet", "CUET Maths Section A", "batch-1 file #3") == "CL-CU-MA-B1-003"


def test_importer_is_deterministic():
    out = imp.build(run_code=False)
    assert {f: out[f] for f in FAMS} == ITEMS  # committed files match a fresh run on the curation sources


def test_family_isolation():
    for f in FAMS:
        topics = families.family_topics(f)
        assert all(q["topic"] in topics and families.topic_family(q["topic"]) == f for q in ITEMS[f])
        assert all(imp.EXAM_FAMILY[q["exam"]] == f for q in ITEMS[f])
        paths = bank.import_paths(f)
        assert bank.claude_bank_path(f) in paths
        assert not any(bank.claude_bank_path(g) in paths for g in FAMS if g != f)
    assert bank.import_paths("medical") == bank.IMPORT_PATHS


def test_curation_decisions_applied():
    q62, q138 = BY_SOURCE["claude:file-1 #62"], BY_SOURCE["claude:file-1 #138"]
    assert q62["options"]["C"] == "99" and q62["correct_answer"] == "A" and "72" not in q62["pedagogical_explanation"]
    assert q138["options"]["D"] == "against" and q138["correct_answer"] == "B"
    assert "claude:file-1 #25" not in BY_SOURCE
    assert not [q for q in ALL if q["topic"] == "CLAT RC"]  # batches 40-42 are Legal Reasoning
    assert all(BY_SOURCE[f"claude:file-5 #{i}"]["topic"] == "CLAT Legal Reasoning" for i in range(40))


def test_verify_codes_reproduce_keys():
    coded = [q for q in ALL if q["verify_code"]]
    assert len(coded) > 500
    for q in coded:
        assert "computed" in q["verification"]
        ans = engine.run_verify_code(q["verify_code"])
        assert engine.answer_matches_key(ans, q["options"], q["correct_answer"]), q["id"]


@pytest.mark.parametrize("family", FAMS)
def test_served_with_verified_label(family):
    topics = families.family_topics(family)
    imported = [q for p in bank.import_paths(family) for q in bank.load_json_bank(p)["questions"] if q["topic"] in topics]
    pool = bank.serving_pool([], [], imported)
    mine = [q for q in pool if q["source"] == bank.CLAUDE_SOURCE]
    assert len(mine) == len(ITEMS[family])
    for q in mine:
        assert q["verified"] is True and q["verification"][0] == "independent solve"
        badge = ("✅ Verified (" + ", ".join(q["verification"]) + ")") if q.get("verified") else "⚠️ Unverified"
        assert badge.startswith("✅ Verified (independent solve")
    assert {q["source"] for q in pool} <= set(bank.IMPORT_SOURCES)


def test_excluded_and_seen_items_are_not_served():
    items = [dict(q) for q in ITEMS["sarkari"] if q["topic"] == "Sarkari Reasoning" and q["difficulty"] == "Easy"]
    items[0]["excluded"] = {"category": "wrong key", "reason": "test"}
    pool = bank.serving_pool([], [], items)
    assert items[0]["id"] not in {q["id"] for q in pool}
    seen = {q["id"] for q in pool[1:]}
    rng = random.Random(1)
    assert bank.pick_unseen(pool, "Sarkari Reasoning", "Easy", seen, rng)["id"] == pool[0]["id"]
    assert bank.pick_unseen(pool, "Sarkari Reasoning", "Easy", seen | {pool[0]["id"]}, rng) is None


def test_exclusions_from_decisions(tmp_path):
    for name in ("verified_questions.json", "manifest.json", "additions.json"):
        (tmp_path / name).write_text((imp.CURATION_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
    dec = json.loads((imp.CURATION_DIR / "decisions.json").read_text(encoding="utf-8"))
    dec["exclusions"] = [{"source": "file-1 #62", "category": "review", "reason": "test"}]
    (tmp_path / "decisions.json").write_text(json.dumps(dec), encoding="utf-8")
    out = imp.build(tmp_path, run_code=False)
    q = next(q for q in out["sarkari"] if q["source_ref"] == "claude:file-1 #62")
    assert q["excluded"]["reason"] == "test" and len(bank.servable_imports(out["sarkari"])) == 178


def test_scheduled_ai_still_served_first():
    claude = dict(ITEMS["mgmt_law"][0])
    ai = dict(claude, id="AI-TEST-1", text_hash="x", created_at="2026-10-28T00:00:00", review_status="approved")
    pool = bank.serving_pool([], [ai], [claude])
    got = bank.pick_unseen(pool, claude["topic"], claude["difficulty"], set(), random.Random(0))
    assert got["id"] == "AI-TEST-1"
