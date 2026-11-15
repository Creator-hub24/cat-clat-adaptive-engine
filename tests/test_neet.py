"""NEET UG app (EXAM_FAMILY=medical): Biology sections, served from the scheduled AI bank (faculty review pending)."""
import collections
import datetime as dt
import json
import pathlib
import random

import bank
import engine
import families
import prompts
from scripts import build_bank

ROOT = pathlib.Path(__file__).resolve().parents[1]
NEET_TOPICS = {"NEET Botany", "NEET Zoology"}
AI = json.loads((ROOT / "data/ai_bank.json").read_text(encoding="utf-8"))["questions"]
NEET = [q for q in AI if q["topic"] in NEET_TOPICS]


def test_neet_family_config(monkeypatch):
    f = families.FAMILIES["medical"]
    assert f["name"] == "NEET Adaptive Engine" and f["icon"] == "🩺" and not f["coming_soon"]
    assert f["sections"] == {"Biology": ["NEET Botany", "NEET Zoology"]}
    assert all(f["sections"].values())  # no empty section (Physics/Chemistry come later)
    assert f["level_labels"]["CAT-Level"] == "Exam-Level"
    monkeypatch.setenv("EXAM_FAMILY", "medical")
    assert families.get_family()["key"] == "medical"
    for t in NEET_TOPICS:
        assert families.topic_family(t) == "medical" and t in prompts.TOPIC_RULES
        assert t not in engine.NO_AI_GENERATION_TOPICS
    assert {build_bank.topic_prefix(t) for t in NEET_TOPICS} == {"NB", "NZ"}
    assert families.FAMILIES["engineering"]["coming_soon"]


def test_neet_bank_items_valid_and_pending_review():
    assert len(NEET) == 498
    assert collections.Counter(q["topic"] for q in NEET) == {"NEET Botany": 271, "NEET Zoology": 227}
    ids = [q["id"] for q in NEET]
    assert len(ids) == len(set(ids)) and all(i.startswith(("AI-NB-", "AI-NZ-")) for i in ids)
    for q in NEET:
        assert q["exam"] == "NEET" and q["difficulty"] in engine.DIFFICULTIES
        assert sorted(q["options"]) == list("ABCD") and len(set(q["options"].values())) == 4
        assert q["correct_answer"] in "ABCD" and engine.REQUIRED_KEYS <= q.keys()
        assert q["review_status"] == "unreviewed" and q["verified"] and q["source_ref"].startswith("gemini_verify/")
        assert q["text_hash"] == bank.text_hash(q)
    for t in NEET_TOPICS:  # every level has questions in both sections
        assert {q["difficulty"] for q in NEET if q["topic"] == t} == set(engine.DIFFICULTIES)


def test_neet_pool_serves_only_biology_with_review_label():
    topics = families.family_topics("medical")
    imported = [q for p in bank.import_paths("medical") for q in bank.load_json_bank(p)["questions"] if q["topic"] in topics]
    pool = [q for q in bank.serving_pool([], AI, imported) if q["topic"] in topics]
    assert len(pool) == 498 and {q["source"] for q in pool} == {"AI bank (faculty review pending)"}
    for t in topics:
        for d in engine.DIFFICULTIES:
            assert bank.pick_unseen(pool, t, d, set(), random.Random(0))["topic"] == t
    assert engine.daily_pick(pool, dt.date(2026, 11, 15))["topic"] in topics
