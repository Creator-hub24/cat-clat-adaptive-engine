"""Import MCQ questions from the AptiSetu bank (Creator-hub24/aptisetu): CAT (data/cat.json) or CUET (data/cuet.json).

CAT (default) writes data/aptisetu_bank.json in the engine's question format. TITA questions are skipped, and so are
VARC MCQs that are not Reading Comprehension (para-summary / para-completion have no engine topic).

Curation in data/aptisetu_curation/ is applied on every import, so a re-import keeps it:
  verified_ids.json  ids whose key was confirmed by an independent blind solve -> verified=true
  exclusions.json    ids kept in the bank with an "excluded" record and not served until fixed
  duplicates.json    same question imported twice: the "drop" id is left out
  fixes.json         stem wording fixes and a seeded option shuffle for series with skewed key positions

CUET (--family cuet) writes data/aptisetu_cuet_bank.json for the CUET app, with its curation in
data/aptisetu_curation/cuet/. Inline HTML (matrix spans, <br>, &nbsp;, entities) becomes plain text/unicode so the
app never needs unsafe_allow_html, and "|" becomes "∣" so determinants and |x| can never render as a table.
Items the source marks "fixed" (options in a meaningful order: A/B/C/D labels, codes) are never shuffled.

Usage: python -m scripts.import_aptisetu /path/to/aptisetu/data/cat.json
       python -m scripts.import_aptisetu /path/to/aptisetu/data/cuet.json --family cuet
"""
from __future__ import annotations

import argparse
import html
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bank  # noqa: E402

LETTERS = "ABCD"
LEVELS = {"Easy": "Easy", "Medium": "Moderate", "Hard": "CAT-Level"}
SECTIONS = {"qa": ("CAT Quant", "QA"), "dilr": ("CAT DILR", "DI"), "varc": ("CAT VARC RC", "VR")}
CURATION_DIR = Path(__file__).resolve().parent.parent / "data" / "aptisetu_curation"
CUET_CURATION_DIR = CURATION_DIR / "cuet"
# (source section, source part) -> (engine topic, id code); ids are AS-CU-<code>-<source id>
CUET_TOPICS = {
    ("gat", "Quantitative Reasoning"): ("CUET Quantitative Reasoning", "QR"),
    ("gat", "General Mental Ability"): ("CUET General Mental Ability", "GMA"),
    ("gat", "Logical & Analytical Reasoning"): ("CUET Logical & Analytical Reasoning", "LAR"),
    ("gat", "General Knowledge"): ("CUET General Knowledge", "GK"),
    ("english", "Reading Comprehension"): ("CUET English Reading Comprehension", "RC"),
    ("english", "Verbal Ability"): ("CUET English Verbal Ability", "VA"),
    ("maths", "Section A (common)"): ("CUET Maths Section A", "MA"),
    ("maths", "Section B1 (Mathematics)"): ("CUET Maths Section B1", "MB"),
}
PIPE = "\u2223"  # "∣" (divides): looks like |, but markdown never reads it as a table cell separator
MATRIX_NOTE = "*(Matrices are written row by row; rows are separated by \";\".)*"


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
    # some source sets nest a <table> inside a <p>; lift tables out so they render as markdown tables
    h = re.sub(r"(<table[^>]*>.*?</table>)", r"</p>\1<p>", h, flags=re.S | re.I)
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


# ---------------------------------------------------------------- CUET
_MX = re.compile(r"<span class=['\"]mx['\"]>((?:<span class=['\"]mx-r['\"]>(?:<span>.*?</span>)+</span>)+)</span>", re.S)
_MX_ROW = re.compile(r"<span class=['\"]mx-r['\"]>((?:<span>.*?</span>)+)</span>", re.S)
_ORDINAL = {"first": "A", "second": "B", "third": "C", "fourth": "D"}


def _matrix(m: re.Match, det: bool) -> str:
    rows = [", ".join(inline(c) for c in re.findall(r"<span>(.*?)</span>", r, re.S))
            for r in _MX_ROW.findall(m.group(1))]
    body = "; ".join(rows)
    return f"{PIPE}{body}{PIPE}" if det else f"[{body}]"


def cuet_inline(s: str, breaks: bool = False) -> str:
    """CUET inline HTML -> plain text. Matrices become [a, b; c, d] (determinants ∣a, b; c, d∣); <br> and &nbsp;
    become line breaks when breaks=True (stems), spaces otherwise; '|' becomes '∣'."""
    s = str(s)
    s = _MX.sub(lambda m: _matrix(m, bool(re.search(r"determinant\s*$", s[:m.start()], re.I))), s)
    if breaks:
        parts = re.split(r"<br\s*/?>|(?:\s*&nbsp;\s*)+", s, flags=re.I)
        s = "\n".join(p for p in (inline(x) for x in parts) if p)
    else:
        s = inline(s.replace("&nbsp;", " "))
    if "<" in s and re.search(r"</?[A-Za-z][^<>]*>", s):
        raise ValueError(f"HTML left after conversion: {s[:80]}")
    return s.replace("|", PIPE)


