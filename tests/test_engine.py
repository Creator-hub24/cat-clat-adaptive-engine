import datetime as dt
import json
import pathlib

import pytest

import engine
import llm
import store

BANK = json.loads((pathlib.Path(__file__).parent.parent / "data/sample_bank.json").read_text())["questions"]


# ---------- adaptive stepping
def run(seq, start="Easy"):
    st = engine.new_topic_state(start)
    for correct, slow in seq:
        st = engine.update_level(st, correct, slow)
    return st["level"]


def test_step_up_after_two_fast_correct():
    assert run([(True, False)]) == "Easy"
    assert run([(True, False)] * 2) == "Moderate"
    assert run([(True, False)] * 4) == "CAT-Level"
    assert run([(True, False)] * 10) == "CAT-Level"


def test_slow_correct_does_not_count():
    assert run([(True, False), (True, True), (True, False)]) == "Moderate"  # only 2 fast, not consecutive-reset
    assert run([(True, True)] * 5) == "Easy"


def test_step_down_after_two_wrong_and_floor():
    assert run([(False, False)] * 2, "CAT-Level") == "Moderate"
    assert run([(False, False), (True, True), (False, False)], "CAT-Level") == "CAT-Level"
    assert run([(False, False)] * 6, "Moderate") == "Easy"


# ---------- spacing
def test_review_intervals_3_7_15():
    assert engine.REVIEW_INTERVALS == [3, 7, 15]
    log, q = {}, {"id": "X"}
    engine.schedule_mistake(log, q, "A", 10)
    assert log["X"]["due_at"] == 13
    engine.advance_review(log, "X", 13)
    assert log["X"]["due_at"] == 20
    engine.advance_review(log, "X", 20)
    assert log["X"]["due_at"] == 35
    engine.advance_review(log, "X", 35)
    assert "X" not in log


# ---------- timing
def test_timing_targets_and_classification():
    assert engine.target_seconds("CAT Quant", "Easy") == (45, 60)
    rc = engine.target_seconds("CAT VARC RC", "Easy", " ".join(["w"] * 500) + "\n\nQ?")
    assert rc == (165, 180)
    assert engine.classify(True, 200, (90, 120)) == "Right but too slow"
    assert engine.classify(True, 100, (90, 120)) == "Right & on time"
    assert engine.classify(False, 10, (90, 120)) == "Wrong"


# ---------- sandbox
def test_sandbox_computes_answer():
    assert engine.run_verify_code("import math\nanswer = math.comb(5, 2)") == 10
    assert engine.answer_matches_key(10, {"A": "8", "B": "10", "C": "12", "D": "15"}, "B")
    assert not engine.answer_matches_key(10, {"A": "8", "B": "10", "C": "12", "D": "15"}, "A")


@pytest.mark.parametrize("code", [
    "import os\nanswer = 1",
    "answer = open('/etc/passwd').read()",
    "answer = ().__class__.__bases__",
    "import socket\nanswer = 1",
    "answer = __import__('os')",
    "answer = eval('1')",
])
def test_sandbox_blocks_unsafe(code):
    with pytest.raises(Exception):
        engine.run_verify_code(code)


def test_sandbox_timeout():
    with pytest.raises(Exception):
        engine.run_verify_code("while True:\n    pass", timeout=1)


# ---------- seed bank
def test_seed_bank_coverage():
    assert len(BANK) >= 45 and len({q["id"] for q in BANK}) == len(BANK)
    from collections import Counter
    c = Counter(q["topic"] for q in BANK)
    assert all(v >= 9 for v in c.values()) and len(c) == 5
    assert {q["difficulty"] for q in BANK} == set(engine.DIFFICULTIES)


def test_every_quant_and_coded_answer_verified():
    for q in BANK:
        if q["topic"] == "CAT Quant":
            assert q.get("verify_code"), q["id"]
        if q.get("verify_code"):
            assert engine.answer_matches_key(engine.run_verify_code(q["verify_code"]), q["options"],
                                             q["correct_answer"]), q["id"]


def test_daily_pick_no_repeats_for_full_cycle():
    d0 = dt.date(2026, 1, 1)
    ids = [engine.daily_pick(BANK, d0 + dt.timedelta(days=i))["id"] for i in range(len(BANK))]
    assert len(set(ids)) == len(BANK)


# ---------- generation pipeline (fake client, no network)
class _Resp:
    def __init__(self, t): self.text = t


class FakeClient:
    def __init__(self, gen, solve):
        self.gen, self.solve, self.models = gen, solve, self
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        if "independent" in (config.system_instruction or ""):
            return _Resp(json.dumps({"answer": self.solve, "ambiguous": False}))
        return _Resp(json.dumps(self.gen))


GOOD = {"question_text": "5C2?", "options": {"A": "8", "B": "10", "C": "12", "D": "15"}, "correct_answer": "B",
        "pedagogical_explanation": "x", "trap_type": "t", "concept_tag": "c",
        "verify_code": "import math\nanswer = math.comb(5,2)"}


def test_generate_verified_ok_records_model():
    q = llm.generate_verified(FakeClient(GOOD, "B"), ["m1"], "CAT Quant", "Easy", "p", "s")
    assert q["verified"] and q["model"] == "m1" and q["verification"] == ["computed", "independent solve"]


def test_generate_rejects_wrong_key_and_solver_disagreement():
    bad = dict(GOOD, correct_answer="C")
    with pytest.raises(RuntimeError):
        llm.generate_verified(FakeClient(bad, "C"), ["m1"], "CAT Quant", "Easy", "p", "s")
    with pytest.raises(RuntimeError):
        llm.generate_verified(FakeClient(GOOD, "A"), ["m1"], "CAT Quant", "Easy", "p", "s")
    nocode = {k: v for k, v in GOOD.items() if k != "verify_code"}
    with pytest.raises(RuntimeError):
        llm.generate_verified(FakeClient(nocode, "B"), ["m1"], "CAT Quant", "Easy", "p", "s")
    # non-computable topic: solver agreement alone is enough
    assert llm.generate_verified(FakeClient(nocode, "B"), ["m1"], "CLAT RC", "Easy", "p", "s")["verified"]


# ---------- reports are anonymous
def test_reports_have_no_personal_data():
    r = store.clean_report({"topic": "CAT Quant", "question_ref": "Q-E-01", "reason": "Wrong answer key",
                            "user_id": "abc", "email": "a@b.c"})
    assert set(r) == {"topic", "question_ref", "reason", "created_at"}
    assert store.question_ref({"id": "AI-123", "question_text": "hi"}).startswith("AI-")
