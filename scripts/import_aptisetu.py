"""Import CAT MCQ questions from the AptiSetu bank (Creator-hub24/aptisetu, data/cat.json).

Writes data/aptisetu_bank.json in the engine's question format. TITA questions are skipped, and so are
VARC MCQs that are not Reading Comprehension (para-summary / para-completion have no engine topic).

Usage: python -m scripts.import_aptisetu /path/to/aptisetu/data/cat.json
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bank  # noqa: E402

LETTERS = "ABCD"
LEVELS = {"Easy": "Easy", "Medium": "Moderate", "Hard": "CAT-Level"}
SECTIONS = {"qa": ("CAT Quant", "QA"), "dilr": ("CAT DILR", "DI"), "varc": ("CAT VARC RC", "VR")}


def _table_md(tbl: str) -> str:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S | re.I):
        cells = [inline(c).replace("|", "/") for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S | re.I)]
        rows.append(cells)
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def inline(s: str) -> str:
    """Inline HTML -> markdown-ish plain text."""
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"</?(b|strong)>", "**", s, flags=re.I)
    s = re.sub(r"</?(i|em)>", "*", s, flags=re.I)
    s = re.sub(r"<sup>(.*?)</sup>", r"^\1", s, flags=re.I | re.S)
    s = re.sub(r"<sub>(.*?)</sub>", r"_\1", s, flags=re.I | re.S)
    s = re.sub(r"</?[A-Za-z][A-Za-z0-9]*(\s[^<>]*)?/?>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def html_to_blocks(h: str) -> list[str]:
    """Block-level HTML -> list of markdown blocks (paragraphs, bullet lines, tables)."""
    blocks, pos = [], 0
    pat = re.compile(r"<table[^>]*>.*?</table>|<(ul|ol)[^>]*>.*?</\1>|<p[^>]*>.*?</p>|<blockquote[^>]*>.*?</blockquote>",
                     re.S | re.I)
    for m in pat.finditer(h):
        pre = inline(h[pos:m.start()])
        if pre:
            blocks.append(pre)
        tag = m.group(0)
        if tag.lower().startswith("<table"):
            blocks.append(_table_md(tag))
        elif tag.lower().startswith(("<ul", "<ol")):
            ordered = tag.lower().startswith("<ol")
            items = [inline(li) for li in re.findall(r"<li[^>]*>(.*?)</li>", tag, re.S | re.I)]
            blocks.append("\n".join(f"{i + 1}. {t}" if ordered else f"- {t}" for i, t in enumerate(items)))
        elif tag.lower().startswith("<blockquote"):
            blocks.append("> " + inline(tag))
        else:
            blocks.append(inline(tag))
        pos = m.end()
    tail = inline(h[pos:])
    if tail:
        blocks.append(tail)
    return [b for b in blocks if b.strip()]


def to_text(h: str) -> str:
    return "\n\n".join(html_to_blocks(h)) if "<" in str(h) else str(h).strip()


def fix_options_refs(sol: str) -> str:
    return re.sub(r"\b[Oo]ption\s*([1-4])\b", lambda m: f"Option {LETTERS[int(m.group(1)) - 1]}", sol)


def convert(data: dict) -> tuple[list[dict], Counter]:
    sets, out, skipped = data.get("sets", {}), [], Counter()
    for sec, (topic, pre) in SECTIONS.items():
        for q in data["sections"][sec]["questions"]:
            if q.get("type") != "mcq":
                skipped[f"{sec}: TITA (not MCQ)"] += 1
                continue
            if sec == "varc" and q.get("topic") != "Reading Comprehension":
                skipped[f"varc: {q.get('topic')} (no engine topic)"] += 1
                continue
            opts = q.get("options") or []
            if len(opts) != 4 or not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < 4:
                skipped[f"{sec}: options not exactly 4 / bad answer"] += 1
                continue
            level = LEVELS.get(q.get("level") or q.get("difficulty"))
            if not level:
                skipped[f"{sec}: unknown level"] += 1
                continue
            stem = to_text(q["question"])
            st = sets.get(q.get("set") or "")
            if sec == "varc":
                if not st:
                    skipped["varc: RC question without passage"] += 1
                    continue
                # passage paragraphs joined by single newlines so engine.passage_words counts the whole passage
                passage = "\n".join(b for b in html_to_blocks(st["html"]) if not b.startswith("**"))
                text = f"Passage: {passage}\n\n{stem}"
            elif sec == "dilr" and st:
                text = "\n\n".join(html_to_blocks(st["html"])) + "\n\n**Question:** " + stem
            else:
                text = stem
            out.append({
                "id": f"AS-{pre}-{q['id']}", "exam": "CAT", "topic": topic, "difficulty": level,
                "concept_tag": q.get("topic", ""),
                "question_text": text,
                "options": {LETTERS[i]: inline(str(o)) for i, o in enumerate(opts)},
                "correct_answer": LETTERS[q["answer"]],
                "trap_type": "-",
                "pedagogical_explanation": fix_options_refs(to_text(q.get("solution", ""))),
                "verify_code": "",
                "source_ref": f"aptisetu:{q['id']}",
            })
    return out, skipped


def dedupe(items: list[dict], existing: list[dict]) -> tuple[list[dict], list[str]]:
    keep, dropped, hashes = [], [], set()
    for q in items:
        h = bank.text_hash(q)
        why = "exact duplicate inside import" if h in hashes else bank.is_duplicate(q, existing)
        if why:
            dropped.append(f"{q['id']}: {why}")
            continue
        hashes.add(h)
        keep.append(q)
    return keep, dropped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, default=bank.APTISETU_PATH)
    a = ap.parse_args(argv)
    import json
    data = json.loads(a.src.read_text(encoding="utf-8"))
    items, skipped = convert(data)
    existing = bank.load_json_bank(bank.SEED_PATH)["questions"] + bank.load_json_bank(bank.AI_BANK_PATH)["questions"]
    items, dups = dedupe(items, existing)
    for q in items:
        q["text_hash"] = bank.text_hash(q)
    bank.save_json_bank({"meta": {"version": 1, "source": "Creator-hub24/aptisetu data/cat.json (CAT MCQ only)",
                                  "author": "Vaibhav Gupta"}, "questions": items}, a.out)
    print(f"imported {len(items)}:", dict(Counter((q['topic'], q['difficulty']) for q in items)))
    print("skipped:", dict(skipped), "| duplicates:", len(dups))
    for d in dups:
        print("  dup", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
