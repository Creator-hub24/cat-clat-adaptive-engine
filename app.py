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
import families
import guard
import payments
import prompts
import store as storage

APP_DIR = Path(__file__).parent
try:
    _family_key = st.secrets.get("EXAM_FAMILY")
except Exception:
    _family_key = None
FAMILY = families.get_family(_family_key or os.environ.get("EXAM_FAMILY"))  # default: mgmt_law
FAMILY_TOPICS = families.family_topics(FAMILY)
BANK_PATH = APP_DIR / "data" / ("sample_bank.json" if FAMILY["key"] == families.DEFAULT_FAMILY
                                else f"sample_bank_{FAMILY['key']}.json")
FREE_DAILY_QUESTION_CAP = guard.FREE_DAILY_QUESTION_CAP  # free: total questions per IST day, bank only
REVIEW_INTERVALS = engine.REVIEW_INTERVALS  # 3 -> 7 -> 15 questions
SECTIONS, DIFFICULTIES = FAMILY["sections"], prompts.DIFFICULTIES
REQUIRED_KEYS = engine.REQUIRED_KEYS


# ---------------------------------------------------------------- data / retrieval
@st.cache_data
def load_bank() -> list[dict]:
    if not BANK_PATH.exists():
        return []
    with open(BANK_PATH, encoding="utf-8") as f:
        return [q for q in json.load(f)["questions"] if q["topic"] in FAMILY_TOPICS]


parse_question_json = engine.parse_question_json


@st.cache_data(ttl=3600)
def load_pool() -> list[dict]:
    """Seed bank + scheduled (pre-generated) AI bank + imports, rejected items excluded. No API call needed.
    pick_unseen serves the scheduled AI questions first."""
    pool = qbank.serving_pool(load_bank(), qbank.load_json_bank(qbank.AI_BANK_PATH)["questions"],
                              qbank.load_json_bank(qbank.APTISETU_PATH)["questions"])
    return [q for q in pool if q["topic"] in FAMILY_TOPICS]  # only this app's exams


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
def _make_store(url, key, family):
    return storage.SupabaseStore(url, key, family=family)


def get_store():
    # Cache keyed on the secrets, and never cache a failure, so adding
    # secrets later takes effect without a manual reboot.
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_SERVICE_KEY")
    if not (url and key):
        return None
    try:
        return _make_store(str(url).strip(), str(key).strip(), FAMILY["key"])
    except Exception as e:
        st.session_state["store_error"] = str(e)[:200]
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
            "topic_levels": s.topic_levels, "pro_purchases": s.get("pro_purchases", 0)}


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
    s.pro_purchases = int(profile.get("pro_purchases") or 0)
    today = guard.ist_today()
    # Free daily counter (profiles.usage_day / ai_used, IST day). Keep any guest-session count from today.
    session_used = s.ai_used if s.get("day") == today else 0
    s.ai_used = max(session_used, guard.free_used_today(profile.get("usage_day"), profile.get("ai_used")))
    s.day = today
    persist()  # ensures the profile row exists before attempts are inserted
    # One active session per (user, exam_family): this sign-in takes over from any older one.
    s.session_token, s.session_lost = guard.new_session_token(), False
    g = db.load_guard(uid) or {}
    s.cooldown_until = g.get("cooldown_until")
    db.save_guard(uid, {"session_token": s.session_token,
                        "session_started_at": dt.datetime.now(dt.timezone.utc).isoformat()})


def serve_gate() -> str | None:
    """Pro (unlimited) only: None if a question may be served now, else the friendly message to show.
    Guards the bank against scripted scraping. Degrades gracefully if usage_guard is missing."""
    s = st.session_state
    now = time.time()
    g = s.db.load_guard(s.uid) if s.get("uid") and s.get("db") else None
    if g is not None and s.get("session_token") and not guard.session_is_current(g.get("session_token"), s.session_token):
        s.session_lost = True
    if s.get("session_lost"):
        return guard.OTHER_DEVICE_MESSAGE
    if guard.in_cooldown(s.get("cooldown_until") or (g or {}).get("cooldown_until"), now):
        return guard.COOLDOWN_MESSAGE
    s.req_times = (s.req_times + [now])[-20:]
    if guard.too_fast(s.req_times, now):
        until = guard.cooldown_until(now)
        s.cooldown_until, s.req_times = until, []
        if s.get("uid") and s.get("db"):
            s.db.save_guard(s.uid, {"cooldown_until": dt.datetime.fromtimestamp(until, dt.timezone.utc).isoformat()})
            s.db.log_abuse(s.uid, "speed", f"cooldown {guard.COOLDOWN_S}s")
        return guard.COOLDOWN_MESSAGE
    return None


