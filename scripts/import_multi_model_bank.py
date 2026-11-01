"""Import verified multi-model Sarkari questions into data/multi_model_bank_sarkari.json.

Source (data/multi_model_curation/):
  verified_questions.json  items that passed independent verification (Gemini batches 1–6 + model compares)
  manifest.json            position -> source model/batch and original index (stable ids)
  additions.json           items re-included after review (optional)
  decisions.json           text fixes, exclusions, faculty flags, option-shuffle seed, cross-dedupe drop log
  raw/                     original passing JSON files used to build verified_questions.json
  fixes_record.md          human-readable curation record

Output: data/multi_model_bank_sarkari.json in the engine's question format. The Sarkari app loads it via
bank.import_paths("sarkari"). Every item carries verified=True and verification steps so the app shows
the "✅ Verified" badge.

Ids are MM-SK-<topic code>-<batch code>-<index>, e.g. MM-SK-SQA-GB1-003. They come from the source
position, so a re-run gives the same ids. On every import, options are shuffled per item with a fixed
seed (remapping correct_answer, Trap (X) / Option X references, and verify_code OPTS/answer letters).

Usage: python3 -m scripts.import_multi_model_bank            # writes the bank file
       python3 -m scripts.import_multi_model_bank --check    # validates and prints counts, writes nothing
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bank  # noqa: E402
import engine  # noqa: E402
import families  # noqa: E402

CURATION_DIR = ROOT / "data" / "multi_model_curation"
FAMILY = "sarkari"
FAMILY_CODE = "SK"
TOPIC_CODES = {
    "Sarkari Quantitative Aptitude": "SQA",
    "Sarkari Reasoning": "SRE",
    "Sarkari English": "SEN",
}
FIELDS = ("exam", "topic", "difficulty", "concept_tag", "question_text", "options", "correct_answer",
          "trap_type", "pedagogical_explanation")
LETTERS = "ABCD"
SOURCE_RE = re.compile(r"^(batch-\d+[a-z]?|compare-[a-z0-9]+)\s+#(\d+)$")
VERIFICATION = ["independent solve"]
TRAP_RE = re.compile(r"\bTrap \(([A-D])\)")
OPTION_RE = re.compile(r"\b(Options?)(\s+)((?:[A-D])(?:(?:,\s*|\s+and\s+|\s+or\s+)[A-D])*)\b")
OPTS_KEY_RE = re.compile(r"(['\"])([A-D])\1\s*:")
ANSWER_LETTER_RE = re.compile(r"\banswer\s*=\s*(['\"])([A-D])\1")


def bank_path() -> Path:
    return bank.multi_model_bank_path(FAMILY)


def _rd(name: str, d: Path = CURATION_DIR):
    return json.loads((d / name).read_text(encoding="utf-8"))


def source_parts(source: str) -> tuple[str, int]:
    m = SOURCE_RE.match(source)
    if not m:
        raise ValueError(f"unrecognised source {source!r}")
    return m.group(1), int(m.group(2))


def make_id(topic: str, code: str, index: int) -> str:
    return f"MM-{FAMILY_CODE}-{TOPIC_CODES[topic]}-{code}-{index:03d}"


def load_source(d: Path = CURATION_DIR) -> list[tuple[dict, dict]]:
    """(manifest_item, question) pairs in manifest order, then additions."""
    qs = _rd("verified_questions.json", d)["questions"]
    man = _rd("manifest.json", d)["items"]
    if [m["n"] for m in man] != list(range(len(qs))):
        raise ValueError("manifest does not line up with verified_questions.json")
    pairs = [(dict(m), dict(q)) for m, q in zip(man, qs)]
    for a in _rd("additions.json", d)["items"]:
        pairs.append((dict(a["manifest"]), dict(a["question"])))
    return pairs


def apply_text_fixes(pairs: list[tuple[dict, dict]], dec: dict) -> None:
    by = {m["source"]: q for m, q in pairs}
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


def remap_explanation(text: str, mapping: dict[str, str]) -> str:
    """Remap Trap (X) and Option X references through an old->new letter mapping."""
    text = TRAP_RE.sub(lambda m: f"Trap ({mapping[m.group(1)]})", text)

    def opt_sub(m):
        body = re.sub(r"[A-D]", lambda t: mapping[t.group(0)], m.group(3))
        return m.group(1) + m.group(2) + body

    return OPTION_RE.sub(opt_sub, text)


def remap_verify_code(code: str, mapping: dict[str, str]) -> str:
    """Remap OPTS={'A': ...} keys and answer='X' letters through old->new mapping."""
    if not code:
        return code
    code = OPTS_KEY_RE.sub(lambda m: f"{m.group(1)}{mapping[m.group(2)]}{m.group(1)}:", code)
    code = ANSWER_LETTER_RE.sub(lambda m: f"answer = {m.group(1)}{mapping[m.group(2)]}{m.group(1)}", code)
    return code


def shuffle_item(q: dict, seed: str, source: str) -> dict[str, str]:
    """Deterministic per-item option shuffle. Returns old->new letter map."""
    rng = random.Random(f"{seed}:{source}")
    old_order = list(LETTERS)
    new_slots = list(LETTERS)
    rng.shuffle(new_slots)  # new_slots[i] receives text from old_order[i]? No — permute freely
    # Build permutation: assign each old letter a unique new letter
    targets = list(LETTERS)
    rng.shuffle(targets)
    mapping = {old: new for old, new in zip(LETTERS, targets)}  # old -> new
    inverse = {new: old for old, new in mapping.items()}  # new -> old
    q["options"] = {new: q["options"][inverse[new]] for new in LETTERS}
    q["correct_answer"] = mapping[q["correct_answer"]]
    q["pedagogical_explanation"] = remap_explanation(q.get("pedagogical_explanation") or "", mapping)
    q["verify_code"] = remap_verify_code(q.get("verify_code") or "", mapping)
    return mapping


def validate(q: dict) -> None:
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
    if q["topic"] not in families.family_topics(FAMILY):
        raise ValueError(f"topic {q['topic']!r} is not in the {FAMILY} app")
    if q.get("verify_code"):
        ans = engine.run_verify_code(q["verify_code"])
        if not engine.answer_matches_key(ans, q["options"], q["correct_answer"]):
            raise ValueError(f"verify_code gives {ans!r}, key is {q['correct_answer']}")


def convert(pairs: list[tuple[dict, dict]], dec: dict, run_code: bool = True) -> list[dict]:
    excluded = {e["source"]: e for e in dec.get("exclusions", [])}
    seed = (dec.get("option_shuffle") or {}).get("seed", "multi-model-sarkari")
    out: list[dict] = []
    for man, q in pairs:
        source = man["source"]
        if families.topic_family(q["topic"]) != FAMILY:
            raise ValueError(f"{source}: topic {q['topic']!r} does not belong to {FAMILY}")
        shuffle_item(q, seed, source)
        try:
            validate(q if run_code else dict(q, verify_code=""))
        except Exception as e:
            raise ValueError(f"{source}: {e}") from e
        item = {
            "id": make_id(q["topic"], man["code"], man["index"]),
            **{k: q[k] for k in FIELDS},
            "verify_code": q.get("verify_code") or "",
            "source_ref": f"multi:{source}",
            "import_source": bank.MULTI_MODEL_SOURCE,
            "source_model": man["model"],
            "source_batch": man["batch"],
            "verified": True,
            "verification": VERIFICATION + (["computed"] if q.get("verify_code") else []),
        }
        item["text_hash"] = bank.text_hash(item)
        if source in excluded:
            item["excluded"] = {"category": excluded[source]["category"], "reason": excluded[source]["reason"]}
        out.append(item)
    out.sort(key=lambda q: q["id"])
    ids = [q["id"] for q in out]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate ids: {[i for i,c in Counter(ids).items() if c>1]}")
    hashes = Counter(q["text_hash"] for q in out)
    if any(c > 1 for c in hashes.values()):
        raise ValueError("duplicate questions after import")
    return out


def existing_hashes() -> dict[str, str]:
    paths = [bank.SEED_PATH, bank.AI_BANK_PATH, *bank.IMPORT_PATHS, *sorted(ROOT.glob("data/sample_bank_*.json")),
             *sorted(ROOT.glob("data/claude_bank_*.json"))]
    return {bank.text_hash(q): q.get("id") for p in paths for q in bank.load_json_bank(p)["questions"]}


def write_bank(items: list[dict]) -> Path:
    path = bank_path()
    meta = {
        "version": 1,
        "source": "data/multi_model_curation (Gemini + model-compare, independently verified)",
        "author": "Vaibhav Gupta",
        "family": FAMILY,
        "count": len(items),
        "topics": dict(sorted(Counter(q["topic"] for q in items).items())),
        "models": dict(sorted(Counter(q["source_model"] for q in items).items())),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "questions": items}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def build(d: Path = CURATION_DIR, run_code: bool = True) -> list[dict]:
    dec = _rd("decisions.json", d)
    pairs = load_source(d)
    apply_text_fixes(pairs, dec)
    # drops already applied when verified_questions was built; exclusions still applied
    return convert(pairs, dec, run_code)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="validate and print counts without writing")
    args = ap.parse_args(argv)
    items = build()
    clash = existing_hashes()
    hits = [(q["id"], clash[q["text_hash"]]) for q in items if q["text_hash"] in clash]
    if hits:
        print("exact duplicates of questions already in the app banks:", hits)
        return 1
    served = len(bank.servable_imports(items))
    print(f"sarkari multi-model: {len(items)} items, {served} served")
    for (topic, level), n in sorted(Counter((q["topic"], q["difficulty"]) for q in items).items()):
        print(f"  {topic:40s} {level:10s} {n}")
    print("models:", dict(sorted(Counter(q["source_model"] for q in items).items())))
    keys = Counter(q["correct_answer"] for q in items)
    print("keys:", dict(sorted(keys.items())))
    if not args.check:
        print("  ->", write_bank(items).relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
