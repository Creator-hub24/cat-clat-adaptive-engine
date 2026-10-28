import json

import bank
from scripts import import_aptisetu as imp

SAMPLE = {
    "sets": {
        "cv-x": {"kind": "passage", "title": "T", "html": "<b>T</b><p>First para.</p><p>Second para.</p>"},
        "cd-x": {"kind": "dilr", "title": "S", "html": "<b>S</b><p>Data.</p><table><tr><th>A</th><th>B</th></tr>"
                                                     "<tr><td>1</td><td>2</td></tr></table>"},
    },
    "sections": {
        "qa": {"questions": [
            {"id": "Q1", "type": "mcq", "topic": "Inequalities", "level": "Hard", "question": "Solve x<sup>2</sup> &lt; 4",
             "options": ["x < 2 or x > 5", "b", "c", "d"], "answer": 0, "solution": "Option 1 is right; option 3 traps."},
            {"id": "Q2", "type": "tita", "kind": "number", "level": "Easy", "question": "n?", "answer": "3",
             "solution": ""},
            {"id": "Q3", "type": "mcq", "topic": "X", "level": "Easy", "question": "q", "options": ["a", "b", "c"],
             "answer": 0, "solution": ""}]},
        "dilr": {"questions": [
            {"id": "D1", "type": "mcq", "topic": "Tables", "level": "Medium", "set": "cd-x", "question": "Who?",
             "options": ["a", "b", "c", "d"], "answer": 2, "solution": "Option 3."}]},
        "varc": {"questions": [
            {"id": "V1", "type": "mcq", "topic": "Reading Comprehension", "level": "Easy", "set": "cv-x",
             "question": "Main idea?", "options": ["a", "b", "c", "d"], "answer": 3, "solution": ""},
            {"id": "V2", "type": "mcq", "topic": "Para-summary", "level": "Easy", "question": "s",
             "options": ["a", "b", "c", "d"], "answer": 0, "solution": ""}]},
    },
}


def test_convert_maps_fields_and_skips():
    out, skipped = imp.convert(SAMPLE)
    by = {q["id"]: q for q in out}
    assert set(by) == {"AS-QA-Q1", "AS-DI-D1", "AS-VR-V1"}
    qa = by["AS-QA-Q1"]
    assert qa["topic"] == "CAT Quant" and qa["difficulty"] == "CAT-Level" and qa["correct_answer"] == "A"
    assert qa["options"]["A"] == "x < 2 or x > 5" and "x^2 < 4" in qa["question_text"]
    assert "Option A is right; Option C" in qa["pedagogical_explanation"]
    di = by["AS-DI-D1"]
    assert di["correct_answer"] == "C" and di["difficulty"] == "Moderate"
    assert "| A | B |" in di["question_text"] and "| 1 | 2 |" in di["question_text"]
    rc = by["AS-VR-V1"]
    assert rc["question_text"].startswith("Passage: First para.\nSecond para.\n\nMain idea?")
    assert rc["correct_answer"] == "D" and rc["difficulty"] == "Easy"
    assert sum(v for k, v in skipped.items() if "TITA" in k) == 1
    assert skipped["varc: Para-summary (no engine topic)"] == 1
    assert skipped["qa: options not exactly 4 / bad answer"] == 1


def test_dedupe_against_existing():
    out, _ = imp.convert(SAMPLE)
    keep, dropped = imp.dedupe(out + [dict(out[0])], [])
    assert len(keep) == 3 and len(dropped) == 1
    keep, dropped = imp.dedupe(out, [out[0]])
    assert len(keep) == 2


def test_shipped_bank_is_valid_and_served():
    qs = bank.load_json_bank(bank.APTISETU_PATH)["questions"]
    assert qs and len({q["id"] for q in qs}) == len(qs)
    for q in qs:
        assert q["id"].startswith(("AS-QA-", "AS-DI-", "AS-VR-"))
        assert set(q["options"]) == set("ABCD") and q["correct_answer"] in "ABCD"
        assert q["topic"] in ("CAT Quant", "CAT DILR", "CAT VARC RC")
        assert q["difficulty"] in ("Easy", "Moderate", "CAT-Level")
        assert "<" not in q["question_text"] or "<p>" not in q["question_text"]
    seed = bank.load_json_bank(bank.SEED_PATH)["questions"]
    base = bank.serving_pool(seed, [])
    pool = bank.serving_pool(seed, [], qs)
    served = [q for q in qs if not q.get("excluded")]
    assert pool[:len(base)] == base and len(pool) == len(base) + len(served)
    assert all(q["source"] == "AptiSetu bank" for q in pool[len(base):])


# ---------------------------------------------------------------- curation (data/aptisetu_curation)
import re  # noqa: E402
from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402

CUR = imp.load_curation()
SHIPPED = bank.load_json_bank(bank.APTISETU_PATH)["questions"]
BY_ID = {q["id"]: q for q in SHIPPED}
SEED = bank.load_json_bank(bank.SEED_PATH)["questions"]
SERVED = [q for q in bank.serving_pool(SEED, [], SHIPPED) if q["source"] == "AptiSetu bank"]
SERIES = CUR["fixes"]["option_shuffle"]["series"]


def test_verified_flag_applied():
    verified = set(CUR["verified"]["ids"])
    assert len(verified) == 492
    for q in SHIPPED:
        assert q["verified"] is (q["id"] in verified)
        if q["verified"]:
            assert q["verification"] and "independent solve" in q["verification"]
    # every served AptiSetu item is verified, and the pool passes the flag through (no blanket label)
    assert SERVED and all(q["verified"] and q["verification"] for q in SERVED)
    unverified = dict(SHIPPED[0], id="AS-QA-X", verified=False)
    unverified.pop("verification", None)
    (q,) = [p for p in bank.serving_pool([], [], [unverified])]
    assert q["verified"] is False and q["verification"] == []


