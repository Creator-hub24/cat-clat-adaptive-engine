<h1 align="center">🎯 CAT/CLAT Adaptive Mock Test & Analytics Engine</h1>

<p align="center">
  <a href="https://cat-clat-adaptive-engine-gzkqrxpowaogew7ptmabip.streamlit.app/"><img src="https://static.streamlit.io/badges/streamlit_badge_black_white.svg" alt="Open in Streamlit"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/LLM-Gemini%20Flash-orange" alt="Gemini">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
</p>

<p align="center"><b>An AI practice engine that writes questions the way a CAT/CLAT faculty member does: every wrong option is a named trap.</b></p>

> Built by **Vaibhav Gupta**, who taught CAT/CLAT at Career Launcher for 6 years. Plenty of people can wrap an LLM. This project encodes *why* an RC option is a trap and *how* QA difficulty scales non-linearly into prompts, rubrics and analytics. See [PRD.md](PRD.md) for the full product and pedagogy rationale.

## 🎥 Demo
- **Live app:** https://cat-clat-adaptive-engine-gzkqrxpowaogew7ptmabip.streamlit.app/
- **Video walkthrough:** TODO: not recorded yet

| Practice | Weakness heatmap |
|---|---|
| ![Practice screen](docs/screenshot-practice.png) | ![Heatmap](docs/screenshot-heatmap.png) |
*TODO: screenshots not added yet; the image links above are placeholders.*

## ✨ Features
- **Controlled generation:** CAT Quant, CAT VARC RC, CAT DILR, CLAT RC and CLAT Logical Reasoning at Easy / Moderate / CAT-Level, using a faculty system prompt, a difficulty rubric, topic rules and retrieved few-shot examples.
- **Adaptive difficulty per topic (default):** your level in each topic steps up after 2 consecutive correct answers *within the target time* and down after 2 consecutive wrong ones. Levels are saved for signed-in users. A manual override is in the sidebar.
- **Answer-key checks on AI questions:** for Quant (and computable DILR) the model must also return a short Python `verify_code`, which runs in a restricted sandbox (3 s timeout; only `math`, `itertools` and `fractions`; no files or network) and must reproduce the key. Every AI question then gets a separate solve pass with the key hidden. If either check disagrees, the app regenerates (max 2 tries) and then falls back to a seed question. Questions that pass show a ✅ Verified badge. These checks reduce wrong keys; they do not eliminate them. Use **Report this question** (anonymous) when one slips through.
- **Per-question timer:** targets of Easy ≈ 60 s, Moderate 90–120 s and CAT-Level 2–3 min, with RC targets scaled by passage length. Correct-but-slow answers are tagged **Right but too slow** in feedback and analytics.
- **Strict JSON + validation:** fence stripping, trailing-comma repair, A–D normalisation and key checks.
- **Pedagogical feedback:** the correct answer, the trap type of the main distractor (Extreme scope, Out-of-scope, Half-true, Reversal…), and a step-by-step explanation with the shortcut.
- **Error log + spaced repetition:** mistakes come back after 3 → 7 → 15 questions.
- **Weakness heatmap:** accuracy by topic × difficulty, a speed breakdown (on time / too slow / wrong), and the traps you fall for most.
- **Streaks & a daily micro-challenge** (cycles through the whole seed bank before repeating).
- **Freemium + Pro:** 10 AI questions/day free; **Pro ₹999/month** unlimited, paid through Razorpay Payment Links (no card data touches the app).
- **Optional Google sign-in:** saves your progress across devices. Guest mode works without it.
- **Privacy-first:** only a hashed ID is stored (HMAC-SHA256 of your email + a server secret). No email, name or photo. One-click **Download my data** and **Delete my data**. See **[PRIVACY.md](PRIVACY.md)**.
- **Always-on demo:** with no API key, the app serves 45 original seed questions (9 per section, across all three difficulties). All answer keys are hand-checked, and every Quant key is also verified by computation in the test suite.

## 🏗️ Architecture
```
Sidebar (exam/topic/difficulty)
        │
        ▼
retrieve_examples()  ← data/sample_bank.json (seed bank / RAG corpus)
        │
        ▼
build_prompt() + SYSTEM_PROMPT  ──►  Gemini (JSON mode), first available of:
        │                           GEMINI_MODEL (optional) → gemini-3.8-flash
        │                           → gemini-flash-latest → gemini-2.5-flash
        │                                   │
        │                         parse → sandbox verify_code → independent solve
        │                         ── fail ×2 ──► seed fallback
        ▼
Practice UI ─► record_answer() ─► session_state: attempts, error_log, streak
                                         │
                                         ▼
                              Heatmap (pandas + Plotly)
```

```
cat-clat-adaptive-engine/
├── app.py                        # Streamlit app
├── data/sample_bank.json         # 45 original seed questions (explanations, trap types, verify_code)
├── engine.py                     # Adaptive levels, timing, spacing, sandboxed verifier
├── llm.py                        # Gemini calls + verification pipeline
├── store.py                      # Privacy-first storage (hashed IDs, Supabase)
├── payments.py                   # Razorpay Payment Links
├── PRIVACY.md
├── supabase/schema.sql
├── tests/
├── PRD.md                        # Product requirements + pedagogical rationale
├── requirements.txt
├── .streamlit/secrets.toml.example
└── LICENSE
```

## 🚀 Run locally
```bash
git clone https://github.com/Creator-hub24/cat-clat-adaptive-engine.git
cd cat-clat-adaptive-engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# optional: enable AI generation (without it the app runs in seed-bank demo mode)
export GEMINI_API_KEY="your-key"        # or copy .streamlit/secrets.toml.example to .streamlit/secrets.toml

streamlit run app.py
```

## 🔐 Optional services setup
Every service is optional. If its secrets are missing, the app falls back: guest mode, session-only storage, "Pro coming soon".

| Feature | Secrets | Where |
|---|---|---|
| AI questions | `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |
| Google sign-in | `[auth]` block | Google Cloud Console → OAuth client (Web). Redirect URI: `https://<your-app>.streamlit.app/oauth2callback` |
| Saved progress | `PEPPER`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Supabase project → run [`supabase/schema.sql`](supabase/schema.sql) in the SQL editor |
| Pro payments | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `APP_URL` | Razorpay Dashboard → API Keys (test mode first) |

All keys are listed in [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example).

> ⚠️ `SUPABASE_SERVICE_KEY` is the service-role key. It stays server-side in Streamlit secrets and is never sent to the browser. RLS is enabled with no public policies, so the anon key can't read anything. Never change `PEPPER` after launch, because that would orphan every user's saved data.

Run the tests: `pip install pytest && pytest -q tests`

## ☁️ Deploy to Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **Create app** → repo `Creator-hub24/cat-clat-adaptive-engine`, branch `main`, file `app.py`.
3. **Advanced settings → Secrets:** paste `GEMINI_API_KEY = "your-key"`.
4. Deploy. Optionally set `GEMINI_MODEL` to pin a model; otherwise the fallback list above is used.

## 🧭 Roadmap
Mentor Meera's test builder, IRT-based adaptive sequencing. See [PRD.md §9](PRD.md#9-roadmap).

## 📄 License
MIT © 2026 Vaibhav Gupta
