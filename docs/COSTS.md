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
