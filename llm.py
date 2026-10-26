"""Gemini generation with answer-key verification.

Pipeline per attempt (max 2 attempts, then the caller falls back to the seed bank):
1. Generate question JSON (+ verify_code for computable topics).
2. If verify_code present: run in sandbox and require it to match the key (Quant must pass this).
3. Independent second solve (separate call, key withheld); must agree with the key.
"""
from __future__ import annotations

import json
import random

import engine

TRANSIENT = ("404", "NOT_FOUND", "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL",
             "504", "DEADLINE_EXCEEDED", "timed out", "Timeout", "ReadTimeout", "deadline")
CALL_TIMEOUT_MS = 90_000


def make_client(api_key: str):
    """Client with a per-request timeout (some models can hang for minutes under load)."""
    from google import genai
    from google.genai import types
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=CALL_TIMEOUT_MS))

SOLVER_PROMPT = """You are an independent CAT/CLAT examiner checking a question. Solve it yourself carefully.
Return ONLY JSON: {"answer": "<A|B|C|D>", "confidence": <0-1>, "ambiguous": <true|false>}.
Set ambiguous=true if more than one option could be defended or none is correct."""


def call_model(client, models, contents, system, temperature):
    from google.genai import types
    last = None
    for m in models:
        try:
            resp = client.models.generate_content(
                model=m, contents=contents,
                config=types.GenerateContentConfig(system_instruction=system,
                                                   response_mime_type="application/json",
                                                   temperature=temperature))
            return resp.text, m
        except Exception as e:  # fall through to next model on transient/unknown-model errors
            if any(k in str(e) for k in TRANSIENT) or "timeout" in type(e).__name__.lower():
                last = e
                continue
            raise
    raise RuntimeError(f"No available Gemini model: {last}")


def independent_solve(client, models, q, writer_model=None) -> tuple[str | None, bool]:
    """Separate call with the key withheld; prefers a different model from the writer."""
    if writer_model in models and len(models) > 1:
        models = [m for m in models if m != writer_model] + [writer_model]
    opts = "\n".join(f"{k}) {v}" for k, v in q["options"].items())
    text, _ = call_model(client, models, f"{q['question_text']}\n\nOptions:\n{opts}", SOLVER_PROMPT, 0.0)
    data = engine.parse_json_blob(text)
    ans = str(data.get("answer", "")).strip().upper()[:1] or None
    return ans, bool(data.get("ambiguous"))


def missing_stem(topic: str, text: str) -> str | None:
    """Live finding: models sometimes return an RC passage with no question after it."""
    if topic == "CAT VARC RC":  # CLAT principle-fact items legitimately imply the question
        tail = text.strip()[-400:]
        if "?" not in tail and not tail.rstrip().endswith(":"):
            return "question_text has no question stem after the passage"
    return None


def generate_verified(client, models, topic, difficulty, prompt, system, max_tries=2, log=None):
    log = log if log is not None else []
    for attempt in range(1, max_tries + 1):
        try:
            text, model_used = call_model(client, models, prompt, system, 0.8)
            q = engine.parse_question_json(text)
        except (ValueError, json.JSONDecodeError) as e:
            log.append(f"try {attempt}: invalid JSON ({e})")
            continue
        stem_issue = missing_stem(topic, q["question_text"])
        if stem_issue:
            log.append(f"try {attempt}: {stem_issue}")
            continue
        checks = []
        code = q.get("verify_code")
        if topic in engine.COMPUTABLE_TOPICS and code:
            try:
                val = engine.run_verify_code(code)
            except Exception as e:
                log.append(f"try {attempt}: verify_code failed ({e})")
                continue
            if not engine.answer_matches_key(val, q["options"], q["correct_answer"]):
                log.append(f"try {attempt}: computed {val!r} does not match key {q['correct_answer']}")
                continue
            checks.append("computed")
        elif topic == "CAT Quant":
            log.append(f"try {attempt}: Quant question returned no verify_code")
            continue
        ans, ambiguous = independent_solve(client, models, q, model_used)
        if ambiguous or ans != q["correct_answer"]:
            log.append(f"try {attempt}: independent solver said {ans} (ambiguous={ambiguous}) vs key {q['correct_answer']}")
            continue
        checks.append("independent solve")
        q.update({"id": f"AI-{random.randint(10000, 99999)}", "topic": topic, "difficulty": difficulty,
                  "exam": topic.split()[0], "source": "AI", "model": model_used,
                  "verified": True, "verification": checks})
        return q
    raise RuntimeError("; ".join(log) or "generation failed")
