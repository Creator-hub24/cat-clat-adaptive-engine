#!/usr/bin/env python3
"""Export data/ai_bank.json to review/ai_bank_review.csv for faculty review (opens in Excel/Sheets).

Fill the `approve` column with Y (approve) or N (reject); leave blank to keep 'unreviewed'.
Optional `review_note` is kept. Then run scripts/apply_review.py.
`check_flags` lists automatic findings for the reviewer (e.g. a CAT DILR item with no verify_code, or code
that does not list all consistent answers, so its uniqueness is unchecked); it is informational only.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bank  # noqa: E402
from scripts.audit_bank import dilr_code_issues  # noqa: E402

FIELDS = ["id", "section", "topic", "difficulty", "question", "option_A", "option_B", "option_C", "option_D",
          "answer", "explanation", "trap", "concept", "verified_computed", "verified_independent", "check_flags", "model",
          "created_at", "review_status", "approve", "review_note"]
DEFAULT_CSV = ROOT / "review" / "ai_bank_review.csv"


def export(bank_path=bank.AI_BANK_PATH, csv_path=DEFAULT_CSV) -> int:
    qs = bank.load_json_bank(bank_path)["questions"]
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        for q in qs:
            st = q.get("review_status", "unreviewed")
            w.writerow({"id": q["id"], "section": q["topic"].split()[0], "topic": q["topic"],
                        "difficulty": q["difficulty"], "question": q["question_text"],
                        **{f"option_{k}": q["options"].get(k, "") for k in "ABCD"},
                        "answer": q["correct_answer"], "explanation": q.get("pedagogical_explanation", ""),
                        "trap": q.get("trap_type", ""), "concept": q.get("concept_tag", ""),
                        "verified_computed": q.get("verified_computed", False),
                        "verified_independent": q.get("verified_independent", False),
                        "check_flags": "; ".join(dilr_code_issues(q)),
                        "model": q.get("model", ""), "created_at": q.get("created_at", ""), "review_status": st,
                        "approve": {"approved": "Y", "rejected": "N"}.get(st, ""),
                        "review_note": q.get("review_note", "")})
    return len(qs)


if __name__ == "__main__":
    print(f"Wrote {export()} rows to {DEFAULT_CSV.relative_to(ROOT)}")
