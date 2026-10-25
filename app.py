"""CAT/CLAT Adaptive Mock Test & Analytics Engine (Streamlit prototype)."""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

APP_DIR = Path(__file__).parent
BANK_PATH = APP_DIR / "data" / "sample_bank.json"
MODEL = "gemini-2.5-flash"
FREE_DAILY_AI_LIMIT = 10
REVIEW_INTERVALS = [1, 3, 7]  # spaced-repetition gaps (in questions answered)

SECTIONS = {
    "CAT": ["CAT Quant", "CAT VARC RC", "CAT DILR"],
    "CLAT": ["CLAT RC", "CLAT Logical Reasoning"],
}
DIFFICULTIES = ["Easy", "Moderate", "CAT-Level"]

DIFFICULTY_RUBRIC = {
    "Easy": "Single concept, one or two steps, direct application. A prepared aspirant should solve it in under 60 seconds.",
    "Moderate": "Two linked concepts or one concept with a twist; 90-120 seconds. Distractors reflect the most common procedural slip.",
    "CAT-Level": "Non-linear jump: needs an insight (a symmetry, a negative remainder, an invariant, a premise attack) rather than more computation. Brute force should be possible but slow; the elegant path takes 2-3 minutes. Distractors must be the answers a strong but hasty solver would actually get.",
}

TOPIC_RULES = {
    "CAT Quant": "Use clean integers. Every distractor must be the result of a specific, nameable mistake (e.g. additive fallacy, wrong base, ordered vs unordered). Mention the fastest shortcut.",
    "CAT VARC RC": "Write an ORIGINAL 120-220 word passage (no copyrighted text) followed by one question. Distractors must follow the taxonomy: Extreme scope, Out-of-scope, Half-true, Reversal. Label the trap type of each wrong option in the explanation.",
    "CAT DILR": "Write a small self-contained set (arrangement, tournament, scheduling or table). It MUST have exactly one solution; verify uniqueness in the explanation by showing why other cases fail. Prefer sets that reward a global check (conservation, parity) before grid-building.",
    "CLAT RC": "Write an ORIGINAL legal-principle passage (100-200 words) and a fact situation. The answer must follow ONLY from the stated principle, not outside legal knowledge. Include an exception in the principle at Moderate+.",
    "CLAT Logical Reasoning": "Argument-based (assumption, strengthen/weaken, inference, conditional logic). Use the negation test or contrapositive in the explanation.",
}

SYSTEM_PROMPT = """You are a master CAT/CLAT faculty member with 10+ years of classroom coaching.
You write ORIGINAL exam-grade questions (never copy past papers) and you teach through the explanation.
Pedagogical constraints you must obey:
1. Exactly 4 options keyed A, B, C, D, exactly one correct.
2. Every wrong option is a deliberate, realistic trap; the most tempting one is the 'main distractor'.
3. The explanation must (a) solve step by step, (b) name the shortcut or reading signal, (c) explain why the main distractor is wrong and what thinking error produces it.
4. Match the difficulty rubric exactly; difficulty comes from insight, not ugly numbers.
5. Output ONLY one JSON object, no markdown fences, with keys:
   question_text (string), options (object with keys A,B,C,D), correct_answer (one of A,B,C,D),
   pedagogical_explanation (string), trap_type (string, the main distractor's trap), concept_tag (string)."""

REQUIRED_KEYS = {"question_text", "options", "correct_answer", "pedagogical_explanation", "trap_type", "concept_tag"}


# ---------------------------------------------------------------- data / retrieval
@st.cache_data
def load_bank() -> list[dict]:
    with open(BANK_PATH, encoding="utf-8") as f:
        return json.load(f)["questions"]


def retrieve_examples(bank: list[dict], topic: str, difficulty: str, k: int = 2) -> list[dict]:
    """Simple lexical retrieval: same topic first (same difficulty ranked higher), then same exam."""
    exam = topic.split()[0]
    def score(q):
        return (q["topic"] == topic) * 2 + (q["difficulty"] == difficulty) + (q["exam"] == exam) * 0.5
    ranked = sorted(bank, key=score, reverse=True)
    return [q for q in ranked if score(q) > 0][:k]


# ---------------------------------------------------------------- LLM
def get_api_key() -> str | None:
    try:
        key = st.secrets.get("GEMINI_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")


def build_prompt(topic: str, difficulty: str, examples: list[dict]) -> str:
    shots = "\n\n".join(
        json.dumps({k: ex[k] for k in REQUIRED_KEYS}, ensure_ascii=False) for ex in examples
    )
    return f"""Topic: {topic}
Difficulty: {difficulty}
Difficulty rubric: {DIFFICULTY_RUBRIC[difficulty]}
Topic rules: {TOPIC_RULES[topic]}

Reference examples of house style (do NOT reuse their content, numbers or passages):
{shots}

Now write ONE new question as a single JSON object."""


