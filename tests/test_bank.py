import csv
import json
import random

import pytest

import bank
from scripts import apply_review, build_bank, export_review


class _Resp:
    def __init__(self, t): self.text = t


class FakeGemini:
    """Generator returns a fresh computed Quant/DILR or text question each call; solver agrees unless told."""

    def __init__(self, wrong_every=0, fail_429_first=0):
        self.n, self.wrong_every, self.fail_429 = 0, wrong_every, fail_429_first
        self.models = self

    def generate_content(self, model, contents, config):
        if self.fail_429 > 0:
            self.fail_429 -= 1
            raise RuntimeError("429 RESOURCE_EXHAUSTED rate limit")
        if "independent" in config.system_instruction:
            return _Resp(json.dumps({"answer": "B", "ambiguous": False}))
        self.n += 1
        k = self.n
        key = "C" if self.wrong_every and k % self.wrong_every == 0 else "B"
        words = " ".join(f"w{k}x{i}" for i in range(12))
        return _Resp(json.dumps({
            "question_text": f"Unique question {k}: {words}. What is {k} + 1?",
            "options": {"A": str(k), "B": str(k + 1), "C": str(k + 2), "D": str(k + 3)},
            "correct_answer": key, "pedagogical_explanation": "add one", "trap_type": "off-by-one",
            "concept_tag": f"c{k}", "verify_code": f"answer = {k} + 1"}))


def throttled(fake, max_calls=10_000):
    return build_bank.ThrottledClient(fake, rpm=1e9, max_calls=max_calls, sleep=lambda s: None)


def test_dedupe_exact_and_near():
    a = {"id": "1", "topic": "T", "question_text": "A train travels 120 km in 2 hours at constant speed. Find speed.",
         "options": {"A": "1"}}
    b = dict(a, id="2")
    c = dict(a, id="3", question_text=a["question_text"] + " Give the answer in km/h.")
    d = dict(a, id="4", question_text="Completely different passage about contracts and consideration.")
    assert "exact" in bank.is_duplicate(b, [a])
    assert "near" in bank.is_duplicate(c, [a])
    assert bank.is_duplicate(d, [a]) is None


def test_build_fills_cells_evenly_and_resumes(tmp_path):
    out = tmp_path / "ai.json"
    build_bank.build(throttled(FakeGemini()), 2, out, topics=["CAT Quant", "CLAT RC"],
                     difficulties=["Easy", "Moderate"], log=lambda *_: None)
    qs = bank.load_json_bank(out)["questions"]
    assert len(qs) == 8
    assert all(build_bank.cell_counts(qs)[c] == 2 for c in build_bank.cell_counts(qs))
    q = qs[0]
    assert q["review_status"] == "unreviewed" and q["model"] and q["created_at"] and q["verified"]
    assert q["verified_independent"]
    # resume: raising the target only adds the missing ones, existing kept
    build_bank.build(throttled(FakeGemini()), 3, out, topics=["CAT Quant", "CLAT RC"],
                     difficulties=["Easy", "Moderate"], log=lambda *_: None)
    qs2 = bank.load_json_bank(out)["questions"]
    assert len(qs2) == 12 and [x["id"] for x in qs2[:8]] == [x["id"] for x in qs]


def test_build_rejects_wrong_keys_and_counts(tmp_path):
    out = tmp_path / "ai.json"
    build_bank.build(throttled(FakeGemini(wrong_every=2)), 2, out, topics=["CAT Quant"],
                     difficulties=["Easy"], log=lambda *_: None)
    d = bank.load_json_bank(out)
    assert len(d["questions"]) == 2
    assert d["build_stats"]["CAT Quant"]["rejected"] >= 1
    assert all(q["correct_answer"] == "B" for q in d["questions"])


def test_backoff_on_429_and_quota_stop(tmp_path):
    out = tmp_path / "ai.json"
    build_bank.build(throttled(FakeGemini(fail_429_first=2)), 1, out, topics=["CAT Quant"],
                     difficulties=["Easy"], log=lambda *_: None)
    assert len(bank.load_json_bank(out)["questions"]) == 1
    with pytest.raises(build_bank.QuotaStop):
        build_bank.build(throttled(FakeGemini(), max_calls=3), 5, out, topics=["CAT Quant"],
                         difficulties=["Easy"], log=lambda *_: None)
    assert len(bank.load_json_bank(out)["questions"]) >= 1   # progress kept


def test_export_and_apply_review_roundtrip(tmp_path):
    out, csvp = tmp_path / "ai.json", tmp_path / "r.csv"
    build_bank.build(throttled(FakeGemini()), 3, out, topics=["CAT Quant"], difficulties=["Easy"],
                     log=lambda *_: None)
    assert export_review.export(out, csvp) == 3
    rows = list(csv.DictReader(open(csvp, encoding="utf-8-sig")))
    assert set(export_review.FIELDS) <= set(rows[0])
    rows[0]["approve"], rows[1]["approve"] = "Y", "n"
    with open(csvp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, export_review.FIELDS); w.writeheader(); w.writerows(rows)
    res = apply_review.apply(csvp, out, reviewer="VG")
    assert (res["approved"], res["rejected"], res["unchanged"]) == (1, 1, 1)
    qs = bank.load_json_bank(out)["questions"]
    st = {q["id"]: q["review_status"] for q in qs}
    assert st[rows[0]["id"]] == "approved" and st[rows[1]["id"]] == "rejected"
    pool = bank.serving_pool([], qs)
    assert rows[1]["id"] not in {q["id"] for q in pool} and len(pool) == 2


def test_pick_unseen_exhausts_then_none():
    pool = [{"id": str(i), "topic": "T", "difficulty": "Easy"} for i in range(3)]
    seen, rng = set(), random.Random(0)
    for _ in range(3):
        seen.add(bank.pick_unseen(pool, "T", "Easy", seen, rng)["id"])
    assert seen == {"0", "1", "2"} and bank.pick_unseen(pool, "T", "Easy", seen, rng) is None


class DailyCapGemini(FakeGemini):
    def __init__(self, cap):
        super().__init__(); self.cap, self.used = cap, {}

    def generate_content(self, model, contents, config):
        self.used[model] = self.used.get(model, 0) + 1
        if self.used[model] > self.cap:
            raise RuntimeError("429 RESOURCE_EXHAUSTED quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return super().generate_content(model, contents, config)


def test_daily_quota_skips_model_then_stops(tmp_path):
    out = tmp_path / "ai.json"
    fake = DailyCapGemini(cap=3)
    with pytest.raises(build_bank.QuotaStop):
        build_bank.build(throttled(fake), 50, out, topics=["CAT Quant"], difficulties=["Easy"], log=lambda *_: None)
    n = len(bank.load_json_bank(out)["questions"])
    assert n >= 3                                    # kept working on later models after the first ran out
    assert all(v <= 4 for v in fake.used.values())   # never hammered an exhausted model
