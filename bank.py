"""Pre-generated question bank: storage format, dedupe and serving pool (no Streamlit import)."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).parent
SEED_PATH = ROOT / "data" / "sample_bank.json"
AI_BANK_PATH = ROOT / "data" / "ai_bank.json"
REVIEW_STATUSES = ("unreviewed", "approved", "rejected")
NEAR_DUP_JACCARD = 0.6


# ---------------------------------------------------------------- io
def load_json_bank(path: Path) -> dict:
    if not Path(path).exists():
        return {"meta": {"version": 1}, "questions": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json_bank(data: dict, path: Path) -> None:
    """Atomic write so an interrupted build never corrupts the bank."""
    path = Path(path)
    data.setdefault("meta", {})["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------- dedupe
def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def text_hash(q: dict) -> str:
    opts = " ".join(normalize(v) for _, v in sorted(q.get("options", {}).items()))
    return hashlib.sha256((normalize(q["question_text"]) + "|" + opts).encode()).hexdigest()


def shingles(text: str, n: int = 5) -> set:
    w = normalize(text).split()
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def is_duplicate(q: dict, existing: list[dict], threshold: float = NEAR_DUP_JACCARD) -> str | None:
    """Return a reason string if q duplicates (exactly or nearly) anything in existing."""
    h = text_hash(q)
    sh = shingles(q["question_text"])
    for e in existing:
        if e.get("text_hash", text_hash(e)) == h:
            return f"exact duplicate of {e.get('id')}"
        if e.get("topic") == q.get("topic") and jaccard(sh, shingles(e["question_text"])) >= threshold:
            return f"near-duplicate of {e.get('id')}"
    return None


# ---------------------------------------------------------------- serving
def servable(questions: list[dict]) -> list[dict]:
    return [q for q in questions if q.get("review_status", "approved") != "rejected" and q.get("verified", True)]


def serving_pool(seed: list[dict], ai: list[dict]) -> list[dict]:
    out = []
    for q in seed:
        q = dict(q, source="Seed bank", verified=True,
                 verification=["hand-checked"] + (["computed"] if q.get("verify_code") else []))
        out.append(q)
    for q in servable(ai):
        out.append(dict(q, source="AI bank" + (" (faculty-approved)" if q.get("review_status") == "approved"
                                              else " (faculty review pending)")))
    return out


def pick_unseen(pool: list[dict], topic: str, difficulty: str, seen: set, rng) -> dict | None:
    """Unseen question for this topic+level; None if the user has exhausted that cell."""
    fresh = [q for q in pool if q["topic"] == topic and q["difficulty"] == difficulty and q["id"] not in seen]
    return dict(rng.choice(fresh)) if fresh else None