def parse_question_json(text: str) -> dict:
    """Robustly extract and validate a question JSON object from model output."""
    if not text:
        raise ValueError("Empty model response")
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found")
    blob = cleaned[start:end + 1]
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        blob = re.sub(r",\s*([}\]])", r"\1", blob)  # trailing commas
        data = json.loads(blob)
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"Missing keys: {missing}")
    opts = data["options"]
    if isinstance(opts, list):  # ["A) ...", ...] -> dict
        opts = {chr(65 + i): re.sub(r"^\s*[A-D][\).:\-]\s*", "", str(o)) for i, o in enumerate(opts[:4])}
    opts = {str(k).strip().upper()[:1]: str(v) for k, v in opts.items()}
    if set(opts) != {"A", "B", "C", "D"}:
        raise ValueError("Options must be exactly A-D")
    ans = str(data["correct_answer"]).strip().upper()[:1]
    if ans not in opts:
        raise ValueError("correct_answer not in options")
    data["options"], data["correct_answer"] = opts, ans
    return data


def generate_ai_question(topic: str, difficulty: str, api_key: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    examples = retrieve_examples(load_bank(), topic, difficulty)
    last_err = None
    for _ in range(2):
        resp = client.models.generate_content(
            model=MODEL,
            contents=build_prompt(topic, difficulty, examples),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.8,
            ),
        )
        try:
            q = parse_question_json(resp.text)
            q.update({"id": f"AI-{random.randint(10000, 99999)}", "topic": topic,
                      "difficulty": difficulty, "exam": topic.split()[0], "source": "AI"})
            return q
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    raise RuntimeError(f"Model output failed validation: {last_err}")


def seed_question(topic: str, difficulty: str, exclude: set[str]) -> dict:
    bank = load_bank()
    pool = [q for q in bank if q["topic"] == topic and q["difficulty"] == difficulty] \
        or [q for q in bank if q["topic"] == topic] or bank
    fresh = [q for q in pool if q["id"] not in exclude] or pool
    q = dict(random.choice(fresh))
    q["source"] = "Seed bank"
    return q


# ---------------------------------------------------------------- state
def init_state():
    today = dt.date.today().isoformat()
    s = st.session_state
    s.setdefault("attempts", [])       # list of dicts
    s.setdefault("error_log", {})      # id -> {question, due_at, stage}
    s.setdefault("current", None)
    s.setdefault("answered", False)
    s.setdefault("streak", 0)
    s.setdefault("best_streak", 0)
    s.setdefault("seen", set())
    if s.get("day") != today:
        s.day = today
        s.ai_used = 0
        s.challenge_done = False
    s.setdefault("ai_used", 0)
    s.setdefault("challenge_done", False)


def daily_challenge() -> dict:
    bank = load_bank()
    rng = random.Random(dt.date.today().toordinal())
    return dict(rng.choice(bank), source="Daily micro-challenge")


def due_reviews() -> list[dict]:
    n = len(st.session_state.attempts)
    return [v for v in st.session_state.error_log.values() if v["due_at"] <= n]


def record_answer(q: dict, choice: str):
    s = st.session_state
    correct = choice == q["correct_answer"]
    s.attempts.append({"id": q["id"], "topic": q["topic"], "difficulty": q["difficulty"],
                       "correct": correct, "trap_type": q.get("trap_type", ""),
                       "time": dt.datetime.now().strftime("%H:%M")})
    s.streak = s.streak + 1 if correct else 0
    s.best_streak = max(s.best_streak, s.streak)
    n = len(s.attempts)
    entry = s.error_log.get(q["id"])
    if not correct:
        s.error_log[q["id"]] = {"question": q, "stage": 0, "due_at": n + REVIEW_INTERVALS[0],
                                "your_answer": choice}
    elif entry:  # correct on a review: push further out or graduate
        entry["stage"] += 1
        if entry["stage"] >= len(REVIEW_INTERVALS):
            del s.error_log[q["id"]]
        else:
            entry["due_at"] = n + REVIEW_INTERVALS[entry["stage"]]
    if q.get("source") == "Daily micro-challenge":
        s.challenge_done = True


def set_current(q: dict):
    st.session_state.current = q
    st.session_state.answered = False
    st.session_state.seen.add(q["id"])


# ---------------------------------------------------------------- UI
st.set_page_config(page_title="CAT/CLAT Adaptive Engine", page_icon="🎯", layout="wide")
init_state()
s = st.session_state
api_key = get_api_key()