def ordinal_refs(sol: str) -> str:
    """'the second option' -> 'Option B' (source order), so the option shuffle can remap it."""
    return re.sub(r"\b[Tt]he (first|second|third|fourth) option\b", lambda m: f"Option {_ORDINAL[m.group(1)]}", sol)


def cuet_stem(h: str) -> str:
    text = cuet_inline(h, breaks=True)
    # fill-in blanks: escape the underscores so markdown shows them as a blank, never as emphasis
    return re.sub(r"_{2,}", lambda m: "\\_" * len(m.group(0)), text)


def convert_cuet(data: dict) -> tuple[list[dict], Counter]:
    sets, out, skipped = data.get("sets", {}), [], Counter()
    for sec, block in data["sections"].items():
        for q in block["questions"]:
            topic_code = CUET_TOPICS.get((sec, q.get("part")))
            if not topic_code:
                skipped[f"{sec}: unknown part {q.get('part')}"] += 1
                continue
            topic, code = topic_code
            opts = q.get("options") or []
            if q.get("type") != "mcq" or len(opts) != 4 or not isinstance(q.get("answer"), int) \
                    or not 0 <= q["answer"] < 4:
                skipped[f"{sec}: not a 4-option MCQ"] += 1
                continue
            level = LEVELS.get(q.get("difficulty"))
            if not level:
                skipped[f"{sec}: unknown level"] += 1
                continue
            stem = cuet_stem(q["question"])
            if _MX.search(q["question"]) or any(_MX.search(str(o)) for o in opts):
                stem += "\n\n" + MATRIX_NOTE
            st = sets.get(q.get("set") or "")
            blocks = [cuet_inline(b) if "<" in b else b for b in html_to_blocks(st["html"])] if st else []
            if topic == "CUET English Reading Comprehension":
                if not st:
                    skipped["english: RC question without passage"] += 1
                    continue
                # single newlines inside the passage so engine.passage_words counts all of it
                passage = "\n".join(b for b in blocks if not b.startswith("**"))
                text = f"Passage: {passage}\n\n{stem}"
            elif st:
                text = "\n\n".join(blocks) + "\n\n**Question:** " + stem
            else:
                text = stem
            item = {
                "id": f"AS-CU-{code}-{q['id']}", "exam": "CUET", "topic": topic, "difficulty": level,
                "concept_tag": q.get("topic", ""),
                "question_text": text,
                "options": {LETTERS[i]: cuet_inline(o) for i, o in enumerate(opts)},
                "correct_answer": LETTERS[q["answer"]],
                "trap_type": "-",
                "pedagogical_explanation": cuet_inline(fix_options_refs(ordinal_refs(str(q.get("solution", ""))))),
                "verify_code": "",
                "source_ref": f"aptisetu:cuet:{q['id']}",
            }
            if q.get("fixed"):
                item["options_fixed"] = True  # option order carries meaning: never shuffled
            out.append(item)
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


# ---------------------------------------------------------------- curation
def load_curation(d: Path = CURATION_DIR) -> dict:
    def rd(name, default):
        f = Path(d) / name
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default
    return {"verified": rd("verified_ids.json", {"ids": [], "verification": {}}),
            "exclusions": rd("exclusions.json", {"items": []}),
            "duplicates": rd("duplicates.json", {"pairs": []}),
            "fixes": rd("fixes.json", {})}


def apply_stem_fixes(items: list[dict], fixes: list[dict]) -> None:
    """Exact-once text replacements; 'field' defaults to question_text (pedagogical_explanation also allowed)."""
    by = {q["id"]: q for q in items}
    for f in fixes:
        q, field = by[f["id"]], f.get("field", "question_text")
        if q[field].count(f["find"]) != 1:
            raise ValueError(f"text fix for {f['id']}: text to replace not found exactly once")
        q[field] = q[field].replace(f["find"], f["replace"])


_REF = re.compile(r"\b(Options?)(\s+)((?:[A-D1-4])(?:(?:,\s*|\s+and\s+|\s+or\s+)[A-D1-4])*)\b")


def remap_refs(text: str, mapping: dict[str, str]) -> str:
    """Rewrite 'Option C' / 'Options 1 and 4' references through an old->new letter mapping (numbers 1-4 are
    read as A-D and written back as letters)."""
    def sub(m):
        body = re.sub(r"[A-D1-4]", lambda t: mapping[LETTERS[int(t.group(0)) - 1] if t.group(0).isdigit()
                                                     else t.group(0)], m.group(3))
        return m.group(1) + m.group(2) + body
    return _REF.sub(sub, text)


def series_of(qid: str, prefixes: list[str]) -> str | None:
    return next((p for p in prefixes if qid.startswith(p)), None)


