# PRD: CAT/CLAT Adaptive Mock Test & Analytics Engine

| | |
|---|---|
| **Author** | Vaibhav Gupta (6 years CAT/CLAT faculty, Career Launcher) |
| **Status** | v0.3 prototype, live on Streamlit Cloud |
| **Last updated** | October 2026 |

---

## 1. Executive summary
A practice engine that writes CAT and CLAT questions the way a senior faculty member does. Every wrong option is a named trap, every explanation says why the tempting answer is wrong, and every mistake comes back on a spaced-repetition schedule. An LLM (Gemini Flash family, with automatic fallback between models) does the writing, and every AI answer key is checked before display. A pedagogical layer does the controlling: a difficulty rubric, a distractor taxonomy, topic rules and few-shot examples from a curated seed bank. That layer is the product's real value.

## 2. Problem statement
- **Coaching is expensive and hard to reach.** Classroom programmes cost ₹40k–₹1L+ and assume a fixed schedule. Working aspirants mostly practise alone, late at night.
- **Static test banks don't adapt.** A fixed PDF or mock series can't tell that a student keeps falling for "extreme scope" options, or understands remainders but not negative remainders.
- **Explanations are shallow.** Most solutions show how to get the right answer. They rarely say why option C looked right, and that is the lesson that actually raises the score.
- **Generic AI chatbots are not faculty.** Ask an LLM for a "CAT-level RC question" and you often get ambiguous keys, distractors that are obviously wrong, and difficulty that comes from ugly numbers instead of insight.

## 3. Target users
### Aspirant Arun (primary)
- 26, software engineer in Bengaluru, preparing for CAT 2026 while working full time.
- Has 45–60 minutes on weekday evenings and longer on weekends.
- Pain: he doesn't know *which* mistakes he repeats; full mocks take too long for weekdays.
- Needs: short, high-yield sets aimed at his weak spots, with explanations he can absorb in 2 minutes.

### Mentor Meera (secondary)
- 34, VARC and LR faculty at a mid-sized coaching centre, teaching 4 batches.
- Pain: writing original sectional tests with good distractors takes 6–8 hours a week.
- Needs: draft questions to a given topic and difficulty in seconds, with trap labels she can review, edit and reuse.

## 4. Core features (v0.1)
| # | Feature | Description | Status |
|---|---|---|---|
| F1 | Controlled question generation | Exam → section → difficulty (Easy / Moderate / CAT-Level). Structured prompt with a rubric, topic rules and retrieved few-shot examples; strict JSON output validated before display. | ✅ |
| F2 | Pedagogical feedback loop | After each answer: the correct key, the **trap type** of the main distractor, and a step-by-step coach's explanation including the shortcut. | ✅ |
| F3 | Error log + spaced repetition | Wrong answers enter a queue and come back after 3, 7 and 15 further questions, then graduate. | ✅ (saved when signed in) |
| F4 | Weakness heatmap | Accuracy % by topic × difficulty, plus a "traps you fall for most" chart. | ✅ |
| F5 | Streaks & daily micro-challenge | Correct-answer streak, plus one deterministic challenge question per day. | ✅ |
| F6 | Freemium meter | 10 AI questions per day free; the seed bank is always available. | ✅ (client-side) |
| F7 | Graceful offline mode | With no API key, or if the model fails, the app serves curated seed questions so the demo always works. | ✅ |
| F9 | Adaptive difficulty | Per-topic level; up after 2 consecutive on-time correct answers, down after 2 wrong; manual override. | ✅ v0.3 |
| F10 | Answer-key verification | Sandboxed `verify_code` for Quant/DILR, an independent solve pass for all sections, max 2 regenerations, then seed fallback; Verified badge; anonymous Report button. | ✅ v0.3 |
| F11 | Per-question timer | Difficulty-based targets, RC scaled by passage length; "Right but too slow" category. | ✅ v0.3 |
| F8 | Faculty test builder (Meera) | Batch-generate a 10–20 question sectional, edit it, export as PDF/CSV. | Roadmap |

## 5. Pedagogical rationale (the differentiator)
These are the rules a good faculty member follows without thinking. The system makes them explicit and enforces them on the model.

### 5.1 RC distractor taxonomy
Every wrong RC option the engine writes must belong to one named class, and the explanation must name it:

| Trap | What it does | Telltale signal | Example pattern |
|---|---|---|---|
| **Extreme scope** | Takes a moderate claim and makes it absolute | *always, only, most, never, all, proves* | Passage: "often in response to disputes" → Option: "disputes were the *only* cause" |
| **Out-of-scope** | Brings in a claim the passage never discusses, often one that sounds sensible | New entity, motive or policy not in the text | Passage uses roads as an analogy → Option: "spend less on roads" |
| **Half-true** | The first half matches the passage, the second half distorts it | A correct clause joined by "and/because" to a wrong one | "The coat was a necessary, *so the full contract price is payable*" |
| **Reversal** | Flips the author's direction, or confuses a conditional with its converse | Cause and effect swapped, concession read as rejection | "The objection has force, but…" read as "the author finds it baseless" |

