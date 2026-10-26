#!/usr/bin/env python3
"""Apply faculty decisions from review/ai_bank_review.csv back into data/ai_bank.json.

approve column: Y/YES/APPROVE/1 -> approved; N/NO/REJECT/0 -> rejected; blank -> unchanged.
Rejected questions stay in the JSON (so they are never regenerated as 'new') but are never served.
Only the review fields are applied; edits to question text in the CSV are ignored on purpose.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bank  # noqa: E402
from scripts.export_review import DEFAULT_CSV  # noqa: E402

YES, NO = {"y", "yes", "approve", "approved", "1", "true"}, {"n", "no", "reject", "rejected", "0", "false"}


def apply(csv_path=DEFAULT_CSV, bank_path=bank.AI_BANK_PATH, reviewer: str = "") -> dict:
    data = bank.load_json_bank(bank_path)
    by_id = {q["id"]: q for q in data["questions"]}
    res = {"approved": 0, "rejected": 0, "unchanged": 0, "unknown_ids": []}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            q = by_id.get(row.get("id", ""))
            if q is None:
                res["unknown_ids"].append(row.get("id"))
                continue
            v = (row.get("approve") or "").strip().lower()
            status = "approved" if v in YES else "rejected" if v in NO else None
            if status is None:
                res["unchanged"] += 1
                continue
            q["review_status"] = status
            q["reviewed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            if reviewer:
                q["reviewed_by"] = reviewer
            if row.get("review_note"):
                q["review_note"] = row["review_note"][:500]
            res[status] += 1
    bank.save_json_bank(data, bank_path)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--reviewer", default="")
    a = ap.parse_args()
    print(apply(a.csv, reviewer=a.reviewer))
