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
    assert pool[:len(base)] == base and len(pool) == len(base) + len(qs)
    assert all(q["source"] == "AptiSetu bank" for q in pool[len(base):])
