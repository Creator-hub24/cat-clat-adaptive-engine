"""CAT DILR: verify_code is required and must list every consistent answer (uniqueness contract)."""
import csv
import json
import pathlib

import pytest

import bank
import engine
import llm
import prompts
from scripts import audit_bank, build_bank, export_review

ROOT = pathlib.Path(__file__).resolve().parents[1]
OPTS = {"A": "1", "B": "2", "C": "3", "D": "4"}
CONTRACT = "answers = set()\nfor x in range(1, 5):\n    if x * x == 9:\n        answers.add(x)\nanswer = 3"
NO_CONTRACT = "answer = 3"
TWO_FIT = "answers = {x for x in range(1, 5) if x > 2}\nanswer = 3"


# ---------- runner and contract checks
def test_runner_reports_distinct_normalised_answers():
    res = engine.run_verify_code_full("import fractions\nanswers = [3, 3.0, fractions.Fraction(6, 2)]\nanswer = 3")
    assert res == {"answer": 3, "answers": [3]}
    assert engine.run_verify_code_full("answers = {(1, 2), (1, 2)}")["answers"] == [[1, 2]]
    assert "answers" not in engine.run_verify_code_full(NO_CONTRACT)
    assert engine.run_verify_code_full("answers = 5\nanswer = 5")["answers"] is None
    assert engine.run_verify_code(CONTRACT) == 3            # old single-answer API unchanged


def test_check_unique_answers_reasons():
    ok = engine.run_verify_code_full(CONTRACT)
    assert engine.check_unique_answers(ok, OPTS, "C") is None
    assert "does not assign `answers`" in engine.check_unique_answers({"answer": 3}, OPTS, "C")
    assert "list or set" in engine.check_unique_answers({"answer": 3, "answers": None}, OPTS, "C")
    assert "no arrangement" in engine.check_unique_answers({"answer": None, "answers": []}, OPTS, "C")
    assert "not unique: 2" in engine.check_unique_answers(engine.run_verify_code_full(TWO_FIT), OPTS, "C")
    assert "does not match key B" in engine.check_unique_answers(ok, OPTS, "B")
    assert "`answer` 4" in engine.check_unique_answers({"answer": 4, "answers": [3]}, OPTS, "C")
    assert engine.check_unique_answers({"answer": None, "answers": ["C"]}, OPTS, "C") is None  # option letter


def test_uses_answers_contract_is_static():
    assert engine.uses_answers_contract(CONTRACT) and engine.uses_answers_contract("answers: set = {1}")
    assert not engine.uses_answers_contract(NO_CONTRACT)
    assert not engine.uses_answers_contract(None) and not engine.uses_answers_contract("answers = (")
    assert not engine.uses_answers_contract("print(answers)")


def test_topic_sets():
    assert engine.CODE_REQUIRED_TOPICS == engine.QUANT_TOPICS | {"CAT DILR"}
    assert engine.UNIQUE_ANSWER_TOPICS == {"CAT DILR"} <= engine.COMPUTABLE_TOPICS


# ---------- generation (fake client, no network)
class _Resp:
    def __init__(self, t): self.text = t


class FakeClient:
    def __init__(self, gens, solve="C"):
        self.gens, self.solve, self.models, self.gen_calls = list(gens), solve, self, 0

    def generate_content(self, model, contents, config):
        if "independent" in (config.system_instruction or ""):
            return _Resp(json.dumps({"answer": self.solve, "ambiguous": False}))
        self.gen_calls += 1
        return _Resp(json.dumps(self.gens[min(self.gen_calls - 1, len(self.gens) - 1)]))


def dilr(code=CONTRACT, k=0, **kw):
    q = {"question_text": f"Set {k}: four friends sit in a row under these conditions. Who sits third?",
         "options": dict(OPTS), "correct_answer": "C", "pedagogical_explanation": "Only 3 fits.",
         "trap_type": "t", "concept_tag": f"c{k}"}
    if code is not None:
        q["verify_code"] = code
    q.update(kw)
    return q


def gen(client, topic="CAT DILR", tries=2):
    return llm.generate_verified(client, ["m1"], topic, "Easy", "p", "s", max_tries=tries)


def test_generate_dilr_accepts_contract_with_unique_answer():
    q = gen(FakeClient([dilr()]))
    assert q["verification"] == ["computed", "unique solution", "independent solve"]
    q = gen(FakeClient([dilr("answers = {'C'}")]))      # `answers` alone is enough
    assert "unique solution" in q["verification"]


