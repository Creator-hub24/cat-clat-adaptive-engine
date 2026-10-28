"""Pure, testable engine logic: adaptive difficulty, timing targets, spaced repetition,
answer parsing, sandboxed answer-key verification, daily-challenge rotation."""
from __future__ import annotations

import ast
import datetime as dt
import json
import random
import re
import subprocess
import sys
from fractions import Fraction

DIFFICULTIES = ["Easy", "Moderate", "CAT-Level"]
REVIEW_INTERVALS = [3, 7, 15]  # questions answered before a mistake comes back
STEP_UP_AFTER = 2
STEP_DOWN_AFTER = 2
RC_TOPICS = {"CAT VARC RC", "CLAT RC", "CLAT Legal Reasoning", "CLAT Current Affairs & GK"}
# Topics whose facts must be grounded in a cited source (source_url + as_of). The LLM generator has no
# web access, so these are never auto/live generated: served only from the hand-verified seed bank.
NO_AI_GENERATION_TOPICS = {"CLAT Current Affairs & GK", "Sarkari General Awareness"}
GROUNDED_KEYS = ("source_url", "as_of")
COMPUTABLE_TOPICS = {"CAT Quant", "CAT DILR", "IPMAT Quant", "Sarkari Quantitative Aptitude"}
QUANT_TOPICS = {"CAT Quant", "IPMAT Quant", "Sarkari Quantitative Aptitude"}  # verify_code required
REQUIRED_KEYS = {"question_text", "options", "correct_answer", "pedagogical_explanation",
                 "trap_type", "concept_tag"}

# --------------------------------------------------------------- adaptive difficulty
def new_topic_state(level: str = "Easy") -> dict:
    return {"level": level, "run_correct": 0, "run_wrong": 0}


def update_level(state: dict | None, correct: bool, slow: bool) -> dict:
    """Step up after 2 consecutive fast-correct answers, down after 2 consecutive wrong.
    A correct-but-slow answer breaks a wrong run but does not count toward stepping up."""
    st = dict(state or new_topic_state())
    i = DIFFICULTIES.index(st.get("level", "Easy"))
    if correct and not slow:
        st["run_correct"] += 1
        st["run_wrong"] = 0
        if st["run_correct"] >= STEP_UP_AFTER:
            i = min(i + 1, len(DIFFICULTIES) - 1)
            st["run_correct"] = 0
    elif correct:  # right but too slow
        st["run_wrong"] = 0
    else:
        st["run_wrong"] += 1
        st["run_correct"] = 0
        if st["run_wrong"] >= STEP_DOWN_AFTER:
            i = max(i - 1, 0)
            st["run_wrong"] = 0
    st["level"] = DIFFICULTIES[i]
    return st


# --------------------------------------------------------------- timing
BASE_TARGET = {"Easy": (45, 60), "Moderate": (90, 120), "CAT-Level": (120, 180)}
READING_WPM = 250


def passage_words(text: str) -> int:
    """Words before the question stem (RC passages)."""
    body = text.split("\n\n")[0] if "\n\n" in text else text
    return len(body.split())


def target_seconds(topic: str, difficulty: str, question_text: str = "") -> tuple[int, int]:
    lo, hi = BASE_TARGET[difficulty]
    if topic in RC_TOPICS and question_text:
        read = round(passage_words(question_text) / READING_WPM * 60)
        lo, hi = lo + read, hi + read
    return lo, hi


def classify(correct: bool, seconds: float, target: tuple[int, int]) -> str:
    if not correct:
        return "Wrong"
    return "Right but too slow" if seconds > target[1] else "Right & on time"


# --------------------------------------------------------------- spaced repetition
def schedule_mistake(error_log: dict, q: dict, choice: str, n_answered: int) -> None:
    error_log[q["id"]] = {"question": q, "stage": 0, "your_answer": choice,
                          "due_at": n_answered + REVIEW_INTERVALS[0]}


def advance_review(error_log: dict, qid: str, n_answered: int) -> None:
    e = error_log.get(qid)
    if not e:
        return
    e["stage"] += 1
    if e["stage"] >= len(REVIEW_INTERVALS):
        del error_log[qid]
    else:
        e["due_at"] = n_answered + REVIEW_INTERVALS[e["stage"]]


# --------------------------------------------------------------- daily challenge
def daily_pick(bank: list[dict], day: dt.date, salt: int = 2026) -> dict:
    """Fixed shuffled order; one item per day -> no repeat for len(bank) days."""
    order = sorted(bank, key=lambda q: q["id"])
    random.Random(salt).shuffle(order)
    return order[day.toordinal() % len(order)]