def test_exclusions_kept_but_not_served():
    ex = {e["id"]: e for e in CUR["exclusions"]["items"]}
    assert len(ex) == 21
    assert Counter(e["category"] for e in ex.values()) == {"ambiguous": 2, "answer_giveaway": 15, "unknown_person": 4}
    served = {q["id"] for q in SERVED}
    for i, e in ex.items():
        assert BY_ID[i]["excluded"]["reason"] == e["reason"]  # record kept in the bank for a later fix
        assert i not in served
    assert all(not q.get("excluded") for q in SERVED)
    assert len(SERVED) == len(SHIPPED) - len(ex) == 469


def test_duplicates_dropped_and_no_duplicate_stems():
    for p in CUR["duplicates"]["pairs"]:
        assert p["drop"] not in BY_ID and p["keep"] in BY_ID
    full = Counter(bank.normalize(q["question_text"]) for q in SHIPPED)
    assert max(full.values()) == 1
    qa = Counter(bank.normalize(q["question_text"]) for q in SHIPPED if q["topic"] == "CAT Quant")
    assert max(qa.values()) == 1
    assert len({q["text_hash"] for q in SHIPPED}) == len(SHIPPED)


def test_key_distribution_balanced():
    for p in SERIES:
        c = Counter(q["correct_answer"] for q in SHIPPED if q["id"].startswith(p))
        n = sum(c.values())
        assert n == 16 and all(abs(c[k] - n / 4) <= 1 for k in "ABCD"), (p, c)
    for topic in ("CAT Quant", "CAT DILR", "CAT VARC RC"):
        c = Counter(q["correct_answer"] for q in SERVED if q["topic"] == topic)
        assert max(c.values()) / sum(c.values()) < 0.4 and min(c.values()) / sum(c.values()) > 0.12, (topic, c)


def test_shuffled_keys_map_to_same_option_text():
    snap = json.loads((Path(__file__).parent / "fixtures" / "aptisetu_shuffled_keys.json").read_text(encoding="utf-8"))
    items = snap["items"]
    assert len(items) == 96 == sum(1 for q in SHIPPED if imp.series_of(q["id"], SERIES))
    moved = 0
    for i, s in items.items():
        q = BY_ID[i]
        assert q["options"][q["correct_answer"]] == s["key_text"], i
        assert len(set(q["options"].values())) == 4
        moved += q["correct_answer"] != s["source_key"]
        # multi-option dismissals in the explanation never name the key after remapping
        for ref in re.findall(r"\bOptions\s+((?:[A-D])(?:(?:,\s*|\s+and\s+|\s+or\s+)[A-D])+)", q["pedagogical_explanation"]):
            assert q["correct_answer"] not in ref, (i, ref)
        assert not re.search(r"\bOptions?\s+[1-4]\b", q["pedagogical_explanation"]), i
    assert moved > 50


def test_balanced_shuffle_remaps_options_and_refs():
    items = [{"id": f"S-{k}", "options": dict(zip("ABCD", ["w", "x", "y", "z"])), "correct_answer": "B",
              "pedagogical_explanation": "Option B is right. Options 1 and 4 are wrong; Option C too."} for k in range(8)]
    maps = imp.balanced_shuffle(items, ["S-"], "t")
    assert Counter(q["correct_answer"] for q in items) == {k: 2 for k in "ABCD"}
    for q in items:
        m = maps[q["id"]]
        assert q["options"][q["correct_answer"]] == "x"
        assert all(q["options"][m[o]] == t for o, t in zip("ABCD", "wxyz"))
        assert q["pedagogical_explanation"] == (f"Option {m['B']} is right. Options {m['A']} and {m['D']} are wrong; "
                                                f"Option {m['C']} too.")
    again = [dict(q, options=dict(zip("ABCD", "wxyz")), correct_answer="B",
                  pedagogical_explanation="Option B") for q in items]
    imp.balanced_shuffle(again, ["S-"], "t")
    assert [q["correct_answer"] for q in again] == [q["correct_answer"] for q in items]  # deterministic seed


def test_table_inside_paragraph_becomes_markdown_table():
    blocks = imp.html_to_blocks("<p>Intro.<table><tr><th></th><th>X</th></tr><tr><td>P</td><td>5</td></tr></table></p>"
                                "<p>After.</p>")
    assert blocks == ["Intro.", "|  | X |\n|---|---|\n| P | 5 |", "After."]
    for i in ("DS1-TABLE4-17", "DS2-TABLE2-10", "M1-TABLE4-17", "M3-TABLE5-22", "M4-TABLE1-02", "M5-TABLE4-18",
              "DP-TABLE4-18", "DP-TABLE9-40"):
        t = BY_ID["AS-DI-" + i]["question_text"]
        assert "\n|---|---|---|---|\n" in t and len(re.findall(r"^\| ", t, re.M)) == 5, i


def test_stem_fixes_use_mcq_wording():
    assert "Which option gives the ratio" in BY_ID["AS-QA-M3-QA-04"]["question_text"]
    assert "which option gives k" in BY_ID["AS-QA-M3-QA-17"]["question_text"]
    assert not [q["id"] for q in SERVED if re.search(r"\bEnter (the|your)\b", q["question_text"])]
    bad = [dict(SHIPPED[0], id="Z")]
    try:
        imp.apply_stem_fixes(bad, [{"id": "Z", "find": "no such text", "replace": "x"}])
        raise AssertionError("missing fix text must fail loudly")
    except ValueError:
        pass
