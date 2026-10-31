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
- **Controlled generation:** CAT Quant, CAT VARC RC, CAT DILR, CLAT RC, CLAT Logical Reasoning, CLAT Legal Reasoning, CLAT Current Affairs & GK, IPMAT Quant and IPMAT Verbal at Easy / Moderate / CAT-Level, using a faculty system prompt, a difficulty rubric, topic rules and retrieved few-shot examples.
- **Adaptive difficulty per topic (default):** your level in each topic steps up after 2 consecutive correct answers *within the target time* and down after 2 consecutive wrong ones. Levels are saved for signed-in users. A manual override is in the sidebar.
- **Answer-key checks on AI questions:** for Quant and CAT DILR the model must also return a short Python `verify_code`, which runs in a restricted sandbox (3 s timeout; only `math`, `itertools` and `fractions`; no files or network) and must reproduce the key. For CAT DILR the code also brute-forces every arrangement and lists all consistent answers in `answers`; the item is kept only when exactly one answer fits and it matches the key (a unique set-up). Every AI question then gets a separate solve pass with the key hidden. If either check disagrees, the app regenerates (max 2 tries) and then falls back to a seed question. Questions that pass show a ✅ Verified badge. These checks reduce wrong keys; they do not eliminate them. Use **Report this question** (anonymous) when one slips through.
- **Per-question timer:** targets of Easy ≈ 60 s, Moderate 90–120 s and CAT-Level 2–3 min, with RC targets scaled by passage length. Correct-but-slow answers are tagged **Right but too slow** in feedback and analytics.
- **Pre-generated, verified question bank (default):** practice is served from the 45 hand-checked seed questions plus `data/ai_bank.json` (first batch: 7 live-generated, verified and spot-checked questions; the Gemini free tier allows only 20 requests/day per model, about 50 questions/day across the fallback models, so run `python scripts/build_bank.py --per-cell 14` daily to resume toward the ~210 target), a bank generated offline by `scripts/build_bank.py` through the same verification pipeline. No live API call happens per question, so the app costs nothing per user and keeps working under load or when the API is down. No question repeats for a user until the bank for that topic and level runs out (tracked across devices when signed in). There is no live AI at runtime for anyone (free or Pro): the only AI cost is the scheduled daily batch that tops up `data/ai_bank.json` through `scripts/build_bank.py`. Scheduled AI questions are served first, freshest generation day first (by `created_at`), so users see the newest questions before older ones; once a user has seen all of them for a topic and level, the rest of the bank (seed, family sample bank, AptiSetu imports, the Claude-curated bank) follows. Items a faculty reviewer rejects are never served. AptiSetu imports (`data/aptisetu_bank.json`, built by `scripts/import_aptisetu.py`) carry their verification status from `data/aptisetu_curation/verified_ids.json` (each key independently re-solved); items on `data/aptisetu_curation/exclusions.json` stay in the bank with their reason but are not served until fixed, and duplicates, stem fixes and a seeded option shuffle are applied from the same folder on every re-import. Items not yet reviewed are labelled "faculty review pending".
- **CLAT Current Affairs & GK (verified bank only):** CLAT UG-style news passages (~300 words) on real events, with MCQs on the event and related static GK. Every seed question stores a `source_url` and an `as_of` date, and its facts were checked against that source. The generator has no web grounding, so this topic is **excluded from daily auto-generation** (`scripts/build_bank.py`) **and from live AI generation** (`engine.NO_AI_GENERATION_TOPICS`), instead of letting the model hallucinate current affairs. Refresh it by adding hand-verified seed questions with `source_url`/`as_of`.
- **Strict JSON + validation:** fence stripping, trailing-comma repair, A–D normalisation and key checks.
- **Pedagogical feedback:** the correct answer, the trap type of the main distractor (Extreme scope, Out-of-scope, Half-true, Reversal…), and a step-by-step explanation with the shortcut.
- **Error log + spaced repetition:** mistakes come back after 3 → 7 → 15 questions.
- **Weakness heatmap:** accuracy by topic × difficulty, a speed breakdown (on time / too slow / wrong), and the traps you fall for most.
- **Streaks & a daily micro-challenge** (cycles through the whole seed bank before repeating).
- **Freemium + Pro:** Free: 10 questions/day (counted by IST day; the daily challenge and mistake reviews are not counted); **Pro: ₹499/month or ₹999 for 3 months; Founding 500 offer: the first 500 paying users of each app get their first month for ₹199 (MRP ₹999)**: Unlimited verified practice + fresh questions added every day. For Pro, very fast repeated question requests (a script scraping the bank) trigger a 10-minute cooldown (logged in `abuse_events`, never an automatic ban), and only the most recent sign-in per app gets new questions; paid through Razorpay Payment Links. Each payment unlocks 30 days (90 on the 3-month plan); there is no auto-debit, so you pay again only if you want to continue (run `supabase/migrations/2026-10-27_pro_purchases.sql` and `supabase/migrations/2026-10-31_launch_offer.sql` once; until the second one is run the launch offer stays hidden) (no card data touches the app).
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
        │                           GEMINI_MODEL (optional) → gemini-3.6-flash (primary)
        │                           → fallbacks on error: 3.5-flash → 3-flash-preview
        │                             → 3.8-flash → 3.7-flash → flash-latest
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
├── bank.py                       # AI-bank storage, dedupe, serving pool
├── prompts.py                    # Prompt layer shared by app + scripts
├── scripts/                      # build_bank.py, export_review.py, apply_review.py, import_claude_bank.py
├── data/claude_bank_<family>.json  # Claude-curated verified bank per app (sources in data/claude_curation/)
├── review/ai_bank_review.csv     # faculty review sheet
├── data/ai_bank.json             # pre-generated verified questions
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

