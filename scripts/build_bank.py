#!/usr/bin/env python3
"""Build / top up data/ai_bank.json with verified Gemini questions.

Uses the app's own prompt layer (prompts.py) and verification pipeline (llm.generate_verified):
Quant/DILR verify_code computed in the sandbox, an independent second solve for every section,
reject on any disagreement. Accepted questions are deduped (normalised hash + 5-gram Jaccard) and
written to the bank after EACH acceptance, so the script can be stopped and resumed at any time.

  GEMINI_API_KEY=... python scripts/build_bank.py --per-cell 14 --rpm 8 --max-calls 450

Free tier: keep --rpm under your model's RPM limit; --max-calls caps a run below the daily quota.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bank  # noqa: E402
import engine  # noqa: E402
import llm  # noqa: E402
import prompts  # noqa: E402

STATS_KEY = "build_stats"


class QuotaStop(Exception):
    pass


class ThrottledClient:
    """Wraps genai.Client: enforces an RPM ceiling, backs off on 429, skips 503 models, counts calls."""

    def __init__(self, client, rpm: float, max_calls: int, max_backoff: float = 120, sleep=time.sleep):
        self._c, self.min_gap, self.max_calls = client, 60.0 / rpm, max_calls
        self.max_backoff, self.sleep = max_backoff, sleep
        self.calls, self._last = 0, 0.0
        self.exhausted: set[str] = set()   # models whose free-tier DAILY quota is used up
        self.models = self

    def generate_content(self, **kw):
        delay = 5.0
        model = kw.get("model")
        if model in self.exhausted:
            raise RuntimeError(f"429 RESOURCE_EXHAUSTED: daily quota already used for {model} (skipped)")
        while True:
            if self.calls >= self.max_calls:
                raise QuotaStop(f"--max-calls {self.max_calls} reached")
            wait = self.min_gap - (time.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            self.calls += 1
            try:
                return self._c.models.generate_content(**kw)
            except Exception as e:
                msg = str(e)
                if any(k in msg for k in ("API_KEY_INVALID", "PERMISSION_DENIED", "UNAUTHENTICATED", "401", "403")):
                    raise QuotaStop("API key rejected by Gemini (check GEMINI_API_KEY): " + msg[:120])
                if "503" in msg or "UNAVAILABLE" in msg:
                    raise  # overloaded model: fall through to the next model immediately
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    if "PerDay" in msg or "per day" in msg.lower():
                        self.exhausted.add(model)
                        print(f"  daily quota used up for {model}; skipping it for this run", flush=True)
                        if set(prompts.model_candidates()) <= self.exhausted:
                            raise QuotaStop("daily free-tier quota used up on every model")
                        raise  # llm.call_model falls through to the next model
                    if delay > self.max_backoff:
                        raise  # let llm.call_model fall through to the next model
                    print(f"  backoff {delay:.0f}s ({msg[:60]})", flush=True)
                    self.sleep(delay)
                    delay *= 2
                    continue
                raise


# Explicit prefixes where the initials rule would clash ("CLAT Legal Reasoning" -> CLR, already CLAT Logical Reasoning).
ID_PREFIX_OVERRIDES = {"CLAT Legal Reasoning": "CLG", "CLAT Current Affairs & GK": "CGK",
                       "Sarkari Quantitative Aptitude": "SQA", "Sarkari General Awareness": "SGA"}


def topic_prefix(topic: str) -> str:
    """AI id prefix: first letter of the exam + initials of the rest (CAT Quant -> CQ), unless overridden."""
    return ID_PREFIX_OVERRIDES.get(topic) or topic.split()[0][0] + "".join(w[0] for w in topic.split()[1:])


def cell_counts(questions):
    return Counter((q["topic"], q["difficulty"]) for q in questions)


def build(client, per_cell: int, out_path: Path, max_tries_per_q: int = 2, max_fail_per_cell: int = 6,
          topics=None, difficulties=None, log=print) -> dict:
    data = bank.load_json_bank(out_path)
    data.setdefault("meta", {}).update({"version": 1, "generator": "scripts/build_bank.py"})
    qs = data.setdefault("questions", [])
    stats = data.setdefault(STATS_KEY, {})
    seed = bank.load_json_bank(bank.SEED_PATH)["questions"]
    # Current-affairs topics need web-grounded facts the generator cannot verify: never auto-generated.
    topics = topics or [t for sec in prompts.SECTIONS.values() for t in sec
                        if t not in engine.NO_AI_GENERATION_TOPICS]
    difficulties = difficulties or prompts.DIFFICULTIES
    cells = [(t, d) for d in difficulties for t in topics]
    # round-robin across cells so a quota stop still leaves an even spread
    fails = Counter()
    while True:
        counts = cell_counts(qs)
        todo = [c for c in cells if counts[c] < per_cell and fails[c] < max_fail_per_cell]
        if not todo:
            break
        todo.sort(key=lambda c: counts[c])
        for topic, diff in todo:
            st = stats.setdefault(topic, Counter())
            st = stats[topic] = dict(Counter(st))
            existing = [q for q in qs + seed if q["topic"] == topic]
            avoid = [f"{q.get('concept_tag', '')}: {q['question_text'][:90]}" for q in existing
                     if q["difficulty"] == diff]
            prompt = prompts.build_prompt(topic, diff, prompts.retrieve_examples(seed, topic, diff), avoid)
            reasons = []
            try:
                q = llm.generate_verified(client, prompts.model_candidates(), topic, diff, prompt,
                                          prompts.SYSTEM_PROMPT, max_tries=max_tries_per_q, log=reasons)
            except QuotaStop:
                raise
            except Exception as e:
                st["rejected"] = st.get("rejected", 0) + max(1, len(reasons))
                st["attempts"] = st.get("attempts", 0) + max(1, len(reasons))
                fails[(topic, diff)] += 1
                log(f"✗ {topic} / {diff}: {str(e)[:160]}")
                bank.save_json_bank(data, out_path)
                continue
            st["attempts"] = st.get("attempts", 0) + len(reasons) + 1
            st["rejected"] = st.get("rejected", 0) + len(reasons)
            dup = bank.is_duplicate(q, qs + seed)
            if dup:
                st["duplicates"] = st.get("duplicates", 0) + 1
                fails[(topic, diff)] += 1
                log(f"≈ {topic} / {diff}: {dup}")
                bank.save_json_bank(data, out_path)
                continue
            h = bank.text_hash(q)
            q.update({"id": f"AI-{topic_prefix(topic)}-{h[:8]}",
                      "text_hash": h, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                      "review_status": "unreviewed", "verified_computed": "computed" in q["verification"],
                      "verified_independent": "independent solve" in q["verification"]})
            q.pop("source", None)
            qs.append(q)
            st["accepted"] = st.get("accepted", 0) + 1
            bank.save_json_bank(data, out_path)
            log(f"✓ {topic} / {diff} [{q['model']}] {q['id']}  ({cell_counts(qs)[(topic, diff)]}/{per_cell})")
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-cell", type=int, default=14, help="target questions per topic x difficulty")
    ap.add_argument("--rpm", type=float, default=8, help="request ceiling per minute (free tier ~10)")
    ap.add_argument("--max-calls", type=int, default=450, help="hard cap on API calls this run")
    ap.add_argument("--out", type=Path, default=bank.AI_BANK_PATH)
    ap.add_argument("--topic", action="append")
    ap.add_argument("--difficulty", action="append")
    a = ap.parse_args(argv)
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY is not set")
    client = ThrottledClient(llm.make_client(key), a.rpm, a.max_calls)
    try:
        data = build(client, a.per_cell, a.out, topics=a.topic, difficulties=a.difficulty)
        print("Done: all cells full (or skipped after repeated failures).")
    except QuotaStop as e:
        print(f"Stopped early: {e}. Progress is saved; re-run to resume.")
        data = bank.load_json_bank(a.out)
    except KeyboardInterrupt:
        print("Interrupted; progress is saved.")
        data = bank.load_json_bank(a.out)
    print(f"API calls this run: {client.calls}")
    print(json.dumps(data.get(STATS_KEY, {}), indent=2))
    c = Counter(q["topic"] for q in data["questions"])
    print("Bank size:", len(data["questions"]), dict(c))


if __name__ == "__main__":
    main()