def balanced_shuffle(items: list[dict], prefixes: list[str], seed: str) -> dict[str, dict[str, str]]:
    """Within each series, give every key position an equal share (seeded), move the options so the key text
    lands on its new letter, and remap option references in the explanation. Items marked options_fixed keep their
    order. Returns id -> old->new map."""
    maps, groups = {}, {}
    for q in items:
        p = series_of(q["id"], prefixes)
        if p and not q.get("options_fixed"):
            groups.setdefault(p, []).append(q)
    for p, qs in groups.items():
        rng = random.Random(f"{seed}:{p}")
        fixed = Counter(q["correct_answer"] for q in items if series_of(q["id"], [p]) and q.get("options_fixed"))
        if fixed:  # fixed-order items keep their keys: the movable ones fill each letter up to an equal share
            n = len(qs) + sum(fixed.values())
            share = {k: n // 4 + (i < n % 4) for i, k in enumerate(sorted(LETTERS, key=lambda k: -fixed[k]))}
            targets = [k for k in LETTERS for _ in range(max(0, share[k] - fixed[k]))]
            targets = (targets + [LETTERS[i % 4] for i in range(len(qs))])[:len(qs)]
        else:
            targets = [LETTERS[i % 4] for i in range(len(qs))]
        rng.shuffle(targets)
        for q, new_key in zip(qs, targets):
            old_key = q["correct_answer"]
            others = [k for k in LETTERS if k != old_key]
            rng.shuffle(others)
            slots = iter(others)
            order = {new: (old_key if new == new_key else next(slots)) for new in LETTERS}  # new letter -> old
            mapping = {old: new for new, old in order.items()}
            q["options"] = {new: q["options"][order[new]] for new in LETTERS}
            q["correct_answer"] = new_key
            q["pedagogical_explanation"] = remap_refs(q["pedagogical_explanation"], mapping)
            maps[q["id"]] = mapping
    return maps


def curate(items: list[dict], cur: dict) -> tuple[list[dict], dict]:
    """Apply fixes, shuffle, duplicate drops, verified flags and exclusions (in that order). With
    option_shuffle.after_duplicate_drop (CUET) duplicates are dropped first, so the shipped keys are balanced;
    the CAT bank keeps the original order so its published keys don't move."""
    ids = {q["id"] for q in items}
    fx = cur["fixes"]
    apply_stem_fixes(items, fx.get("stem_fixes", []))
    sh = fx.get("option_shuffle")
    drop = {p["drop"] for p in cur["duplicates"]["pairs"]}
    missing = (drop | {e["id"] for e in cur["exclusions"]["items"]} | set(cur["verified"]["ids"])) - ids
    if missing:
        raise ValueError(f"curation refers to ids not in the import: {sorted(missing)[:5]}")
    if sh and sh.get("after_duplicate_drop"):
        items = [q for q in items if q["id"] not in drop]
    maps = balanced_shuffle(items, sh["series"], sh["seed"]) if sh else {}
    items = [q for q in items if q["id"] not in drop]
    verified, how = set(cur["verified"]["ids"]), cur["verified"].get("verification", {})
    excluded = {e["id"]: e for e in cur["exclusions"]["items"]}
    for q in items:
        q["verified"] = q["id"] in verified
        if q["verified"]:
            q["verification"] = list(how.get(q["topic"], ["independent solve"]))
        if q["id"] in excluded:
            q["excluded"] = {"category": excluded[q["id"]]["category"], "reason": excluded[q["id"]]["reason"]}
    stats = {"dropped_duplicates": len(drop), "shuffled": len(maps), "verified": sum(q["verified"] for q in items),
             "excluded": len(excluded)}
    return items, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("--family", choices=["cat", "cuet"], default="cat")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--curation", type=Path)
    a = ap.parse_args(argv)
    cuet = a.family == "cuet"
    out = a.out or (bank.APTISETU_CUET_PATH if cuet else bank.APTISETU_PATH)
    data = json.loads(a.src.read_text(encoding="utf-8"))
    items, skipped = convert_cuet(data) if cuet else convert(data)
    items, stats = curate(items, load_curation(a.curation or (CUET_CURATION_DIR if cuet else CURATION_DIR)))
    existing = bank.load_json_bank(bank.SEED_PATH)["questions"] + bank.load_json_bank(bank.AI_BANK_PATH)["questions"]
    items, dups = dedupe(items, existing)
    for q in items:
        q["text_hash"] = bank.text_hash(q)
    source = ("Creator-hub24/aptisetu data/cuet.json (CUET UG MCQ)" if cuet
              else "Creator-hub24/aptisetu data/cat.json (CAT MCQ only)")
    bank.save_json_bank({"meta": {"version": 1, "source": source, "author": "Vaibhav Gupta"}, "questions": items}, out)
    print(f"imported {len(items)}:", dict(Counter((q['topic'], q['difficulty']) for q in items)))
    print("skipped:", dict(skipped), "| duplicates:", len(dups), "| curation:", stats)
    for d in dups:
        print("  dup", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
