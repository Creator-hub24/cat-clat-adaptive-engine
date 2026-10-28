"""Read-only audit of an imported question bank (default: data/aptisetu_bank.json).

Never modifies the bank or any 'verified' flag. Writes:
  data/audit/aptisetu_audit.json   per-question results (resumable)
  data/audit/aptisetu_audit.md     summary + disagreements

  python scripts/audit_bank.py                 # static + deterministic checks only
  GEMINI_API_KEY=... python scripts/audit_bank.py --llm   # + independent LLM solve (resumes)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine  # noqa: E402

LETTERS = ("A", "B", "C", "D")
NUM = r"-?\d+(?:,\d{3})*(?:\.\d+)?"


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _num(s) -> float | None:
    """Value of an option that is just a number (optionally with %, ₹, units)."""
    t = re.sub(r"(?i)(rs\.?|₹|%|inr|units?|km/h|kmph|km|hours?|hrs?|days?|minutes?|mins?|years?|cm|m|kg|litres?|l)\b|[₹%]", "",
               str(s or "")).strip()
    t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        pass
    m = re.fullmatch(r"(-?\d+)\s*/\s*(\d+)", t)
    return float(m.group(1)) / float(m.group(2)) if m and float(m.group(2)) else None


def stated_letter(expl: str) -> str | None:
    """An explicit answer letter in the explanation, e.g. 'Answer: (C)' / 'option B is correct'."""
    m = re.search(r"(?i)\b(?:answer|ans|correct (?:answer|option|choice))\s*(?:is|:|=|-)?\s*\(?(?:option\s*)?([A-D])\)?(?![\w'])", expl or "")
    m = m or re.search(r"(?i)\boption\s*\(?([A-D])\)?\s*is\s*(?:the\s*)?correct", expl or "")
    return m.group(1).upper() if m else None


def final_number(expl: str) -> float | None:
    """The last number the explanation concludes with (after '=', 'is', '⇒', 'answer')."""
    hits = re.findall(rf"(?:=|⇒|→|\bis\b|\banswer\b[^0-9\-]{{0,15}})\s*(?:rs\.?|₹)?\s*({NUM})", expl or "", re.I)
    if not hits:
        return None
    try:
        return float(hits[-1].replace(",", ""))
    except ValueError:
        return None


def static_issues(q: dict) -> list[str]:
    """Hard problems (error:) and heuristic warnings (warn:)."""
    out = []
    opts = q.get("options") or {}
    key = str(q.get("correct_answer") or "").strip().upper()
    if not isinstance(opts, dict) or sorted(opts) != list(LETTERS):
        out.append(f"error: options must be exactly A-D (got {sorted(opts) if isinstance(opts, dict) else type(opts).__name__})")
    if key not in LETTERS or key not in opts:
        out.append(f"error: correct_answer '{key}' is not a valid option letter")
    vals = [_norm(v) for v in opts.values()] if isinstance(opts, dict) else []
    if any(not v for v in vals):
        out.append("error: empty option text")
    if len(set(v for v in vals if v)) < len([v for v in vals if v]):
        out.append("error: duplicate option texts")
    nums = [_num(v) for v in opts.values()] if isinstance(opts, dict) else []
    if len([n for n in nums if n is not None]) != len({n for n in nums if n is not None}):
        out.append("error: duplicate numeric option values")
    stem = str(q.get("question_text") or "").strip()
    if len(stem) < 15:
        out.append("error: empty or very short question_text")
    try:
        import llm
        ms = llm.missing_stem(q.get("topic", ""), stem)
        if ms:
            out.append("warn: " + ms)
    except Exception:
        pass
    expl = str(q.get("pedagogical_explanation") or "")
    if len(expl.strip()) < 10:
        out.append("warn: explanation missing/very short")
    letter = stated_letter(expl)
    if letter and key in LETTERS and letter != key:
        out.append(f"error: explanation states answer {letter} but key is {key}")
    if key in opts:
        kv = _num(opts[key])
        fn = final_number(expl)
        if kv is not None and fn is not None and abs(fn - kv) > 1e-6 * max(1, abs(kv)):
            others = [k for k, n in zip(opts, nums) if n is not None and abs(fn - n) <= 1e-6 * max(1, abs(n))]
            if others and key not in others:
                out.append(f"error: explanation concludes {fn:g}, which is option {others[0]}, but key is {key} ({opts[key]})")
    out += dilr_code_issues(q)
    return out


def dilr_code_issues(q: dict, run: bool = True) -> list[str]:
    """CAT DILR verify_code checks (topics in engine.UNIQUE_ANSWER_TOPICS). Flags an item with no verify_code
    or with code that does not assign `answers` (the uniqueness contract); with run=True, code that meets the
    contract is executed in the sandbox and must give exactly one consistent answer equal to the key."""
    if q.get("topic") not in engine.UNIQUE_ANSWER_TOPICS:
        return []
    code = q.get("verify_code")
    if not code:
        return ["warn: DILR item has no verify_code (answer not computed)"]
    if not engine.uses_answers_contract(code):
        return ["warn: DILR verify_code does not list all consistent answers (`answers`), so uniqueness is unchecked"]
    if not run:
        return []
    try:
        res = engine.run_verify_code_full(code)
    except Exception as e:
        return [f"error: DILR verify_code failed to run ({str(e)[:120]})"]
    why = engine.check_unique_answers(res, q.get("options") or {}, str(q.get("correct_answer") or "").strip().upper())
    return [f"error: DILR uniqueness check failed ({why})"] if why else []


def numeric_check(q: dict) -> dict | None:
    """Deterministic check for Quant/DI: if the explanation's concluding number equals exactly one
    numeric option, that option is the 'derived' answer."""
    if q.get("topic") not in ("CAT Quant", "CAT DILR"):
        return None
    opts = q.get("options") or {}
    fn = final_number(q.get("pedagogical_explanation") or "")
    if fn is None:
        return None
    match = [k for k, v in opts.items() if (n := _num(v)) is not None and abs(n - fn) <= 1e-6 * max(1, abs(n))]
    return {"final_number": fn, "derived": match[0] if len(match) == 1 else None}


def llm_solve(q: dict, client, models) -> dict:
    import llm
    ans, amb = llm.independent_solve(client, models, q)
    return {"answer": ans, "ambiguous": amb}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bank", default=str(ROOT / "data/aptisetu_bank.json"))
    ap.add_argument("--out", default=str(ROOT / "data/audit/aptisetu_audit.json"))
    ap.add_argument("--llm", action="store_true", help="also run the independent LLM solve (needs GEMINI_API_KEY)")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between LLM calls")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)

    qs = json.loads(Path(a.bank).read_text())
    qs = qs["questions"] if isinstance(qs, dict) else qs
    out_path = Path(a.out)
    prev = json.loads(out_path.read_text()) if out_path.exists() else {}
    results = prev.get("results", {})

    client = models = None
    llm_status = "not run"
    if a.llm:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            llm_status = "skipped: GEMINI_API_KEY not set"
            print(llm_status)
        else:
            import llm
            import prompts
            client, models = llm.make_client(key), prompts.model_candidates(os.environ.get("GEMINI_MODEL"))
            llm_status = "run"

    done_llm = 0
    for i, q in enumerate(qs):
        if a.limit and i >= a.limit:
            break
        r = results.get(q["id"], {})
        r.update({"topic": q.get("topic"), "key": q.get("correct_answer"),
                  "static": static_issues(q), "numeric": numeric_check(q)})
        if client and not (r.get("llm") or {}).get("answer"):
            for attempt in range(4):  # back off on per-minute quota (429) instead of burning the item
                try:
                    r["llm"] = llm_solve(q, client, models)
                    break
                except Exception as e:
                    r["llm"] = {"answer": None, "error": str(e)[:200]}
                    if "429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e):
                        break
                    time.sleep(30 * (attempt + 1))
            done_llm += 1
            time.sleep(a.sleep)
        results[q["id"]] = r
        if client and done_llm and done_llm % 10 == 0:
            _write(out_path, results, qs, llm_status)
            print(f"{i + 1}/{len(qs)}", flush=True)
    _write(out_path, results, qs, llm_status)
    print(f"wrote {out_path} and {out_path.with_suffix('.md')}")


def disagreements(results: dict, qs: list[dict]) -> list[dict]:
    byid = {q["id"]: q for q in qs}
    rows = []
    for qid, r in results.items():
        q = byid.get(qid, {})
        reasons, solver = [], None
        errs = [s for s in r.get("static", []) if s.startswith("error")]
        reasons += errs
        n = r.get("numeric") or {}
        if n.get("derived") and n["derived"] != r.get("key"):
            reasons.append(f"explanation's final number {n['final_number']:g} matches option {n['derived']}")
            solver = n["derived"]
        l = r.get("llm") or {}
        if l.get("answer") and l["answer"] != r.get("key"):
            reasons.append(f"independent LLM solve chose {l['answer']}" + (" (flagged ambiguous)" if l.get("ambiguous") else ""))
            solver = solver or l["answer"]
        elif l.get("answer") and l.get("ambiguous"):
            reasons.append("independent LLM solve agrees but flags the item as ambiguous")
        if reasons:
            rows.append({"id": qid, "topic": r.get("topic"),
                         "stem": re.sub(r"\s+", " ", str(q.get("question_text", "")))[-160:],
                         "key": r.get("key"), "solver": solver, "reasons": reasons,
                         "severity": 2 if (errs or (solver and solver != r.get("key"))) else 1})
    return sorted(rows, key=lambda x: (-x["severity"], x["topic"] or "", x["id"]))


def _write(out_path: Path, results: dict, qs: list[dict], llm_status: str):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = disagreements(results, qs)
    llm_n = sum(1 for r in results.values() if (r.get("llm") or {}).get("answer"))
    llm_err = sum(1 for r in results.values() if (r.get("llm") or {}).get("error"))
    llm_dis = sum(1 for r in results.values() if (l := r.get("llm") or {}).get("answer") and l["answer"] != r.get("key"))
    summary = {"checked": len(results),
               "static_errors": sum(1 for r in results.values() if any(s.startswith("error") for s in r["static"])),
               "static_warnings": sum(1 for r in results.values() if any(s.startswith("warn") for s in r["static"])),
               "numeric_mismatch": sum(1 for r in results.values() if (n := r.get("numeric") or {}).get("derived") and n["derived"] != r.get("key")),
               "llm_solved": llm_n, "llm_errors": llm_err, "llm_disagreements": llm_dis,
               "llm_ambiguous": sum(1 for r in results.values() if (r.get("llm") or {}).get("ambiguous")),
               "flagged": len(rows)}
    if llm_n:
        llm_status = "run" if llm_n == len(results) else (
            f"partial: {llm_n}/{len(results)} solved; resume with --llm (already-solved items are skipped)")
    out_path.write_text(json.dumps({"summary": summary, "llm_status": llm_status, "results": results},
                                   indent=1, ensure_ascii=False))
    md = ["# AptiSetu bank audit (read-only)", "",
          "Nothing in the bank was changed. Items listed here need human review.", "",
          f"- LLM pass: {llm_status}"] + [f"- {k.replace('_', ' ')}: {v}" for k, v in summary.items()]
    md += ["", "## Disagreements / issues", "", "| id | topic | stem (last 160 chars) | key | solver | reason |", "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['id']} | {r['topic']} | {r['stem'].replace('|', '/')} | {r['key']} | {r['solver'] or '-'} | "
                  f"{'; '.join(r['reasons']).replace('|', '/')} |")
    warn = [(qid, s) for qid, r in results.items() for s in r["static"] if s.startswith("warn")]
    if warn:
        md += ["", "## Static warnings", ""] + [f"- {qid}: {s[6:]}" for qid, s in warn]
    out_path.with_suffix(".md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