@pytest.mark.parametrize("code, why", [(None, "no verify_code"), (NO_CONTRACT, "does not assign `answers`"),
                                       (TWO_FIT, "not unique"), ("answers = set()", "no arrangement")])
def test_generate_dilr_rejects_and_regenerates(code, why):
    log = []
    client = FakeClient([dilr(code), dilr()])            # first try fails, the regeneration passes
    q = llm.generate_verified(client, ["m1"], "CAT DILR", "Easy", "p", "s", max_tries=2, log=log)
    assert client.gen_calls == 2 and why in log[0] and "unique solution" in q["verification"]
    with pytest.raises(RuntimeError, match=why.split("`")[0]):
        gen(FakeClient([dilr(code)]))


def test_quant_behaviour_unchanged():
    q = gen(FakeClient([dilr(NO_CONTRACT)]), topic="CAT Quant")
    assert q["verification"] == ["computed", "independent solve"]
    with pytest.raises(RuntimeError, match="no verify_code"):
        gen(FakeClient([dilr(None)]), topic="CAT Quant")
    assert gen(FakeClient([dilr(None)]), topic="CLAT RC")["verification"] == ["independent solve"]


def test_prompt_teaches_contract_and_hides_old_style_dilr_code():
    assert "answers" in prompts.TOPIC_RULES["CAT DILR"] and "answers" in prompts.SYSTEM_PROMPT
    assert "verify_code" not in prompts.shot_fields("CAT DILR", dilr(NO_CONTRACT))
    assert prompts.shot_fields("CAT DILR", dilr(CONTRACT))["verify_code"] == CONTRACT
    assert "verify_code" in prompts.shot_fields("CAT Quant", dilr(NO_CONTRACT))
    p = prompts.build_prompt("CAT DILR", "Easy", [dilr(NO_CONTRACT, k=1), dilr(CONTRACT, k=2)])
    assert p.count('"verify_code"') == 1 and "Set 1" in p and "Set 2" in p


# ---------- build_bank guard (daily routine path)
class FakeGemini(FakeClient):
    def __init__(self, contract=True):
        super().__init__([])
        self.contract = contract

    def generate_content(self, model, contents, config):
        if "independent" in (config.system_instruction or ""):
            return _Resp(json.dumps({"answer": "C", "ambiguous": False}))
        self.gen_calls += 1
        k = self.gen_calls
        code = f"answers = {{{k} + 2}}\nanswer = {k} + 2" if self.contract else f"answer = {k} + 2"
        words = " ".join(f"w{k}x{i}" for i in range(12))
        return _Resp(json.dumps(dilr(code, k, question_text=f"Arrangement {k}: {words}. Which value fits?",
                                     options={"A": str(k), "B": str(k + 1), "C": str(k + 2), "D": str(k + 3)})))


def throttled(fake):
    return build_bank.ThrottledClient(fake, rpm=1e9, max_calls=10_000, sleep=lambda s: None)


def test_build_bank_banks_contract_dilr_items(tmp_path):
    out = tmp_path / "ai.json"
    build_bank.build(throttled(FakeGemini()), 2, out, topics=["CAT DILR"], difficulties=["Easy"], log=lambda *_: None)
    qs = bank.load_json_bank(out)["questions"]
    assert len(qs) == 2 and all(q["verified_unique"] and q["verified_computed"] for q in qs)


def test_build_bank_regenerates_then_skips_dilr_without_contract(tmp_path):
    out = tmp_path / "ai.json"
    fake = FakeGemini(contract=False)
    build_bank.build(throttled(fake), 2, out, topics=["CAT DILR"], difficulties=["Easy"], max_fail_per_cell=3,
                     log=lambda *_: None)
    data = bank.load_json_bank(out)
    assert data["questions"] == [] and fake.gen_calls == 6       # 3 cell attempts x 2 tries each
    assert data[build_bank.STATS_KEY]["CAT DILR"]["rejected"] >= 3