def apply_verified_payment(ref: str):
    """Record the payment ref before extending Pro. False = already consumed (replay or another
    session won the race); True/None = go ahead (None: consumed_payments table missing)."""
    s = st.session_state
    db = s.get("db") or get_store()
    if not db or not hasattr(db, "consume_payment"):
        return None
    return db.consume_payment(ref, s.get("uid"))


def user_is_pro() -> bool:
    s = st.session_state
    return storage.is_pro({"pro_until": s.get("pro_until")})


# ---------------------------------------------------------------- state
def init_state():
    today = guard.ist_today()  # free counter and daily challenge follow the IST day
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
    s.setdefault("ai_used", 0)         # free: questions served today (IST), all from the bank
    s.setdefault("req_times", [])      # epoch seconds of recent Pro question requests (speed check)
    s.setdefault("cooldown_until", None)
    s.setdefault("session_token", None)
    s.setdefault("session_lost", False)
    s.setdefault("challenge_done", False)
    s.setdefault("plan", "free")
    s.setdefault("pro_until", None)
    s.setdefault("topic_levels", {})   # topic -> {level, run_correct, run_wrong}
    s.setdefault("q_started", None)
    s.setdefault("session_reports", [])


def daily_challenge() -> dict:
    """Same question for everyone today; no repeat until the whole bank has cycled."""
    approved = [q for q in qbank.load_json_bank(qbank.AI_BANK_PATH)["questions"]
                if q.get("review_status") == "approved" and q.get("verified") and q["topic"] in FAMILY_TOPICS]
    base = load_bank() + approved   # only faculty-approved AI items join the shared daily question
    q = dict(engine.daily_pick(base, dt.date.fromisoformat(guard.ist_today())), source="Daily micro-challenge")
    return q if q["id"].startswith("AI-") else mark_seed(q)


def due_reviews() -> list[dict]:
    n = len(st.session_state.attempts)
    return [v for v in st.session_state.error_log.values()
            if v["due_at"] <= n and v["question"].get("topic") in FAMILY_TOPICS]  # this app's mistakes only


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
st.set_page_config(page_title=FAMILY["name"], page_icon=FAMILY["icon"], layout="wide")
if families.theme_css(FAMILY):  # mgmt_law: none, so its look is unchanged
    st.markdown(families.theme_css(FAMILY), unsafe_allow_html=True)  # static CSS from families.py only
init_state()
hydrate_from_store()
s = st.session_state
pro = user_is_pro()