# --------------------------------------------------------------- parsing
def parse_json_blob(text: str) -> dict:
    if not text:
        raise ValueError("Empty model response")
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found")
    blob = cleaned[start:end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", blob))


def parse_question_json(text: str) -> dict:
    data = parse_json_blob(text)
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"Missing keys: {missing}")
    opts = data["options"]
    if isinstance(opts, list):
        opts = {chr(65 + i): re.sub(r"^\s*[A-D][\).:\-]\s*", "", str(o)) for i, o in enumerate(opts[:4])}
    opts = {str(k).strip().upper()[:1]: str(v) for k, v in opts.items()}
    if set(opts) != {"A", "B", "C", "D"}:
        raise ValueError("Options must be exactly A-D")
    ans = str(data["correct_answer"]).strip().upper()[:1]
    if ans not in opts:
        raise ValueError("correct_answer not in options")
    data["options"], data["correct_answer"] = opts, ans
    return data


# --------------------------------------------------------------- sandboxed verification
ALLOWED_IMPORTS = {"math", "itertools", "fractions"}
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "globals", "locals",
                "vars", "getattr", "setattr", "delattr", "breakpoint", "help", "exit", "quit",
                "memoryview", "type", "object", "super", "dir"}


BANNED_ATTRS = {"format", "format_map"}  # "{0.__class__}".format(x) style attribute escapes


class UnsafeCode(ValueError):
    pass


def check_code(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise UnsafeCode(f"syntax error: {e}") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise UnsafeCode(f"import not allowed: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS or node.level:
                raise UnsafeCode(f"import not allowed: {node.module}")
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            raise UnsafeCode(f"name not allowed: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise UnsafeCode("dunder/private attribute access not allowed")
        elif isinstance(node, ast.Attribute) and node.attr in BANNED_ATTRS:
            raise UnsafeCode(f"attribute not allowed: {node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and (
                "__" in (node.value if isinstance(node.value, str) else node.value.decode("latin-1"))):
            raise UnsafeCode("string containing '__' not allowed")  # covers f-string literal parts too
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await)):
            raise UnsafeCode("construct not allowed")


_RUNNER = r'''
import sys, json, resource, builtins
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
import math, itertools, fractions
code = sys.stdin.read()
allowed = {"math": math, "itertools": itertools, "fractions": fractions}
real_import = builtins.__import__
def guarded_import(name, *a, **k):
    if name.split(".")[0] not in allowed:
        raise ImportError(name)
    return real_import(name, *a, **k)
safe = {n: getattr(builtins, n) for n in (
    "abs all any bool dict divmod enumerate filter float frozenset int isinstance len list map max "
    "min pow range reversed round set sorted str sum tuple zip print next iter chr ord ValueError ZeroDivisionError "
    "StopIteration Exception").split()}
safe["__import__"] = guarded_import
g = {"__builtins__": safe}
exec(compile(code, "<verify>", "exec"), g)
ans = g.get("answer")
if isinstance(ans, fractions.Fraction):
    ans = float(ans)
print(json.dumps({"answer": ans}))
'''


def run_verify_code(code: str, timeout: float = 3.0):
    """Run model/seed verify_code in a locked-down subprocess. The code must set `answer`."""
    check_code(code)
    try:
        p = subprocess.run([sys.executable, "-I", "-S", "-c", _RUNNER], input=code, text=True,
                           capture_output=True, timeout=timeout, env={})
    except subprocess.TimeoutExpired as e:
        raise TimeoutError("verify_code timed out") from e
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "verify failed").strip().splitlines()[-1][:200])
    return json.loads(p.stdout.strip().splitlines()[-1])["answer"]


_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?:\s*/\s*\d+)?")


def option_value(text: str):
    """First number in an option ('Rs 6,000' -> 6000, '3/4' -> 0.75); else stripped lowercase text."""
    m = _NUM.search(str(text))
    if not m:
        return str(text).strip().lower()
    tok = m.group().replace(",", "").replace(" ", "")
    return float(Fraction(tok)) if "/" in tok else float(tok)


def answer_matches_key(answer, options: dict, key: str, tol: float = 1e-6) -> bool:
    """True iff the computed answer matches the keyed option and no other option."""
    def same(a, b):
        if isinstance(b, float):
            try:
                return abs(float(a) - b) <= tol * max(1.0, abs(b))
            except (TypeError, ValueError):
                return False
        return str(a).strip().lower() == b
    if isinstance(answer, str) and answer.strip().upper() in options and len(answer.strip()) == 1:
        return answer.strip().upper() == key
    hits = [k for k, v in options.items() if same(answer, option_value(v))]
    return hits == [key]
