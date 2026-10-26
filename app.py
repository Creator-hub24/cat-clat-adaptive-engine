"""CAT/CLAT Adaptive Mock Test & Analytics Engine (Streamlit prototype)."""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
import time
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import bank as qbank
import engine
import llm
import payments
import prompts
import store as storage

APP_DIR = Path(__file__).parent
BANK_PATH = APP_DIR / "data" / "sample_bank.json"
try:
    _custom = st.secrets.get("GEMINI_MODEL")
except Exception:
    _custom = None
MODEL_CANDIDATES = prompts.model_candidates(_custom)
FREE_DAILY_AI_LIMIT = 10
REVIEW_INTERVALS = engine.REVIEW_INTERVALS  # 3 -> 7 -> 15 questions
SECTIONS, DIFFICULTIES, SYSTEM_PROMPT = prompts.SECTIONS, prompts.DIFFICULTIES, prompts.SYSTEM_PROMPT
REQUIRED_KEYS = engine.REQUIRED_KEYS
retrieve_examples, build_prompt = prompts.retrieve_examples, prompts.build_prompt


# ---------------------------------------------------------------- data / retrieval
@st.cache_data
def load_bank() -> list[dict]:
    with open(BANK_PATH, encoding="utf-8") as f:
        return json.load(f)["questions"]


# ---------------------------------------------------------------- LLM
def get_api_key() -> str | None:
    try:
        key = st.secrets.get("GEMINI_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")


parse_question_json = engine.parse_question_json


def generate_ai_question(topic: str, difficulty: str, api_key: str, log: list | None = None) -> dict:
    """Generate + verify (sandboxed verify_code and an independent solve); max 2 tries."""
    client = llm.make_client(api_key)
    examples = retrieve_examples(load_bank(), topic, difficulty)
    return llm.generate_verified(client, MODEL_CANDIDATES, topic, difficulty,
                                 build_prompt(topic, difficulty, examples), SYSTEM_PROMPT, log=log)


@st.cache_data(ttl=3600)
def load_pool() -> list[dict]:
    """Seed bank + pre-generated AI bank (rejected items excluded). No API call needed."""
    return qbank.serving_pool(load_bank(), qbank.load_json_bank(qbank.AI_BANK_PATH)["questions"])


def bank_question(topic: str, difficulty: str, exclude: set[str]) -> dict | None:
    """Unseen bank question for this topic+level, or None if the user has seen them all."""
    return qbank.pick_unseen(load_pool(), topic, difficulty, exclude, random)


def seed_question(topic: str, difficulty: str, exclude: set[str]) -> dict:
    """Last-resort fallback: prefer unseen, else repeat (never fails)."""
    q = bank_question(topic, difficulty, exclude)
    if q:
        return q
    pool = [q for q in load_pool() if q["topic"] == topic] or load_pool()
    fresh = [q for q in pool if q["id"] not in exclude] or pool
    return dict(random.choice(fresh))


def mark_seed(q: dict) -> dict:
    q["verified"] = True
    q["verification"] = ["hand-checked"] + (["computed"] if q.get("verify_code") else [])
    q.setdefault("model", None)
    return q