with st.sidebar:
    st.title(FAMILY["sidebar_title"])
    if FAMILY["coming_soon"]:
        st.info("Coming soon: questions for this app are being prepared.")
        st.stop()
    _lbl = FAMILY["level_labels"]
    exam = st.radio("Exam", list(SECTIONS), horizontal=True)
    topic = st.selectbox("Section / topic", SECTIONS[exam])
    mode = st.radio("Difficulty mode", ["Adaptive", "Manual"], horizontal=True,
                    help="Adaptive: per topic, steps up after 2 fast correct answers and down after 2 wrong.")
    level = (s.topic_levels.get(topic) or engine.new_topic_state())["level"]
    if mode == "Adaptive":
        difficulty = level
        st.info(f"Your level in {topic}: **{_lbl.get(level, level)}**")
    else:
        difficulty = st.select_slider("Difficulty", DIFFICULTIES, value=level, format_func=lambda d: _lbl.get(d, d))
    with st.expander("My level per topic"):
        st.dataframe(pd.DataFrame([{"Topic": t, "Level": (s.topic_levels.get(t) or engine.new_topic_state())["level"]}
                                   for sec in SECTIONS.values() for t in sec]), hide_index=True,
                     width="stretch")
    st.divider()
    st.caption("Serving the verified question bank: today's freshest questions first. "
               "New verified questions are added every day.")
    if s.get("session_lost"):
        st.warning(guard.OTHER_DEVICE_MESSAGE)
    if pro:
        st.success(f"⭐ Pro until {s.pro_until}: Unlimited practice")
        st.caption(guard.PRO_NOTE)
    else:
        st.metric("Free questions left today", max(0, FREE_DAILY_QUESTION_CAP - s.ai_used))
        st.caption(guard.FREE_NOTE + " Resets at midnight IST.")
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
            err = s.get("store_error")
            st.caption("Signed in, but storage is not configured: session-only."
                       + (f" ({err})" if err else ""))
        if st.button("Sign out", width="stretch"):
            for k in list(s.keys()):
                del s[k]
            st.logout()
    # ---- Pro upgrade
    if not pro:
        price = payments.price_for(profile_from_state())
        intro = price == payments.INTRO_PRICE_PAISE
        st.subheader("Go Pro · first month ₹499, then ₹999/month" if intro else "Go Pro · ₹999/month")
        if intro:
            st.markdown("🎉 **First-time offer: ₹500 off your first month** · ~~₹999~~ **₹499**")
        st.markdown(f"**{guard.PRO_PITCH}**")
        st.caption(("Intro offer for your first Pro month. " if intro else "")
                   + "Each payment unlocks Pro for 30 days. There is no auto-debit: when it ends, you pay again "
                   "(₹999) only if you want to continue.")
        rz_id, rz_secret = secret("RAZORPAY_KEY_ID"), secret("RAZORPAY_KEY_SECRET")
        if s.get("db") is not None and not getattr(s.db, "entitlements_ok", True) and FAMILY["key"] != families.DEFAULT_FAMILY:
            st.caption("Pro coming soon for this app (database setup pending).")
        elif not (rz_id and rz_secret and s.get("uid")):
            st.caption("Pro coming soon." if not (rz_id and rz_secret)
                       else "Sign in to upgrade (Pro is tied to your saved account).")
        else:
            if st.button("Upgrade to Pro", width="stretch"):
                try:
                    link = payments.create_link(rz_id, rz_secret, s.uid, price, secret("APP_URL"),
                                                app_name=FAMILY["name"], exam_family=FAMILY["key"])
                    s.pending_ref, s.pay_url = link["reference_id"], link["short_url"]
                    persist()
                except Exception as e:
                    st.error(f"Could not create payment link: {e}")
            pay_url = s.get("pay_url") or (secret("RAZORPAY_PAYMENT_LINK") if not s.get("pending_ref") else None)
            if pay_url:
                st.link_button(f"Pay ₹{price // 100} securely on Razorpay ↗" if s.get("pay_url")
                               else "Pay securely on Razorpay ↗", pay_url, width="stretch")
            if s.get("pending_ref") and st.button("I've paid, verify", width="stretch"):
                try:
                    if payments.verify_paid(rz_id, rz_secret, s.pending_ref, price, exam_family=FAMILY["key"]):
                        if apply_verified_payment(s.pending_ref) is False:
                            s.pending_ref = None
                            s.pop("pay_url", None)
                            persist()
                            st.info("This payment was already applied to your Pro plan.")
                            st.rerun()
                        prof = payments.extend_pro(profile_from_state())
                        s.plan, s.pro_until, s.pending_ref = prof["plan"], prof["pro_until"], None
                        s.pro_purchases = prof["pro_purchases"]
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

st.title(FAMILY["title"])
st.caption(FAMILY["tagline"])

tab_practice, tab_review, tab_analytics, tab_privacy = st.tabs(
    ["📝 Practice", "🔁 Error log & review", "📊 Weakness heatmap", "🔒 Privacy & my data"])

with tab_practice:
    b1, b2, b3 = st.columns(3)
    if b1.button("Next question", type="primary", width="stretch"):
        # No live AI at runtime for anyone: every question comes from the verified bank, freshest
        # scheduled AI questions first, then the rest of the bank (no repeats, rejected items excluded).
        # Free: 10 questions per IST day in total. Pro: unlimited (speed check + one session apply).
        level_msg = "You've done every bank question at this level, so here is one from another level of this topic."
        if pro:
            gate_msg = serve_gate()
            if gate_msg:
                st.info(gate_msg)
            else:
                q = bank_question(topic, difficulty, s.seen)
                if q is None:
                    st.info(guard.PRO_LEVEL_DONE_MESSAGE)
                set_current(q or seed_question(topic, difficulty, s.seen))
        else:
            q, s.ai_used, note = guard.serve_free(
                s.ai_used, bank=lambda: bank_question(topic, difficulty, s.seen),
                fallback=lambda: seed_question(topic, difficulty, s.seen))
            if q is None:
                st.warning(guard.FREE_CAP_MESSAGE)
            else:
                if note == "level_exhausted":
                    st.info(level_msg)
                set_current(q)
                persist()
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
    if not any(v["question"].get("topic") in FAMILY_TOPICS for v in s.error_log.values()):
        st.info("No mistakes logged yet. Wrong answers appear here and come back after 3, 7 and 15 questions.")
    else:
        n = len(s.attempts)
        rows = [{"Question": v["question"]["id"], "Topic": v["question"]["topic"],
                 "Difficulty": v["question"]["difficulty"], "Trap": v["question"].get("trap_type", ""),
                 "Your answer": v["your_answer"], "Stage": f"{v['stage'] + 1}/{len(REVIEW_INTERVALS)}",
                 "Due": "now" if v["due_at"] <= n else f"in {v['due_at'] - n} questions"}
                for v in s.error_log.values() if v["question"].get("topic") in FAMILY_TOPICS]
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
