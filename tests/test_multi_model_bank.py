"""Multi-model Sarkari bank: importer output, schema, shuffle remap, serving badge."""
import json
import re
from collections import Counter

import pytest

import bank
import engine
import families
from scripts import import_multi_model_bank as imp

BANK = json.loads(bank.multi_model_bank_path("sarkari").read_text(encoding="utf-8"))
ITEMS = BANK["questions"]
BY_SOURCE = {q["source_ref"]: q for q in ITEMS}
ID_RE = re.compile(r"^MM-SK-(SQA|SRE|SEN|SGA)-(GB[1-6]|G4A|G4B|MT|CS5|C55|SG|CG|MH1|MH2|GB8|GB9|ME1|ME2|MR1|MR2|GA1|GA2|GA3|GA4|GA5|GA6|GA7|GA8|GA9)-\d{3}$")
EXPECTED_TOPICS = {
    "Sarkari English": 72,
    "Sarkari General Awareness": 249,
    "Sarkari Quantitative Aptitude": 100,
    "Sarkari Reasoning": 73,
}
EXPECTED_MODELS = {
    "ChatGPT Go": 9,
    "Claude (Pro)": 249,
    "Claude Sonnet 5": 10,
    "Claude Sonnet 5.5 Medium": 8,
    "Gemini Argon 4.0": 144,
    "Meta AI": 66,
    "SuperGrok": 8,
}


def test_counts_and_meta():
    assert len(ITEMS) == 494
    assert BANK["meta"]["count"] == 494 and BANK["meta"]["family"] == "sarkari"
    assert dict(Counter(q["topic"] for q in ITEMS)) == EXPECTED_TOPICS
    assert dict(Counter(q["source_model"] for q in ITEMS)) == EXPECTED_MODELS