Why it matters: aspirants don't fail RC because they can't read. They fail because they can't explain why an attractive option is wrong. Naming the trap gives the student a reusable check ("Is there an extreme word? Is this ever discussed?"), and the error log can then count the trap *type*, not just the question. That is what the heatmap's "traps you fall for most" chart shows.

### 5.2 Non-linear difficulty scaling in QA
Weak question banks make questions "harder" by using bigger numbers. Actual CAT difficulty grows non-linearly, through *insight*:

| Tier | What changes | Time target | Example (from seed bank) |
|---|---|---|---|
| Easy | One concept, direct application | < 60 s | Successive % change: +20% then −20% |
| Moderate | Two linked concepts, or one twist | 90–120 s | Time & work where one worker leaves early |
| CAT-Level | Needs an insight (negative remainder, invariant, factorisation trick). Brute force is possible but slow. | 2–3 min elegant / 6+ min brute | 7^2026 mod 50 via 7² ≡ −1; counting (x−6)(y−6)=36 |

Rules the prompt enforces:
1. Difficulty comes from the idea, not from arithmetic.
2. Every distractor is the result of a *specific, nameable* mistake (additive fallacy, wrong base, ordered vs unordered count), never a random number.
3. The explanation must state the fastest shortcut, because time is the hidden cost in CAT.