def test_build_bank_guard_rejects_items_missing_required_checks(tmp_path, monkeypatch):
    assert build_bank.missing_required_checks("CAT DILR", {"verification": ["independent solve"]})
    assert "uniqueness" in build_bank.missing_required_checks("CAT DILR", {"verification": ["computed"]})
    assert build_bank.missing_required_checks("CAT Quant", {"verification": ["independent solve"]})
    assert build_bank.missing_required_checks("CAT Quant", {"verification": ["computed", "independent solve"]}) is None
    assert build_bank.missing_required_checks("CLAT RC", {"verification": ["independent solve"]}) is None
    monkeypatch.setattr(build_bank.llm, "generate_verified",
                        lambda *a, **k: dict(dilr(None), id="AI-1", topic="CAT DILR", difficulty="Easy",
                                             verified=True, verification=["independent solve"], model="m"))
    out = tmp_path / "ai.json"
    build_bank.build(None, 1, out, topics=["CAT DILR"], difficulties=["Easy"], max_fail_per_cell=2,
                     log=lambda *_: None)
    assert bank.load_json_bank(out)["questions"] == []


# ---------- audit and faculty review CSV
def test_audit_flags_dilr_code_issues():
    base = dict(dilr(), id="X", topic="CAT DILR")
    assert audit_bank.dilr_code_issues(base) == []
    assert "no verify_code" in audit_bank.dilr_code_issues(dict(base, verify_code=""))[0]
    assert audit_bank.dilr_code_issues(dict(base, verify_code=NO_CONTRACT))[0].startswith("warn:")
    assert "not unique" in audit_bank.dilr_code_issues(dict(base, verify_code=TWO_FIT))[0]
    assert "failed to run" in audit_bank.dilr_code_issues(dict(base, verify_code="answers = 1/0"))[0]
    assert audit_bank.dilr_code_issues(dict(base, topic="CAT Quant", verify_code="")) == []
    assert any("uniqueness" in s for s in audit_bank.static_issues(dict(base, verify_code=NO_CONTRACT)))


def test_export_review_has_check_flags(tmp_path):
    out, csvp = tmp_path / "ai.json", tmp_path / "r.csv"
    qs = [dict(dilr(), id="AI-CD-1", topic="CAT DILR", difficulty="Easy"),
          dict(dilr(NO_CONTRACT, 2), id="AI-CD-2", topic="CAT DILR", difficulty="Easy"),
          dict(dilr(None, 3), id="AI-CQ-3", topic="CAT Quant", difficulty="Easy")]
    out.write_text(json.dumps({"questions": qs}))
    export_review.export(out, csvp)
    rows = {r["id"]: r for r in csv.DictReader(open(csvp, encoding="utf-8-sig"))}
    assert "check_flags" in export_review.FIELDS
    assert rows["AI-CD-1"]["check_flags"] == "" and rows["AI-CQ-3"]["check_flags"] == ""
    assert "uniqueness" in rows["AI-CD-2"]["check_flags"]


# ---------- live bank data
AI_BANK = json.loads((ROOT / "data/ai_bank.json").read_text(encoding="utf-8"))["questions"]
UPGRADED = {"AI-CD-8325e27d": 3, "AI-CD-41a29c0d": "C", "AI-CD-ef4ab39a": 24}


@pytest.mark.parametrize("qid", sorted(UPGRADED))
def test_approved_dilr_items_meet_uniqueness_contract(qid):
    q = next(x for x in AI_BANK if x["id"] == qid)
    res = engine.run_verify_code_full(q["verify_code"])
    assert res["answers"] == [UPGRADED[qid]]
    assert engine.check_unique_answers(res, q["options"], q["correct_answer"]) is None
    assert audit_bank.dilr_code_issues(q) == [] and q["review_status"] == "approved"
    assert "unique solution" in q["verification"] and q["verified_unique"]


def test_delta_explanation_wording():
    q = next(x for x in AI_BANK if x["id"] == "AI-CD-8325e27d")
    assert "Delta's record can vary, but its points are always 3" in q["pedagogical_explanation"]
    assert "Delta actually won 1 game" not in q["pedagogical_explanation"]


def test_existing_dilr_items_without_contract_still_served():
    old = [q for q in AI_BANK if q["topic"] == "CAT DILR" and not engine.uses_answers_contract(q.get("verify_code"))]
    assert old and all(q["review_status"] == "unreviewed" for q in old)    # pending faculty review, unchanged
    for q in old:   # their single answer still verifies against the key
        assert engine.answer_matches_key(engine.run_verify_code(q["verify_code"]), q["options"], q["correct_answer"])
    legacy = dict(old[0], review_status="approved")
    assert legacy["id"] in {q["id"] for q in bank.serving_pool([], [legacy])}