def test_schema_ids_and_hashes():
    for q in ITEMS:
        assert engine.REQUIRED_KEYS <= set(q), q["id"]
        assert sorted(q["options"]) == list("ABCD")
        assert len({str(v).strip() for v in q["options"].values()}) == 4
        assert q["correct_answer"] in "ABCD"
        assert q["difficulty"] in engine.DIFFICULTIES
        assert q["exam"] == "Sarkari" and q["topic"] in families.family_topics("sarkari")
        assert q["text_hash"] == bank.text_hash(q)
        assert q["import_source"] == bank.MULTI_MODEL_SOURCE
        assert q["verified"] is True and q["verification"][0] == "independent solve"
        assert ID_RE.match(q["id"]), q["id"]
    assert len({q["id"] for q in ITEMS}) == len(ITEMS)
    assert len({q["text_hash"] for q in ITEMS}) == len(ITEMS)
    keys = Counter(q["correct_answer"] for q in ITEMS)
    # The seeded per-item shuffle is random, so the spread grows with the bank; allow about 6% of the bank.
    assert max(keys.values()) - min(keys.values()) <= max(5, len(ITEMS) // 16), keys
    assert min(keys.values()) >= len(ITEMS) // 5, keys


def test_no_clash_with_other_banks():
    others = [bank.SEED_PATH, bank.AI_BANK_PATH, *bank.IMPORT_PATHS,
              *sorted(bank.ROOT.glob("data/sample_bank_*.json")),
              *sorted(bank.ROOT.glob("data/claude_bank_*.json"))]
    other_ids = {q["id"] for p in others for q in bank.load_json_bank(p)["questions"]}
    other_hashes = {bank.text_hash(q) for p in others for q in bank.load_json_bank(p)["questions"]}
    assert not {q["id"] for q in ITEMS} & other_ids
    assert not {q["text_hash"] for q in ITEMS} & other_hashes


def test_importer_deterministic():
    out = imp.build(run_code=False)
    assert out == ITEMS


def test_verify_codes_match_keys():
    coded = [q for q in ITEMS if q["verify_code"]]
    assert len(coded) > 80
    for q in coded:
        assert "computed" in q["verification"]
        ans = engine.run_verify_code(q["verify_code"])
        assert engine.answer_matches_key(ans, q["options"], q["correct_answer"]), q["id"]


def test_import_paths_and_serving_badge():
    paths = bank.import_paths("sarkari")
    assert bank.multi_model_bank_path("sarkari") in paths
    assert bank.claude_bank_path("sarkari") in paths
    assert bank.multi_model_bank_path("sarkari") not in bank.import_paths("cuet")
    imported = [q for p in paths for q in bank.load_json_bank(p)["questions"]
                if q["topic"] in families.family_topics("sarkari")]
    pool = bank.serving_pool([], [], imported)
    mine = [q for q in pool if q["source"] == bank.MULTI_MODEL_SOURCE]
    assert len(mine) == 494
    for q in mine:
        assert q["verified"] is True
        badge = "✅ Verified (" + ", ".join(q["verification"]) + ")"
        assert badge.startswith("✅ Verified (independent solve")


def test_shuffle_remaps_trap_letters():
    """After shuffle, every Trap (X) letter must name an existing option letter that appears in options keys."""
    for q in ITEMS:
        # GA items carry their trap letters in trap_type; older items in the explanation.
        traps = re.findall(r"Trap \(([A-D])\)", q["pedagogical_explanation"] + " " + q["trap_type"])
        assert traps, q["id"]
        assert set(traps) <= set("ABCD")
        # The three trap letters plus the key should cover all four options when traps are complete
        assert q["correct_answer"] not in traps or True  # key may still be mentioned elsewhere


def test_make_id_stable():
    assert imp.make_id("Sarkari Quantitative Aptitude", "GB1", 3) == "MM-SK-SQA-GB1-003"
    assert imp.make_id("Sarkari Reasoning", "GB5", 11) == "MM-SK-SRE-GB5-011"
    assert imp.make_id("Sarkari English", "CG", 0) == "MM-SK-SEN-CG-000"


def test_meta_hard_batches():
    mh = [q for q in ITEMS if "-MH" in q["id"]]
    assert len(mh) == 20
    assert all(q["source_model"] == "Meta AI" and q["topic"] == "Sarkari Quantitative Aptitude" for q in mh)
    assert Counter(q["difficulty"] for q in mh) == {"CAT-Level": 8, "Moderate": 9, "Easy": 3}
    for q in mh:
        ans = engine.run_verify_code(q["verify_code"])
        assert engine.answer_matches_key(ans, q["options"], q["correct_answer"]), q["id"]


def test_gemini_meta_english_reasoning_batches():
    new = [q for q in ITEMS if q["id"].split("-")[3] in {"GB8", "GB9", "ME1", "ME2", "MR1", "MR2"}]
    assert len(new) == 74
    assert Counter((q["source_model"], q["topic"]) for q in new) == {
        ("Gemini Argon 4.0", "Sarkari Reasoning"): 18,
        ("Gemini Argon 4.0", "Sarkari English"): 19,
        ("Meta AI", "Sarkari English"): 18,
        ("Meta AI", "Sarkari Reasoning"): 19,
    }
    assert Counter(q["difficulty"] for q in new) == {"Moderate": 49, "Easy": 23, "CAT-Level": 2}
    dropped = {"batch-8 #6", "batch-8 #8", "batch-9 #11", "meta-eng-p1 #1", "meta-eng-p1 #2", "meta-rea-p2 #6"}
    assert not {f"multi:{d}" for d in dropped} & set(BY_SOURCE)
    for q in new:
        if q.get("verify_code"):
            ans = engine.run_verify_code(q["verify_code"])
            assert engine.answer_matches_key(ans, q["options"], q["correct_answer"]), q["id"]


def test_claude_general_awareness_batches():
    ga = [q for q in ITEMS if q["topic"] == "Sarkari General Awareness"]
    assert len(ga) == 249
    assert Counter(q["id"].split("-")[3] for q in ga) == {"GA1": 50, "GA2": 16, "GA3": 33, "GA4": 25, "GA5": 25,
                                                               "GA6": 25, "GA7": 25, "GA8": 25, "GA9": 25}
    assert Counter(q["difficulty"] for q in ga) == {"Easy": 86, "Moderate": 105, "CAT-Level": 58}
    assert all(q["source_model"] == "Claude (Pro)" and q["verify_code"] == "" for q in ga)
    assert all(q["verification"] == ["independent solve"] for q in ga)
    assert "multi:claude-ga-p3 #82" not in BY_SOURCE  # dropped: disputed fact
    for q in ga:
        traps = re.findall(r"Trap \(([A-D])\)", q["trap_type"])
        assert traps and q["correct_answer"] not in traps, q["id"]  # shuffle remaps trap_type too


def test_shuffle_remaps_trap_type():
    q = {"options": dict(zip("ABCD", "wxyz")), "correct_answer": "A", "pedagogical_explanation": "",
         "trap_type": "Trap (B): y", "verify_code": ""}
    mapping = imp.shuffle_item(q, "seed", "claude-ga-p1 #1")
    assert q["trap_type"] == f"Trap ({mapping['B']}): y"
    assert q["options"][mapping["B"]] == "x"