with st.sidebar:
    st.title("🎯 Adaptive Engine")
    exam = st.radio("Exam", list(SECTIONS), horizontal=True)
    topic = st.selectbox("Section / topic", SECTIONS[exam])
    difficulty = st.select_slider("Difficulty", DIFFICULTIES, value="Moderate")
    st.divider()
    if api_key:
        st.success(f"AI mode: {MODEL}")
    else:
        st.info("Demo mode: no GEMINI_API_KEY found, serving curated seed questions.")
    st.metric("Free AI questions left today", max(0, FREE_DAILY_AI_LIMIT - s.ai_used))
    st.caption("Pro (₹999/month): unlimited adaptive mocks.")
    st.divider()
    c1, c2 = st.columns(2)
    c1.metric("🔥 Streak", s.streak)
    c2.metric("Best", s.best_streak)
    st.metric("🔁 Reviews due", len(due_reviews()))

st.title("CAT/CLAT Adaptive Mock Test & Analytics Engine")
st.caption("Questions built like a faculty member builds them: every wrong option is a named trap.")

tab_practice, tab_review, tab_analytics = st.tabs(["📝 Practice", "🔁 Error log & review", "📊 Weakness heatmap"])

with tab_practice:
    b1, b2, b3 = st.columns(3)
    if b1.button("Generate question", type="primary", use_container_width=True):
        q = None
        if api_key and s.ai_used < FREE_DAILY_AI_LIMIT:
            with st.spinner("Your coach is writing a question..."):
                try:
                    q = generate_ai_question(topic, difficulty, api_key)
                    s.ai_used += 1
                except Exception as e:
                    st.warning(f"AI generation failed ({e}); serving a seed question instead.")
        elif api_key:
            st.warning("Daily free limit reached. Upgrade to Pro for unlimited; serving a seed question.")
        set_current(q or seed_question(topic, difficulty, s.seen))
    if b2.button("Daily micro-challenge" + (" ✅" if s.challenge_done else ""), use_container_width=True):
        set_current(daily_challenge())
    due = due_reviews()
    if b3.button(f"Review a mistake ({len(due)})", use_container_width=True, disabled=not due):
        set_current(dict(due[0]["question"], source="Spaced-repetition review"))

    q = s.current
    if q is None:
        st.info("Pick a section and difficulty in the sidebar, then hit **Generate question**.")
    else:
        st.markdown(f"**{q['topic']} · {q['difficulty']} · {q.get('concept_tag', '')}**  \n"
                    f"<small>Source: {q.get('source', '')}</small>", unsafe_allow_html=True)
        st.markdown(q["question_text"].replace("\n", "  \n"))
        labels = [f"{k}) {v}" for k, v in q["options"].items()]
        pick = st.radio("Your answer", labels, index=None, key=f"pick_{q['id']}_{len(s.attempts)}",
                        disabled=s.answered)
        if st.button("Submit", disabled=s.answered or pick is None):
            choice = pick[0]
            record_answer(q, choice)
            s.answered = True
            s.last_choice = choice
            st.rerun()
        if s.answered:
            if s.last_choice == q["correct_answer"]:
                st.success(f"Correct! Answer: {q['correct_answer']}")
            else:
                st.error(f"Not quite. You chose {s.last_choice}; correct is {q['correct_answer']}. "
                         "Added to your error log for spaced review.")
            st.markdown(f"**Trap type of the main distractor:** {q.get('trap_type', '-')}")
            with st.expander("Coach's explanation", expanded=True):
                st.write(q["pedagogical_explanation"])

with tab_review:
    if not s.error_log:
        st.info("No mistakes logged yet. Wrong answers appear here and come back after 1, 3 and 7 questions.")
    else:
        n = len(s.attempts)
        rows = [{"Question": v["question"]["id"], "Topic": v["question"]["topic"],
                 "Difficulty": v["question"]["difficulty"], "Trap": v["question"].get("trap_type", ""),
                 "Your answer": v["your_answer"], "Stage": f"{v['stage'] + 1}/{len(REVIEW_INTERVALS)}",
                 "Due": "now" if v["due_at"] <= n else f"in {v['due_at'] - n} questions"}
                for v in s.error_log.values()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tab_analytics:
    if not s.attempts:
        st.info("Answer a few questions to see your weakness heatmap.")
    else:
        df = pd.DataFrame(s.attempts)
        m1, m2, m3 = st.columns(3)
        m1.metric("Attempted", len(df))
        m2.metric("Accuracy", f"{df.correct.mean():.0%}")
        m3.metric("Topics touched", df.topic.nunique())
        pivot = (df.pivot_table(index="topic", columns="difficulty", values="correct", aggfunc="mean")
                 .reindex(columns=[d for d in DIFFICULTIES if d in df.difficulty.unique()]) * 100)
        fig = px.imshow(pivot.round(0), text_auto=True, color_continuous_scale="RdYlGn",
                        zmin=0, zmax=100, aspect="auto", labels=dict(color="Accuracy %"))
        fig.update_layout(title="Accuracy % by topic x difficulty")
        st.plotly_chart(fig, use_container_width=True)
        wrong = df[~df.correct]
        if not wrong.empty:
            st.subheader("Traps you fall for most")
            st.bar_chart(wrong.trap_type.value_counts())
