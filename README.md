<h1 align="center">🎯 CAT/CLAT Adaptive Mock Test & Analytics Engine</h1>

<p align="center">
  <a href="https://YOUR-APP.streamlit.app"><img src="https://static.streamlit.io/badges/streamlit_badge_black_white.svg" alt="Open in Streamlit"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/LLM-Gemini%202.5%20Flash-orange" alt="Gemini">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
</p>

<p align="center"><b>An AI practice engine that writes questions the way a CAT/CLAT faculty member does: every wrong option is a named trap.</b></p>

> Built by **Vaibhav Gupta**, who taught CAT/CLAT at Career Launcher for 6 years. Plenty of people can wrap an LLM. This project encodes *why* an RC option is a trap and *how* QA difficulty scales non-linearly into prompts, rubrics and analytics. See [PRD.md](PRD.md) for the full product and pedagogy rationale.

## 🎥 Demo
- **Live app:** `https://YOUR-APP.streamlit.app` *(replace after deploy)*
- **Video walkthrough:** `https://youtu.be/VIDEO_ID` *(coming soon)*

| Practice | Weakness heatmap |
|---|---|
| ![Practice screen](docs/screenshot-practice.png) | ![Heatmap](docs/screenshot-heatmap.png) |
*(screenshots coming soon)*

## ✨ Features
- **Controlled generation:** CAT Quant, CAT VARC RC, CAT DILR, CLAT RC and CLAT Logical Reasoning at Easy / Moderate / CAT-Level, using a faculty system prompt, a difficulty rubric, topic rules and retrieved few-shot examples.
- **Strict JSON + validation:** fence stripping, trailing-comma repair, A–D normalisation and key checks, with a retry and then a fallback.
- **Pedagogical feedback:** the correct answer, the trap type of the main distractor (Extreme scope, Out-of-scope, Half-true, Reversal…), and a step-by-step explanation with the shortcut.
- **Error log + spaced repetition:** mistakes come back after 1 → 3 → 7 questions.
- **Weakness heatmap:** accuracy by topic × difficulty, plus the traps you fall for most.
- **Streaks & a daily micro-challenge.**
- **Freemium meter:** 10 AI questions/day (Pro tier ₹999/month in the PRD).
- **Always-on demo:** with no API key, the app serves 15 original, curated seed questions.

## 🏗️ Architecture
```
Sidebar (exam/topic/difficulty)
        │
        ▼
retrieve_examples()  ← data/sample_bank.json (seed bank / RAG corpus)
        │
        ▼
build_prompt() + SYSTEM_PROMPT  ──►  Gemini 2.5 Flash (JSON mode)
        │                                   │
        │                         parse_question_json() ── fail ──► seed fallback
        ▼
Practice UI ─► record_answer() ─► session_state: attempts, error_log, streak
                                         │
                                         ▼
                              Heatmap (pandas + Plotly)
```

```
cat-clat-adaptive-engine/
├── app.py                        # Streamlit app
├── data/sample_bank.json         # 15 original seed questions with explanations & trap types
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

## ☁️ Deploy to Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **Create app** → repo `Creator-hub24/cat-clat-adaptive-engine`, branch `main`, file `app.py`.
3. **Advanced settings → Secrets:** paste `GEMINI_API_KEY = "your-key"`.
4. Deploy, then copy the `*.streamlit.app` URL into the badge and demo links above.

## 🧭 Roadmap
Persistent accounts, server-side metering, an answer-key verifier model, Mentor Meera's test builder, IRT-based adaptive sequencing. See [PRD.md §9](PRD.md#9-roadmap).

## 📄 License
MIT © 2026 Vaibhav Gupta