# the app itself never calls Gemini; GEMINI_API_KEY is only needed for scripts/build_bank.py

streamlit run app.py
```

## 🔐 Optional services setup
Every service is optional. If its secrets are missing, the app falls back: guest mode, session-only storage, "Pro coming soon".

| Feature | Secrets | Where |
|---|---|---|
| Daily bank building (`scripts/build_bank.py` only; the app does not use it) | `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |
| Google sign-in | `[auth]` block | Google Cloud Console → OAuth client (Web). Redirect URI: `https://<your-app>.streamlit.app/oauth2callback` |
| Saved progress | `PEPPER`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Supabase project → run [`supabase/schema.sql`](supabase/schema.sql) in the SQL editor |
| Pro payments | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `APP_URL` | Razorpay Dashboard → API Keys (test mode first) |

All keys are listed in [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example).

> ⚠️ `SUPABASE_SERVICE_KEY` is the service-role key. It stays server-side in Streamlit secrets and is never sent to the browser. RLS is enabled with no public policies, so the anon key can't read anything. Never change `PEPPER` after launch, because that would orphan every user's saved data.

Run the tests: `pip install pytest && pytest -q tests`

## 🏦 Question bank workflow (monthly refresh)
```bash
export GEMINI_API_KEY=...                                     # never commit it
python scripts/build_bank.py --per-cell 14 --rpm 8 --max-calls 450   # resumable; Ctrl-C safe
python scripts/export_review.py                               # -> review/ai_bank_review.csv
# faculty fills the `approve` column with Y / N (blank = leave unreviewed), optional review_note
python scripts/apply_review.py --reviewer "VG"                # writes decisions back into data/ai_bank.json
git add data/ai_bank.json && git commit -m "bank: monthly refresh"
```
- **Build:** each question gets the computed check (required for Quant and DILR; DILR also needs the uniqueness check) and an independent solve. Disagreements are rejected, and exact or near duplicates (normalised hash, 5-word-shingle Jaccard ≥ 0.6) are dropped. The bank is written after every accepted question, so a run can stop and resume. The script throttles to `--rpm`, backs off on 429/503, stops cleanly at `--max-calls` or a daily-quota error, and prints accepted/rejected/duplicate counts per topic.
- **Monthly refresh:** raise `--per-cell` (e.g. +5) and re-run. Only the missing items are generated, and the prompt is told what already exists so it writes different questions. Then export, review, apply, commit. Rejected items stay in the JSON (never served) so the reject decision is remembered.

## 🧠 Claude-curated verified bank

1,038 Claude-generated MCQs that passed an independent review (blind solve of every key, computed check of every
`verify_code`, option and format checks, and a duplicate check against all existing banks) are served as
`data/claude_bank_<family>.json`, one file per app:

| Family | Items | Topics |
|---|---|---|
| `mgmt_law` | 458 | CAT DILR 60 · CAT Quant 53 · CAT VARC RC 60 · CLAT Legal Reasoning 119 · CLAT Logical Reasoning 57 · IPMAT Quant 51 · IPMAT Verbal 58 |
| `sarkari` | 179 | Sarkari English 60 · Sarkari Quantitative Aptitude 59 · Sarkari Reasoning 60 |
| `cuet` | 401 | CUET English RC 60 · CUET English Verbal Ability 57 · CUET General Mental Ability 52 · CUET Logical & Analytical Reasoning 60 · CUET Maths Section A 57 · CUET Maths Section B1 60 · CUET Quantitative Reasoning 55 |

Each app loads only its own family's file (`bank.import_paths`), alongside the AptiSetu imports. Items show
"✅ Verified (independent solve[, computed])" with source "Claude curated bank". Scheduled AI questions are
still served first (freshest day first), and seen and excluded items are skipped as for every other bank.

