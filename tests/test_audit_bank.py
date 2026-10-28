import json
import pathlib

from scripts import audit_bank as ab

ROOT = pathlib.Path(__file__).resolve().parents[1]


def q(**kw):
    base = {"id": "T1", "topic": "CAT Quant", "question_text": "What is 2 + 3 equal to, exactly?",
            "options": {"A": "4", "B": "5", "C": "6", "D": "7"}, "correct_answer": "B",
            "pedagogical_explanation": "2 + 3 = 5."}
    base.update(kw)
    return base


def test_clean_item_has_no_issues():
    assert ab.static_issues(q()) == []
    assert ab.numeric_check(q())["derived"] == "B"


def test_invalid_key_and_options():
    assert any("not a valid option" in s for s in ab.static_issues(q(correct_answer="E")))
    assert any("exactly A-D" in s for s in ab.static_issues(q(options={"A": "1", "B": "2", "C": "3"})))
    assert any("empty option" in s for s in ab.static_issues(q(options={"A": "1", "B": "5", "C": " ", "D": "7"})))


def test_duplicates_and_empty_stem():
    assert any("duplicate option" in s for s in ab.static_issues(q(options={"A": "5", "B": "5 ", "C": "6", "D": "7"})))
    assert any("duplicate numeric" in s for s in ab.static_issues(q(options={"A": "5%", "B": "5", "C": "6", "D": "7"})))
    assert any("question_text" in s for s in ab.static_issues(q(question_text="  ")))


def test_explanation_conflicts_with_key():
    assert any("states answer C" in s for s in ab.static_issues(q(pedagogical_explanation="Work it out. Answer: (C)")))
    assert any("which is option D" in s for s in ab.static_issues(q(pedagogical_explanation="So x = 7.")))
    assert ab.numeric_check(q(pedagogical_explanation="So x = 7."))["derived"] == "D"
    assert ab.numeric_check(q(topic="CAT VARC RC")) is None


def test_disagreements_and_report(tmp_path):
    qs = [q(), q(id="T2", pedagogical_explanation="So x = 7.")]
    results = {x["id"]: {"topic": x["topic"], "key": x["correct_answer"], "static": ab.static_issues(x),
                         "numeric": ab.numeric_check(x)} for x in qs}
    results["T1"]["llm"] = {"answer": "C", "ambiguous": False}
    rows = ab.disagreements(results, qs)
    assert {r["id"] for r in rows} == {"T1", "T2"}
    out = tmp_path / "a.json"
    ab._write(out, results, qs, "run")
    assert json.loads(out.read_text())["summary"]["llm_disagreements"] == 1
    assert "| T1 |" in out.with_suffix(".md").read_text()


def test_script_is_read_only(tmp_path):
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps({"questions": [q()]}))
    before = bank.read_text()
    ab.main(
            ["--bank", str(bank), "--out", str(tmp_path / "o.json")])
    assert bank.read_text() == before and (tmp_path / "o.md").exists()