def md_escape(text) -> str:
    """Neutralise markdown/HTML in short model-provided strings (tags, trap names, options)."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$])", r"\\\1", str(text or ""))


# ---------------------------------------------------------------- secrets / account
def secret(name, default=None):
    try:
        v = st.secrets.get(name)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(name, default)


def auth_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def logged_in() -> bool:
    try:
        return auth_configured() and bool(st.user.is_logged_in)
    except Exception:
        return False


@st.cache_resource
def get_store():
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_SERVICE_KEY")
    if not (url and key):
        return None
    try:
        return storage.SupabaseStore(url, key)
    except Exception:
        return None


def current_uid() -> str | None:
    pepper = secret("PEPPER")
    if not (logged_in() and pepper):
        return None
    email = getattr(st.user, "email", None)
    return storage.user_id_hash(email, pepper) if email else None


def profile_from_state() -> dict:
    s = st.session_state
    return {"streak": s.streak, "best_streak": s.best_streak, "usage_day": s.day,
            "ai_used": s.ai_used, "plan": s.plan, "pro_until": s.pro_until,
            "review_queue": s.error_log, "pending_payment_ref": s.get("pending_ref"),
            "topic_levels": s.topic_levels}


def persist():
    s = st.session_state
    if s.get("uid") and s.get("db"):
        try:
            s.db.save_profile(s.uid, profile_from_state())
        except Exception as e:
            st.toast(f"Could not save progress: {e}")


def hydrate_from_store():
    """Load saved progress once per session for a logged-in user."""
    s = st.session_state
    uid, db = current_uid(), get_store()
    if not (uid and db) or s.get("uid") == uid:
        return
    try:
        profile, attempts = db.load(uid)
    except Exception as e:
        st.warning(f"Saved progress unavailable right now ({e}); continuing in guest mode.")
        return
    s.uid, s.db = uid, db
    s.attempts = [{"id": a["question_id"], "topic": a["topic"], "difficulty": a["difficulty"],
                   "correct": a["correct"], "trap_type": a.get("trap_type") or "",
                   "time_taken_s": a.get("time_taken_s"), "timing_class": a.get("timing_class") or "",
                   "time": str(a.get("created_at", ""))[:16]} for a in attempts]
    s.topic_levels = profile.get("topic_levels") or {}
    s.seen = {a.get("question_id") for a in attempts if a.get("question_id")}  # no repeats across sessions
    s.error_log = profile.get("review_queue") or {}
    s.streak, s.best_streak = profile["streak"], profile["best_streak"]
    s.plan, s.pro_until = profile["plan"], profile["pro_until"]
    s.pending_ref = profile.get("pending_payment_ref")
    today = dt.date.today().isoformat()
    s.ai_used = profile["ai_used"] if str(profile.get("usage_day")) == today else 0
    s.day = today
    persist()  # ensures the profile row exists before attempts are inserted


def user_is_pro() -> bool:
    s = st.session_state
    return storage.is_pro({"pro_until": s.get("pro_until")})


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
    s.setdefault("plan", "free")
    s.setdefault("pro_until", None)
    s.setdefault("topic_levels", {})   # topic -> {level, run_correct, run_wrong}
    s.setdefault("q_started", None)
    s.setdefault("session_reports", [])


def daily_challenge() -> dict:
    """Same question for everyone today; no repeat until the whole bank has cycled."""
    approved = [q for q in qbank.load_json_bank(qbank.AI_BANK_PATH)["questions"]
                if q.get("review_status") == "approved" and q.get("verified")]
    base = load_bank() + approved   # only faculty-approved AI items join the shared daily question
    q = dict(engine.daily_pick(base, dt.date.today()), source="Daily micro-challenge")
    return q if q["id"].startswith("AI-") else mark_seed(q)


def due_reviews() -> list[dict]:
    n = len(st.session_state.attempts)
    return [v for v in st.session_state.error_log.values() if v["due_at"] <= n]


def record_answer(q: dict, choice: str, seconds: float):
    s = st.session_state
    correct = choice == q["correct_answer"]
    target = engine.target_seconds(q["topic"], q["difficulty"], q["question_text"])
    tclass = engine.classify(correct, seconds, target)
    s.attempts.append({"id": q["id"], "topic": q["topic"], "difficulty": q["difficulty"],
                       "correct": correct, "trap_type": q.get("trap_type", ""),
                       "time_taken_s": int(seconds), "timing_class": tclass,
                       "time": dt.datetime.now().strftime("%H:%M")})
    s.last_result = {"seconds": int(seconds), "target": target, "class": tclass}
    s.streak = s.streak + 1 if correct else 0
    s.best_streak = max(s.best_streak, s.streak)
    # adaptive level only moves on questions served at the topic's current level
    lvl = s.topic_levels.get(q["topic"]) or engine.new_topic_state()
    if q["difficulty"] == lvl["level"]:
        before = lvl["level"]
        s.topic_levels[q["topic"]] = engine.update_level(lvl, correct, tclass == "Right but too slow")
        after = s.topic_levels[q["topic"]]["level"]
        s.level_change = None if after == before else f"{q['topic']}: {before} → {after}"
    else:
        s.level_change = None
    n = len(s.attempts)
    if not correct:
        engine.schedule_mistake(s.error_log, q, choice, n)
    elif q["id"] in s.error_log:
        engine.advance_review(s.error_log, q["id"], n)
    if q.get("source") == "Daily micro-challenge":
        s.challenge_done = True
    if s.get("uid") and s.get("db"):
        try:
            persist()
            a = s.attempts[-1]
            s.db.add_attempt(s.uid, {"question_id": a["id"], "topic": a["topic"],
                                     "difficulty": a["difficulty"], "correct": a["correct"],
                                     "trap_type": a["trap_type"], "time_taken_s": a["time_taken_s"],
                                     "timing_class": a["timing_class"]})
        except Exception as e:
            st.toast(f"Could not save attempt: {e}")


def set_current(q: dict):
    st.session_state.current = q
    st.session_state.answered = False
    st.session_state.seen.add(q["id"])
    st.session_state.q_started = time.time()


def report_question(q: dict, reason: str):
    rep = {"topic": q["topic"], "question_ref": storage.question_ref(q), "reason": reason}
    db = get_store()
    if db:
        db.add_report(rep)
    else:
        st.session_state.session_reports.append(storage.clean_report(rep))


# ---------------------------------------------------------------- UI
st.set_page_config(page_title="CAT/CLAT Adaptive Engine", page_icon="🎯", layout="wide")
init_state()
hydrate_from_store()
s = st.session_state
pro = user_is_pro()
api_key = get_api_key()

with st.sidebar:
    st.title("🎯 Adaptive Engine")
    exam = st.radio("Exam", list(SECTIONS), horizontal=True)
    topic = st.selectbox("Section / topic", SECTIONS[exam])
    mode = st.radio("Difficulty mode", ["Adaptive", "Manual"], horizontal=True,
                    help="Adaptive: per topic, steps up after 2 fast correct answers and down after 2 wrong.")
    level = (s.topic_levels.get(topic) or engine.new_topic_state())["level"]
    if mode == "Adaptive":
        difficulty = level
        st.info(f"Your level in {topic}: **{level}**")
    else:
        difficulty = st.select_slider("Difficulty", DIFFICULTIES, value=level)
    with st.expander("My level per topic"):
        st.dataframe(pd.DataFrame([{"Topic": t, "Level": (s.topic_levels.get(t) or engine.new_topic_state())["level"]}
                                   for sec in SECTIONS.values() for t in sec]), hide_index=True,
                     width="stretch")
    st.divider()
    if api_key:
        st.success("AI mode (verified): " + " → ".join(MODEL_CANDIDATES))
    else:
        st.info("No GEMINI_API_KEY: serving the verified question bank (seed + pre-generated). Live AI is off.")
    if pro:
        st.success(f"⭐ Pro until {s.pro_until}: unlimited AI questions")
    else:
        st.metric("Free live-AI questions left today", max(0, FREE_DAILY_AI_LIMIT - s.ai_used))
    st.divider()
    st.subheader("Account")
    if not auth_configured():
        st.caption("Guest mode: progress lasts for this browser session only.")
    elif not logged_in():
        st.caption("Guest mode. Sign in to save progress (we store only a hashed ID, never your email).")
        if st.button("Sign in with Google", width="stretch"):
            st.login()
    else:
        if s.get("uid"):
            st.caption("✅ Progress is being saved (pseudonymous ID).")
        else:
            st.caption("Signed in, but storage is not configured: session-only.")
        if st.button("Sign out", width="stretch"):
            for k in list(s.keys()):
                del s[k]
            st.logout()
    # ---- Pro upgrade
    if not pro:
        st.subheader("Go Pro · ₹999/month")
        rz_id, rz_secret = secret("RAZORPAY_KEY_ID"), secret("RAZORPAY_KEY_SECRET")
        if not (rz_id and rz_secret and s.get("uid")):
            st.caption("Pro coming soon." if not (rz_id and rz_secret)
                       else "Sign in to upgrade (Pro is tied to your saved account).")
        else:
            if st.button("Upgrade to Pro", width="stretch"):
                try:
                    link = payments.create_link(rz_id, rz_secret, s.uid, secret("APP_URL"))
                    s.pending_ref, s.pay_url = link["reference_id"], link["short_url"]
                    persist()
                except Exception as e:
                    st.error(f"Could not create payment link: {e}")
            pay_url = s.get("pay_url") or (secret("RAZORPAY_PAYMENT_LINK") if not s.get("pending_ref") else None)
            if pay_url:
                st.link_button("Pay securely on Razorpay ↗", pay_url, width="stretch")
            if s.get("pending_ref") and st.button("I've paid, verify", width="stretch"):
                try:
                    if payments.verify_paid(rz_id, rz_secret, s.pending_ref):
                        prof = payments.extend_pro(profile_from_state())
                        s.plan, s.pro_until, s.pending_ref = prof["plan"], prof["pro_until"], None
                        s.pop("pay_url", None)
                        persist()
                        st.success("Payment verified. Welcome to Pro!")
                        st.rerun()
                    else:
                        st.warning("Payment not found yet. If you just paid, wait a minute and retry.")
                except Exception as e:
                    st.error(f"Verification failed: {e}")
            st.caption("Payments are handled by Razorpay. We never see or store card/UPI details.")
    st.divider()
    c1, c2 = st.columns(2)
    c1.metric("🔥 Streak", s.streak)
    c2.metric("Best", s.best_streak)
    st.metric("🔁 Reviews due", len(due_reviews()))

st.title("CAT/CLAT Adaptive Mock Test & Analytics Engine")
st.caption("Questions built like a faculty member builds them: every wrong option is a named trap.")

tab_practice, tab_review, tab_analytics, tab_privacy = st.tabs(
    ["📝 Practice", "🔁 Error log & review", "📊 Weakness heatmap", "🔒 Privacy & my data"])

with tab_practice:
    b1, b2, b3 = st.columns(3)
    if b1.button("Next question", type="primary", width="stretch"):
        # Default: serve from the verified bank, no live API call. Live AI only for Pro users,
        # or when this user has exhausted the bank for this topic+level (free users: daily cap).
        q = None if pro and api_key else bank_question(topic, difficulty, s.seen)
        if q is None and api_key and (pro or s.ai_used < FREE_DAILY_AI_LIMIT):
            with st.spinner("Your coach is writing and double-checking a question..."):
                try:
                    q = generate_ai_question(topic, difficulty, api_key)
                    s.ai_used += 1
                    persist()
                except Exception as e:
                    st.warning("Couldn't produce a question that passed verification, so here is a "
                               "hand-checked seed question instead.")
                    with st.expander("Verification details"):
                        st.text(str(e)[:1500])
        elif q is None and api_key:
            st.warning("You've done every bank question at this level and today's free AI questions are used up. "
                       "Upgrade to Pro for unlimited fresh questions; serving a question from another level for now.")
        elif q is None:
            st.info("You've done every bank question at this level, so here is one from another level of this topic.")
        set_current(q or seed_question(topic, difficulty, s.seen))
    if b2.button("Daily micro-challenge" + (" ✅" if s.challenge_done else ""), width="stretch"):
        set_current(daily_challenge())
    due = due_reviews()
    if b3.button(f"Review a mistake ({len(due)})", width="stretch", disabled=not due):
        set_current(dict(due[0]["question"], source="Spaced-repetition review"))
    if s.get("level_change"):
        st.toast(f"Adaptive level changed: {s.level_change}")

    q = s.current
    if q is None:
        st.info("Pick a section and difficulty in the sidebar, then hit **Next question**.")
    else:
        badge = ("✅ Verified (" + ", ".join(q.get("verification", [])) + ")") if q.get("verified") else "⚠️ Unverified"
        meta = f"{q['topic']} · {q['difficulty']} · {md_escape(q.get('concept_tag', ''))}"
        st.markdown(f"**{meta}**")
        lo, hi = engine.target_seconds(q["topic"], q["difficulty"], q["question_text"])
        st.caption(f"{badge} · Source: {q.get('source', '')}" + (f" · model: {q['model']}" if q.get("model") else "")
                   + f" · Target time: {lo}-{hi}s")
        # model text rendered as markdown only (tables ok); raw HTML is never enabled
        st.markdown(q["question_text"].replace("\n", "  \n") if "|" not in q["question_text"] else q["question_text"])
        labels = [f"{k}) {md_escape(v)}" for k, v in q["options"].items()]
        pick = st.radio("Your answer", labels, index=None, key=f"pick_{q['id']}_{len(s.attempts)}",
                        disabled=s.answered)
        if st.button("Submit", disabled=s.answered or pick is None):
            choice = pick[0]
            record_answer(q, choice, time.time() - (s.q_started or time.time()))
            s.answered = True
            s.last_choice = choice
            st.rerun()
        if s.answered:
            if s.last_choice == q["correct_answer"]:
                st.success(f"Correct! Answer: {q['correct_answer']}")
            else:
                st.error(f"Not quite. You chose {s.last_choice}; correct is {q['correct_answer']}. "
                         "Added to your error log for spaced review.")
            r = s.get("last_result") or {}
            if r:
                msg = f"⏱️ {r['seconds']}s (target {r['target'][0]}-{r['target'][1]}s): {r['class']}"
                (st.warning if r["class"] == "Right but too slow" else st.caption)(
                    msg + (". Right, but too slow to count toward levelling up." if r["class"] == "Right but too slow" else ""))
            st.markdown(f"**Trap type of the main distractor:** {md_escape(q.get('trap_type', '-'))}")
            with st.expander("Coach's explanation", expanded=True):
                st.markdown(q["pedagogical_explanation"])
            with st.expander("🚩 Report this question"):
                reason = st.selectbox("What's wrong?", storage.REPORT_REASONS, key=f"rr_{q['id']}")
                if st.button("Send report", key=f"rb_{q['id']}"):
                    try:
                        report_question(q, reason)
                        st.success("Thanks! Reported anonymously (topic, question reference and reason only).")
                    except Exception as e:
                        st.error(f"Could not save report: {e}")

with tab_review:
    if not s.error_log:
        st.info("No mistakes logged yet. Wrong answers appear here and come back after 3, 7 and 15 questions.")
    else:
        n = len(s.attempts)
        rows = [{"Question": v["question"]["id"], "Topic": v["question"]["topic"],
                 "Difficulty": v["question"]["difficulty"], "Trap": v["question"].get("trap_type", ""),
                 "Your answer": v["your_answer"], "Stage": f"{v['stage'] + 1}/{len(REVIEW_INTERVALS)}",
                 "Due": "now" if v["due_at"] <= n else f"in {v['due_at'] - n} questions"}
                for v in s.error_log.values()]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

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
        st.plotly_chart(fig, width="stretch")
        if "timing_class" in df:
            st.subheader("Speed: right but too slow")
            tc = (df.assign(timing_class=df.timing_class.replace("", "Unknown"))
                  .pivot_table(index="topic", columns="timing_class", values="correct", aggfunc="size", fill_value=0))
            st.bar_chart(tc)
            slow = (df.timing_class == "Right but too slow").sum()
            st.caption(f"{slow} of {int(df.correct.sum())} correct answers were slower than target. "
                       "In the exam these cost you time on other questions.")
        wrong = df[~df.correct]
        if not wrong.empty:
            st.subheader("Traps you fall for most")
            st.bar_chart(wrong.trap_type.value_counts())

with tab_privacy:
    st.markdown((APP_DIR / "PRIVACY.md").read_text(encoding="utf-8") if (APP_DIR / "PRIVACY.md").exists()
                else "See PRIVACY.md in the repository.")
    st.divider()
    st.subheader("Your data controls")
    if not s.get("uid"):
        st.info("You are in guest mode: nothing is saved on our servers. Closing the tab erases your session.")
    else:
        st.download_button("⬇️ Download my data (JSON)",
                           json.dumps(storage.export_data(s.db, s.uid), indent=2, default=str),
                           file_name="my-cat-clat-data.json", mime="application/json")
        confirm = st.checkbox("I understand this permanently deletes all my saved progress, error log and plan status.")
        if st.button("🗑️ Delete my data", type="primary", disabled=not confirm):
            try:
                s.db.delete_all(s.uid)
                for k in list(s.keys()):
                    del s[k]
                st.success("All your data has been deleted.")
                st.logout()
            except Exception as e:
                st.error(f"Deletion failed: {e}")