### 5.3 DILR set selection
In DILR, choosing which set to attempt matters as much as solving it. The engine's DILR rules:
- **Exactly one solution.** The explanation must show *why the other cases fail*. (The seed bank's arrangement item was rewritten once during authoring because the first draft allowed two arrangements, which is exactly the failure a validator has to catch.)
- **Reward global checks first:** points conservation in tournaments, parity, totals in tables. Students who build the grid before running these checks lose minutes.
- **Teach the selection signal:** the explanation tells the student how to spot, within 60 seconds, that a set is "doable", e.g. a fixed anchor (R in seat 3) or a closed total.

### 5.4 CLAT-specific rules
- The answer must follow *only* from the principle stated in the passage, never from outside legal knowledge.
- From Moderate upward, the principle includes an exception, because CLAT tests whether the student notices it (e.g. minor's contracts → necessaries → reasonable price only).
- Logical reasoning explanations use explicit tools: the negation test for assumptions, alternative causes for weakeners, the contrapositive for conditionals.

### 5.5 How the rules are enforced
1. **System prompt** sets the faculty persona and the non-negotiable output rules (4 options, one key, a named main trap, a shortcut).
2. **Difficulty rubric + topic rules** are injected for each request.
3. **Retrieval-grounded few-shot:** the 2 nearest seed questions (same topic, then same difficulty) are included as house-style references. ChromaDB is optional once the corpus grows beyond a few hundred items.
4. **Schema validation:** JSON is parsed with fence-stripping and trailing-comma repair, the keys are checked, the options are normalised to A–D, and the key must be one of them. On failure: one retry, then a fallback to the seed bank.

## 5A. Privacy by design
Aspirants are often students and working professionals who don't want their prep visible to an employer or institute, so trust is a feature.
- **Data minimisation:** the only identifier is `HMAC-SHA256(lowercased email, server pepper)`. Email, name and photo are never stored.
- **Stored fields:** attempts (question ID, topic, difficulty, correct, trap type, timestamp), streak, daily usage, review queue, plan and Pro expiry. Nothing else.
- **User control:** in-app JSON export and permanent deletion with confirmation.
- **Infrastructure:** Supabase with Row Level Security on and no public policies; the service key exists only server-side. Payments run on Razorpay's hosted page, so no card data reaches the app.
- **LLM processing:** Gemini receives only topic, difficulty and seed-bank examples, never user data.
- **Business model:** subscription only. No ads, no data selling.
- Full policy: [PRIVACY.md](PRIVACY.md).

## 6. Retention hooks
- **Streak counter** for consecutive correct answers, and best streak.
- **Daily micro-challenge:** one question a day, the same for everyone (date-seeded), which also makes it easy to share.
- **Weakness heatmap:** topic × difficulty accuracy, so the next session has an obvious target.
- **Spaced-repetition queue:** a "Reviews due" badge pulls the student back to old mistakes.
- Planned: weekly progress email, peer leaderboard on the daily challenge.

## 7. Unit economics
> ⚠️ **All numbers below are planning assumptions for a pre-launch product, not measured data.** They exist to show the model is viable and to say what must be true.

**Pricing:** Free tier = 10 AI questions/day + full seed bank. **Pro = ₹999/month** for unlimited adaptive mocks, full analytics history and the faculty test builder.

| Assumption | Value | Basis |
|---|---|---|
| ARPU (Pro) | ₹999 / month | List price; ignores annual discounts |
| Gross margin | ~85% | Gemini Flash cost per question is a fraction of a rupee; at ~600 questions/month per heavy user, inference + hosting ≈ ₹100–150 |
| Average paid lifetime | 6 months | CAT prep cycle is ~6–9 months; churn is mostly seasonal after the exam |
| LTV | 999 × 0.85 × 6 ≈ **₹5,100** | |
| Blended CAC | **≤ ₹1,500** | Mix of organic (YouTube/Telegram content from faculty, daily-challenge sharing) and paid Instagram/YouTube ads |
| **LTV : CAC** | **≈ 3.4 : 1** (target > 3 : 1) | |
| Free → Pro conversion | 3–5% | Typical consumer edtech freemium range |

What must hold for >3:1: CAC stays under ~₹1,700, *or* lifetime goes up (e.g. CAT + CLAT + GMAT bundles, or carrying over to the next year's attempt).

### 7.1 Monetisation implementation (v0.2)
- **Free:** 10 AI questions/day plus the unlimited seed bank. **Pro:** ₹999 for 30 days, unlimited AI questions.
- **Flow:** the app creates a per-user Razorpay Payment Link (`reference_id` = hashed user ID + timestamp). The user pays on Razorpay and clicks **"I've paid, verify"**. The server checks the link's status through the Razorpay API and extends `pro_until` by 30 days (stacking on any remaining time).
- **Next:** a Razorpay webhook for automatic activation, then Subscriptions for auto-renew.

### 7.2 B2B: Mentor plan
- **Target:** independent faculty and small coaching centres (Mentor Meera).
- **Offer:** a seat-based plan (indicative ₹4,999/month for 1 mentor + 50 students) with the sectional test builder, batch heatmaps and white-label PDF export.
- **Why it matters:** lower CAC (one sale brings many students), less seasonal churn (centres run batches all year), and a distribution channel into B2C Pro.
- **Privacy:** mentors see batch-level aggregates and students who opt in. Data stays keyed by hashed IDs.
- *Pricing is an assumption, to be validated with 5–10 centre interviews.*

## 8. Success metrics
| Category | Metric | v1 target |
|---|---|---|
| Activation | % of new users answering ≥5 questions in the first session | 60% |
| Engagement | Weekly active days per active user | ≥ 3 |
| Learning | Accuracy on spaced-review items vs first attempt | +25 pts |
| Quality | % of AI questions flagged by users as ambiguous/wrong key | < 3% |
| Retention | D7 / D30 retention | 35% / 15% |
| Revenue | Free → Pro conversion at 30 days | 4% |

## 9. Roadmap
- **v0.1 (shipped):** Streamlit prototype, 5 sections, seed bank, AI generation, session analytics.
- **v0.2 (shipped):** Optional Google sign-in, Supabase storage keyed by hashed IDs, data export/delete, server-side metering for signed-in users, Razorpay Pro.
- **v0.3 (shipped):** Adaptive per-topic difficulty, answer-key verification (sandboxed computation + independent solve), anonymous question reports, per-question timer with "Right but too slow", a 45-question seed bank, a daily challenge that cycles the whole bank, and review intervals 3 → 7 → 15.
- **v0.4:** Mentor Meera's test builder: batch generation, edit, PDF export, batch analytics.
- **v0.5:** Replace the 2-up/2-down rule with an Elo/IRT-style ability estimate per topic and full-length timed sectionals.
- **v1.0:** Payments (Razorpay), mobile-friendly frontend, a ChromaDB corpus of 1,000+ reviewed items.

## 10. Risks & mitigations
| Risk | Mitigation |
|---|---|
| LLM writes a wrong or ambiguous answer key (most likely in DILR/QA) | Schema validation, sandboxed verify_code, independent solve pass and an anonymous Report button (v0.3); faculty review of reported items next |
| Copyright: generating text close to real past papers | The prompt requires original passages; the seed bank is fully original; no past papers in the corpus |
| Freemium limit bypass | Signed-in users are metered server-side in Supabase; guest sessions are still client-side (accepted for the demo) |
| Data breach / privacy | Only hashed IDs + practice stats are stored; RLS on; service key server-side; export/delete in-app |
| Payment spoofing | Pro is granted only after a server-side Razorpay API check of the link status; no client-side trust |
| API cost spikes | Flash-tier model, daily caps, cached seed fallback |
| Seasonal churn after the exam | Bundle the next attempt and adjacent exams (CLAT → AILET, CAT → XAT/GMAT) |