The sources live in `data/claude_curation/` (verified questions, manifest, re-included additions, final
decisions and the full fixes record). Rebuild with `python3 -m scripts.import_claude_bank` (`--check` validates
without writing). Ids such as `CL-ML-CLLR-F5-007` come from each item's source position, so re-runs give
identical files and existing ids stay stable when items are added. To hold an item back, add its source to
`exclusions` in `data/claude_curation/decisions.json` and re-run.

## 🧩 One codebase, several apps (exam families)

Set `EXAM_FAMILY` in an app's Streamlit secrets (or env) to choose which app it runs as:

| `EXAM_FAMILY` | App | Status |
|---|---|---|
| `mgmt_law` (default) | CAT · CLAT · IPMAT | live |
| `sarkari` | SSC CGL/CHSL · Railway NTPC/Group D · Bank IBPS/SBI PO/Clerk | live |
| `cuet` | CUET UG: General Test · English · Maths | ready (see below) |
| `medical` | NEET UG | coming soon |
| `engineering` | JEE Main | coming soon |

Each app has its own branding, question bank (`data/sample_bank_<family>.json`), progress and Pro
(the Founding 500 ₹199 first month is counted per app and applies once per user per app). All apps share one Supabase project and one Razorpay
account. Run `supabase/migrations/2026-10-28_exam_families.sql` once before deploying a second app.

To deploy a new app: Streamlit Community Cloud → New app → same repo, branch `main`, file `app.py`, then
in Secrets paste the same keys as the existing app plus `EXAM_FAMILY = "sarkari"` and that app's own
`APP_URL`. Add the new app URL to the Google OAuth redirect URIs (`<APP_URL>/oauth2callback`, also set as
`redirect_uri` in its `[auth]` secrets) and to your Razorpay website/app details.

### 🎓 Deploying the CUET app

The CUET app ("CUET Adaptive Engine") is a separate Streamlit app from this same repo:

1. **Database (once):** in Supabase → SQL Editor run `supabase/migrations/2026-10-28_cuet_family.sql`
   (after `2026-10-28_exam_families.sql`). It adds `'cuet'` to the `pro_entitlements.exam_family` check so
   CUET Pro gets its own row. Until it runs, the CUET app works for practice but shows
   "Pro coming soon for this app (database setup pending)" and never shows a pay button.
2. **App:** Streamlit Community Cloud → New app → repo `Creator-hub24/cat-clat-adaptive-engine`, branch `main`,
   file `app.py`.
3. **Secrets:** paste the same secrets as the existing app (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `PEPPER`,
   `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `[auth]`), then set `EXAM_FAMILY = "cuet"`, this app's own
   `APP_URL`, and `redirect_uri = "<APP_URL>/oauth2callback"` in its `[auth]` block. Keep `PEPPER` identical
   so signed-in users map to the same account. `RAZORPAY_PAYMENT_LINK` (the static fallback link) is used
   only by the default app.
4. **Google OAuth:** add `<APP_URL>/oauth2callback` to the OAuth client's authorised redirect URIs.
5. **Razorpay:** same account and keys. Payment links carry `notes.exam_family = "cuet"` and the CUET app
   only accepts links with that note, so a payment in one app never unlocks another. Add the new app URL
   to your Razorpay website/app details.

**Question bank.** The CUET app serves its Claude-curated bank (401 items, see above) and `data/aptisetu_cuet_bank.json` (408 AptiSetu CUET MCQs; 407 served:
General Test 287, English 61, Maths 59). It is rebuilt from the AptiSetu source with
`python scripts/import_aptisetu.py <aptisetu>/data/cuet.json --family cuet`, which applies
`data/aptisetu_curation/cuet/`: verified ids (independent solve), the exclusion of one ambiguous item, 28
duplicate drops, fixes, and a seeded balanced option shuffle (items whose option order carries meaning
are never shuffled). HTML is converted to plain text, matrices are written `[a, b; c, d]`, and `|` is
written as `∣` so nothing can render as a table. To add AI questions offline (same verification
pipeline, never at runtime): `python scripts/build_bank.py --family cuet` (CUET General Knowledge is never
generated).

## ☁️ Deploy to Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **Create app** → repo `Creator-hub24/cat-clat-adaptive-engine`, branch `main`, file `app.py`.
3. **Advanced settings → Secrets:** paste the optional service secrets below. No `GEMINI_API_KEY` is needed: the app serves only the verified bank.
4. Deploy.

## 🧭 Roadmap
Mentor Meera's test builder, IRT-based adaptive sequencing. See [PRD.md §9](PRD.md#9-roadmap).

## 📄 License
MIT © 2026 Vaibhav Gupta
