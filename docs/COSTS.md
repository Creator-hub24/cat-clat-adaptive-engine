# Gemini API cost model (Pro)

_Estimates as of 2026-10-28. Prices are from the official page https://ai.google.dev/gemini-api/docs/pricing (fetched 2026-10-28, page "Last updated 2026-10-27 UTC"). Re-check before relying on these numbers._

## 1. What one verified AI question costs

### Calls per question
`llm.generate_verified` makes up to 2 attempts. Each attempt is:
1. **Writer call** (temperature 0.8). Input = `SYSTEM_PROMPT` + `build_prompt(topic, level, 3 examples)`. Output = question JSON (stem, options, explanation, verify_code).
2. Sandboxed `verify_code` for Quant (local, free).
3. **Independent solve** (temperature 0). Input = stem + options + `SOLVER_PROMPT`. Output = a small JSON.

### Models
`prompts.MODEL_CANDIDATES` is tried in order: `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3-flash-preview`, `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-flash-latest`. Later models are only used when the first one fails (404/429/5xx), so **`gemini-3.6-flash` is the cost basis**.

| Model | Input $/1M | Output $/1M (incl. thinking) | Source |
|---|---|---|---|
| gemini-3.6-flash (Standard) | 0.75 until 2026-12-31, **1.50 from 2027-01-01** | 3.75 until 2026-12-31, **7.50 from 2027-01-01** | pricing page |
| gemini-3.8-flash (Standard) | same as 3.6-flash | same as 3.6-flash | pricing page |
| gemini-3-flash-preview (Standard) | 0.50 | 3.00 | pricing page |
| gemini-3.5-flash, gemini-3.7-flash, gemini-flash-latest | **not clearly listed by name**; **assumed = gemini-3.6-flash** | assumed | assumption |

Batch/Flex tiers are about 50% cheaper, but they don't fit interactive serving. They could be used for the offline bank builder (`scripts/build_bank.py`).

### Token sizes
Measured from the actual prompts with the chars/4 rule:

| Piece | Chars | ≈ Tokens |
|---|---|---|
| `SYSTEM_PROMPT` | 1,373 | 340 |
| `build_prompt` for CAT Quant / VARC RC / CLAT Legal | 2,748 / 4,607 / 6,010 | 690 / 1,150 / 1,500 |
| Writer input (system + prompt), used in the model | | **~1,500** |
| Writer visible output (avg question JSON in the bank, 1,386 chars) | | **~450** |
| Solver input (stem + options + solver prompt; RC passages are longer) | | **~800** |
| Solver visible output | | ~40 |

**Thinking tokens are billed as output** and are the biggest unknown. Two scenarios:
- **Lean:** thinking is minimal or off (0 extra tokens).
- **Base:** 1,500 thinking tokens for the writer and 800 for the solver (assumption; measure with `usage_metadata` in production).

**Retries:** we assume 30% of questions need a second attempt, giving a ×1.3 multiplier (this also roughly covers fully failed generations). Prefetched questions that are thrown away when the user switches topic add a few percent.

### Result
FX assumption: **₹88 per US$** (please check the current rate).

| Scenario | US$/question | ₹/question |
|---|---|---|
| gemini-3.6-flash, 2026 prices, lean | 0.0046 | **0.41** |
| gemini-3.6-flash, 2026 prices, base | 0.0158 | **1.39** |
| gemini-3.6-flash, 2027 prices (2×), lean | 0.0093 | 0.82 |
| gemini-3.6-flash, 2027 prices (2×), base | 0.0317 | **2.79** |
| gemini-3-flash-preview, lean / base | 0.0034 / 0.0124 | 0.30 / 1.09 |

## 2. Cost per Pro user per month (30 days, AI questions actually served)

| Usage | AI q / month | 2026 lean | 2026 base | 2027 lean | 2027 base |
|---|---|---|---|---|---|
| Light: 20/day | 600 | ₹245 | ₹837 | ₹489 | ₹1,673 |
| Typical: 50/day | 1,500 | ₹611 | ₹2,091 | ₹1,223 | ₹4,183 |
| Heavy: 100/day (cap) | 3,000 | ₹1,223 | ₹4,183 | ₹2,445 | ₹8,366 |

Bank questions cost ₹0 in API usage.

## 3. Revenue vs cost

