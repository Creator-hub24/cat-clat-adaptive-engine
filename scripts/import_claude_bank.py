"""Import the verified Claude-curated questions into one bank file per exam family.

Source (data/claude_curation/):
  verified_questions.json  items that passed independent verification, with trap/format/verify_code fixes applied
  manifest.json            position -> source file and item index ("file-5 #67"), used for stable ids
  additions.json           items re-included after review (original text)
  decisions.json           option/explanation fixes, topic retags, dropped items and exclusions, applied on every run
  fixes_record.md          human-readable record of every curation decision

Output: data/claude_bank_<family>.json for mgmt_law (CAT, CLAT, IPMAT), sarkari and cuet, in the engine's question
format. Each app loads only its own family's file (bank.import_paths). Every item carries verified=True and its
verification steps, so the app shows the "✅ Verified" badge.

Ids are CL-<family code>-<topic code>-<source code>-<index>, e.g. CL-ML-CLLR-F5-007 for file-5 #7 in CLAT Legal
Reasoning. They come from the source position, so a re-run gives the same ids and the same files byte for byte,
and adding new items never renumbers existing ones (users' seen/repeat history stays valid).

Usage: python3 -m scripts.import_claude_bank            # writes the three bank files
       python3 -m scripts.import_claude_bank --check    # validates and prints counts, writes nothing
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bank  # noqa: E402
import engine  # noqa: E402
import families  # noqa: E402

CURATION_DIR = ROOT / "data" / "claude_curation"
FAMILY_CODES = {"mgmt_law": "ML", "sarkari": "SK", "cuet": "CU"}
EXAM_FAMILY = {"CAT": "mgmt_law", "CLAT": "mgmt_law", "IPMAT": "mgmt_law", "Sarkari": "sarkari", "CUET": "cuet"}
# Claude topic names are the app's own topic names; the code is used only in ids
TOPIC_CODES = {
    "CAT Quant": "CQA", "CAT VARC RC": "CRC", "CAT DILR": "CDI",
    "CLAT RC": "CLRC", "CLAT Logical Reasoning": "CLLG", "CLAT Legal Reasoning": "CLLR",
    "IPMAT Quant": "IQA", "IPMAT Verbal": "IVB",
    "Sarkari Quantitative Aptitude": "SQA", "Sarkari Reasoning": "SRE", "Sarkari English": "SEN",
    "CUET Quantitative Reasoning": "QR", "CUET General Mental Ability": "GMA",
    "CUET Logical & Analytical Reasoning": "LAR", "CUET English Reading Comprehension": "RC",
    "CUET English Verbal Ability": "VA", "CUET Maths Section A": "MA", "CUET Maths Section B1": "MB",
}
FIELDS = ("exam", "topic", "difficulty", "concept_tag", "question_text", "options", "correct_answer", "trap_type",
          "pedagogical_explanation")
SOURCE_RE = re.compile(r"^(?:batch-(\d+) file|file-(\d+)) #(\d+)$")
VERIFICATION = ["independent solve"]  # every item: key re-derived by a blind solve, plus format and duplicate checks


def bank_path(family: str) -> Path:
    return bank.claude_bank_path(family)


def source_code(source: str) -> tuple[str, int]:
    """'file-5 #7' -> ('F5', 7); 'batch-1 file #3' -> ('B1', 3)."""
    m = SOURCE_RE.match(source)
    if not m:
        raise ValueError(f"unrecognised source {source!r}")
    return (f"B{m.group(1)}" if m.group(1) else f"F{m.group(2)}"), int(m.group(3))


def make_id(family: str, topic: str, source: str) -> str:
    code, idx = source_code(source)
    return f"CL-{FAMILY_CODES[family]}-{TOPIC_CODES[topic]}-{code}-{idx:03d}"


def _rd(name: str, d: Path):
    return json.loads((d / name).read_text(encoding="utf-8"))


def load_source(d: Path = CURATION_DIR) -> list[tuple[str, dict]]:
    """(source, item) pairs: the verified items in manifest order, then the re-included additions."""
    qs = _rd("verified_questions.json", d)["questions"]
    man = _rd("manifest.json", d)["items"]
    if [m["n"] for m in man] != list(range(len(qs))):
        raise ValueError("manifest does not line up with verified_questions.json")
    pairs = [(m["source"], dict(q)) for m, q in zip(man, qs)]
    pairs += [(a["source"], dict(a["question"])) for a in _rd("additions.json", d)["items"]]
    return pairs


def apply_decisions(pairs: list[tuple[str, dict]], dec: dict) -> list[tuple[str, dict]]:
    by = {}
    for s, q in pairs:
        if s in by:
            raise ValueError(f"source listed twice: {s}")
        by[s] = q
    for f in dec.get("text_fixes", []):
        q = by[f["source"]]
        if f["field"].startswith("options."):
            k = f["field"].split(".", 1)[1]
            if q["options"][k] != f["old"]:
                raise ValueError(f"{f['source']} option {k}: expected {f['old']!r}")
            q["options"] = dict(q["options"], **{k: f["new"]})
        else:
            if f["old"] not in q[f["field"]]:
                raise ValueError(f"{f['source']} {f['field']}: text to replace not found")
            q[f["field"]] = q[f["field"]].replace(f["old"], f["new"])
    for r in dec.get("topic_retags", []):
        for s, q in pairs:
            code, idx = source_code(s)
            if s.startswith(r["source_prefix"] + " ") and r["index_from"] <= idx <= r["index_to"] and q["topic"] == r["from"]:
                q["topic"] = r["to"]
    drop = {x["source"] for x in dec.get("dropped", [])}
    return [(s, q) for s, q in pairs if s not in drop]


def validate(q: dict, family: str) -> None:
    missing = engine.REQUIRED_KEYS - set(q)
    if missing:
        raise ValueError(f"missing {sorted(missing)}")
    if sorted(q["options"]) != list("ABCD") or not all(str(v).strip() for v in q["options"].values()):
        raise ValueError("options must be non-empty A-D")
    if len({str(v).strip() for v in q["options"].values()}) != 4:
        raise ValueError("options must be distinct")
    if q["correct_answer"] not in "ABCD" or len(q["correct_answer"]) != 1:
        raise ValueError(f"bad key {q['correct_answer']!r}")
    if q["difficulty"] not in engine.DIFFICULTIES:
        raise ValueError(f"bad difficulty {q['difficulty']!r}")
    if q["topic"] not in families.family_topics(family):
        raise ValueError(f"topic {q['topic']!r} is not in the {family} app")
    if q.get("verify_code"):
        ans = engine.run_verify_code(q["verify_code"])
        if not engine.answer_matches_key(ans, q["options"], q["correct_answer"]):
            raise ValueError(f"verify_code gives {ans!r}, key is {q['correct_answer']}")


def convert(pairs: list[tuple[str, dict]], dec: dict, run_code: bool = True) -> dict[str, list[dict]]:
    excluded = {e["source"]: e for e in dec.get("exclusions", [])}
    out: dict[str, list[dict]] = {f: [] for f in FAMILY_CODES}
    for s, q in pairs:
        family = EXAM_FAMILY[q["exam"]]
        if families.topic_family(q["topic"]) != family:
            raise ValueError(f"{s}: topic {q['topic']!r} does not belong to the {family} app")
        try:
            validate(q if run_code else dict(q, verify_code=""), family)
        except Exception as e:
            raise ValueError(f"{s}: {e}") from e
        item = {"id": make_id(family, q["topic"], s), **{k: q[k] for k in FIELDS},
                "verify_code": q.get("verify_code") or "", "source_ref": f"claude:{s}",
                "import_source": bank.CLAUDE_SOURCE, "verified": True,
                "verification": VERIFICATION + (["computed"] if q.get("verify_code") else [])}
        item["text_hash"] = bank.text_hash(item)
        if s in excluded:
            item["excluded"] = {"category": excluded[s]["category"], "reason": excluded[s]["reason"]}
        out[family].append(item)
    for items in out.values():
        items.sort(key=lambda q: q["id"])
    ids = [q["id"] for items in out.values() for q in items]
    dup_ids = [i for i, c in Counter(ids).items() if c > 1]
    hashes = Counter(q["text_hash"] for items in out.values() for q in items)
    if dup_ids or any(c > 1 for c in hashes.values()):
        raise ValueError(f"duplicate ids {dup_ids} or duplicate questions")
    return out


def existing_hashes() -> dict[str, str]:
    """text_hash -> id for every other bank the apps serve (seed banks, AI bank, AptiSetu imports)."""
    paths = [bank.SEED_PATH, bank.AI_BANK_PATH, *bank.IMPORT_PATHS, *sorted(ROOT.glob("data/sample_bank_*.json"))]
    return {bank.text_hash(q): q.get("id") for p in paths for q in bank.load_json_bank(p)["questions"]}


def write_bank(family: str, items: list[dict]) -> Path:
    """Deterministic write (no timestamp): a re-run on unchanged sources leaves the files unchanged."""
    path = bank_path(family)
    meta = {"version": 1, "source": "data/claude_curation (Claude-generated, independently verified)",
            "author": "Vaibhav Gupta", "family": family, "count": len(items),
            "topics": dict(sorted(Counter(q["topic"] for q in items).items()))}
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "questions": items}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def build(d: Path = CURATION_DIR, run_code: bool = True) -> dict[str, list[dict]]:
    dec = _rd("decisions.json", d)
    return convert(apply_decisions(load_source(d), dec), dec, run_code)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="validate and print counts without writing")
    args = ap.parse_args(argv)
    out = build()
    clash = existing_hashes()
    hits = [(q["id"], clash[q["text_hash"]]) for items in out.values() for q in items if q["text_hash"] in clash]
    if hits:
        print("exact duplicates of questions already in the app banks:", hits)
        return 1
    for family, items in out.items():
        served = len(bank.servable_imports(items))
        print(f"{family}: {len(items)} items, {served} served")
        for (topic, level), n in sorted(Counter((q["topic"], q["difficulty"]) for q in items).items()):
            print(f"  {topic:40s} {level:10s} {n}")
        if not args.check:
            print("  ->", write_bank(family, items).relative_to(ROOT))
    print("total:", sum(len(v) for v in out.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