Razorpay standard domestic fee is a 2% platform fee plus 18% GST on that fee, i.e. **2.36%** (https://razorpay.com/pricing/, "Last updated: May 2026", fetched 2026-10-28).

| Plan | Price | Net after Razorpay | Margin, light (2026 lean / base) | Margin, typical (2026 lean / base) | Margin, heavy (2026 lean / base) |
|---|---|---|---|---|---|
| Intro month | ₹499 | ₹487 | ₹242 / −₹350 | −₹124 / −₹1,604 | −₹736 / −₹3,696 |
| Regular month | ₹999 | ₹975 | ₹730 / ₹138 | ₹364 / −₹1,116 | −₹248 / −₹3,208 |

Margins do **not** include GST payable on our own sales (18% if GST-registered, which would cut net revenue to ~₹827 of ₹999) or hosting/Supabase costs.

### Takeaways
- At the **₹999** price, only light usage is clearly profitable once thinking tokens are counted. A user hitting the 100/day cap costs ₹1.2k–₹4.2k a month at 2026 prices, and roughly double that from 2027-01-01.
- Options:
  - Lower the cap (e.g. 30–40 AI questions a day).
  - Turn thinking down/off for the writer (`thinking_config`) and the solver.
  - Serve more bank questions per AI question (prefetch every 2nd or 3rd question).
  - Use Batch pricing (−50%) to pre-generate a larger verified bank offline.
  - Put a cheaper model first for the independent solve (e.g. a Flash-Lite model, after checking its accuracy).
- Measure real `usage_metadata.prompt_token_count / candidates_token_count / thoughts_token_count` for a week before setting the final cap.

## 4. Free-tier limits and production key
- The free tier allows a small number of requests per model per day. The key on our build box hit **`GenerateRequestsPerDayPerProjectPerModel-FreeTier`: 20 requests/day/model** during the bank audit (2026-10-28).
- One verified question needs at least 2 requests (writer + solver), so a free key serves **~10 AI questions a day for the whole app**.
- Production needs a **billing-enabled (paid tier) key**. Free-tier content may also be used to improve Google's products; the paid tier's is not (per the pricing page).
- Set a monthly budget alert in Google Cloud Billing.

## 5. Provider comparison: Gemini vs Anthropic Claude vs xAI Grok

_Pricing sources, all fetched 2026-10-28:_
- Gemini: https://ai.google.dev/gemini-api/docs/pricing (as above)
- Anthropic: https://docs.anthropic.com/en/docs/about-claude/pricing
- xAI: https://docs.x.ai/docs/models (the "Text API Pricing" table)

All prices are standard (non-batch) rates per 1M tokens, for prompts under the long-context thresholds. Our prompts are under 2k tokens.

| Model | Input $/1M | Output $/1M | Notes |
|---|---|---|---|
| Claude Haiku 5.5 | 0.10 | 0.50 | Cheap/fast tier (≤100k-token prompts) |
| Claude Haiku 4.5 | 1.00 | 5.00 | Previous Haiku, for reference |
| Claude Sonnet 5.5 | 2.00 | 10.00 | Mid tier |
| Grok grok-4.3 | 1.25 | 2.50 | Cheapest listed general text model |
| Grok grok-4.20-0309-non-reasoning | 1.25 | 2.50 | No thinking, so only the "low" scenario applies |
| Grok grok-4.7 | 2.00 | 6.00 | Flagship |

### Model choices and pricing caveats
- **xAI:** the page does not list a "fast"/"mini" text model, so grok-4.3 and grok-4.20 non-reasoning are used as the cheap options.
- **Claude tokenizer:** the page says Claude 4.7+ models use a tokenizer that makes **~30% more tokens** for the same text. A ×1.3 token factor is applied to Haiku 5.5 and Sonnet 5.5; Haiku 4.5 uses the older tokenizer.

### Assumptions
Same as section 1:
- Writer call: 1,500 input / 450 output tokens. Solver call: 800 input / 40 output tokens.
- Thinking: low = 0; high = +1,500 (writer) and +800 (solver) tokens, billed as output.
- ×1.3 for retries, ₹88/US$.
- Margin = net revenue after Razorpay 2.36% (₹975.42 of ₹999, ₹487.22 of ₹499) minus API cost. GST on our own sales and hosting are not included.

Each cell shows low / high thinking.

| Model | $/q low / high | ₹/q low / high | ₹/mo 20/day | ₹/mo 30/day | ₹/mo 50/day | ₹/mo 100/day | Margin ₹999 @30/day | Margin ₹499 @30/day |
|---|---|---|---|---|---|---|---|---|
| Gemini gemini-3.6-flash (2026) | 0.0046 / 0.0158 | ₹0.41 / ₹1.39 | ₹245 / ₹837 | ₹367 / ₹1,255 | ₹611 / ₹2,091 | ₹1,223 / ₹4,183 | ₹609 / ₹-279 | ₹120 / ₹-768 |
| Gemini gemini-3.6-flash (from 2027-01-01) | 0.0093 / 0.0317 | ₹0.82 / ₹2.79 | ₹489 / ₹1,673 | ₹734 / ₹2,510 | ₹1,223 / ₹4,183 | ₹2,445 / ₹8,366 | ₹242 / ₹-1,534 | ₹-246 / ₹-2,022 |
| Gemini gemini-3-flash-preview | 0.0034 / 0.0124 | ₹0.30 / ₹1.09 | ₹180 / ₹653 | ₹270 / ₹980 | ₹450 / ₹1,634 | ₹899 / ₹3,267 | ₹706 / ₹-5 | ₹217 / ₹-493 |
| Claude Haiku 5.5 | 0.0008 / 0.0027 | ₹0.07 / ₹0.24 | ₹42 / ₹145 | ₹64 / ₹218 | ₹106 / ₹363 | ₹212 / ₹725 | ₹912 / ₹758 | ₹424 / ₹270 |
| Claude Sonnet 5.5 | 0.0161 / 0.0549 | ₹1.41 / ₹4.83 | ₹848 / ₹2,900 | ₹1,272 / ₹4,350 | ₹2,119 / ₹7,250 | ₹4,239 / ₹14,500 | ₹-296 / ₹-3,375 | ₹-784 / ₹-3,863 |
| Claude Haiku 4.5 | 0.0062 / 0.0211 | ₹0.54 / ₹1.86 | ₹326 / ₹1,115 | ₹489 / ₹1,673 | ₹815 / ₹2,789 | ₹1,630 / ₹5,577 | ₹486 / ₹-698 | ₹-2 / ₹-1,186 |
| Grok grok-4.3 | 0.0053 / 0.0128 | ₹0.47 / ₹1.13 | ₹281 / ₹676 | ₹422 / ₹1,014 | ₹704 / ₹1,690 | ₹1,407 / ₹3,381 | ₹553 / ₹-39 | ₹65 / ₹-527 |
| Grok grok-4.20-0309-non-reasoning (low only) | 0.0053 | ₹0.47 | ₹281 | ₹422 | ₹704 | ₹1,407 | ₹553 | ₹65 |
| Grok grok-4.7 | 0.0098 / 0.0277 | ₹0.86 / ₹2.44 | ₹518 / ₹1,465 | ₹776 / ₹2,197 | ₹1,294 / ₹3,662 | ₹2,588 / ₹7,324 | ₹199 / ₹-1,222 | ₹-289 / ₹-1,710 |

### Discounts that could apply
- **Batch API:** −50% at Anthropic (all models listed) and at Gemini. xAI says not every model accepts batch requests (see each model page). Batch is asynchronous, so it does not suit live serving or prefetch. It is useful for pre-generating a larger verified bank offline.
- **Prompt caching:**
  - Anthropic: cache reads cost 0.1× base input (0.05× on Sonnet 5.5) and 5-minute writes cost 1.25×.
  - xAI: lists cached-input prices (e.g. $0.20 vs $1.25 on grok-4.3).
  - The only shared prefix in our calls is `SYSTEM_PROMPT` (~340 tokens), which is below typical minimum cacheable lengths. Even if fully cached it would save <10% of input cost, and output (thinking) dominates our cost anyway. Caching is **not material** here unless the examples block is restructured into a stable prefix.

### Takeaways
- **Cheapest by far: Claude Haiku 5.5.** It costs about ₹0.07–₹0.24 per verified question, or ₹64–₹218 a month at 30/day and ₹212–₹725 at the 100/day cap. It is the only option that stays profitable at ₹999 (and ₹499) even for a user at the cap with heavy thinking.
- Next cheapest: gemini-3-flash-preview, then gemini-3.6-flash at 2026 prices, grok-4.3 and Claude Haiku 4.5. All of these are profitable at 30/day with low thinking but roughly break even or lose money with high thinking. Gemini gets worse after its 2027-01-01 price rise.
- Claude Sonnet 5.5 and grok-4.7 are too expensive for per-question generation at these prices. They could be used for the independent solve on a sample, or for offline bank building with Batch.

### Quality and feature caveats (not measured)
- **Price says nothing about quality.** Before switching, run `scripts/audit_bank.py`-style checks (verify_code pass rate, independent-solve agreement) on ~100 questions per candidate. A cheaper model with a lower verify pass rate raises the retry factor above 1.3.
- **Structured JSON:**
  - The app uses Gemini's JSON response mode (`response_mime_type` + schema).
  - Claude supports schema-constrained output through tool use / structured outputs. Tool use adds ~286–600 system-prompt tokens per request on the pricing page, which is small.
  - xAI documents structured outputs on its API.
  - Switching providers needs a new client in `llm.py`; this PR does not change the app code.
- **Rate limits:**
  - Anthropic uses usage tiers (Start/Build/Scale), and new accounts get only small free credits.
  - xAI limits are per model/team (see console).
  - Gemini free tier is 20 requests/day/model, as above.
  - All three need a paid key for production. Check the per-minute limits against the expected number of concurrent Pro users.
- Prices change often (Gemini has an announced increase on 2027-01-01). Re-fetch the three pages before deciding.
