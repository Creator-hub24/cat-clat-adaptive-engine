# Multi-model Sarkari curation record

## Scope

Independently verified Sarkari MCQs from:

- Gemini Argon 4.0 batches 1–6 (Quant Easy/Moderate, Reasoning Easy/Moderate, English Easy/Moderate)
- Model-comparison Quant Moderate runs: Meta AI, Claude Sonnet 5, Claude Sonnet 5.5 Medium, SuperGrok, ChatGPT Go

The Gemini compare file (`compare_gemini_passing.json`) was **not** imported: it duplicates batch 4a+4b.

## Verification

Every item was blind-solved, run through `engine.run_verify_code` + `answer_matches_key`, trap-checked, and house-validated with `import_claude_bank.validate(q, "sarkari")` before landing in a `*_passing.json` file. FIX items had VC/trap/Easy-relabel repairs applied in those passing files.

## Cross-dedupe

Candidates (162) were compared with SequenceMatcher ≥ 0.80 against the existing app banks (seed, AI, AptiSetu, Claude) and against earlier candidates. **11 dropped** (see `decisions.json` → `cross_dedupe_drops`). **151 kept.**

## Option shuffle

On every import, each item gets a seeded per-item option shuffle (`seed = multi-model-sarkari-2026-11-01`). Remaps `correct_answer`, `Trap (X)` / `Option X` in explanations, and letter keys inside `verify_code` (`OPTS` / `answer = 'X'`). Re-run is byte-stable.

## Faculty flags

Listed in `decisions.json` → `faculty_flags` (convention notes and sight-check requests). None are hard exclusions in this import.

## Ids

`MM-SK-<topic>-<batchcode>-<index>` e.g. `MM-SK-SQA-GB1-003`, `MM-SK-SQA-C55-002`.

## Meta AI Hard Quant batches (meta_hard_p1 / meta_hard_p2)

20 Meta AI Sarkari Quant items submitted as "Hard" (manifest n=151–170, sources `meta-hard-p1 #0..9` / `meta-hard-p2 #0..9`, ids `MM-SK-SQA-MH1-*` / `MM-SK-SQA-MH2-*`).

- All 20 answer keys were correct on blind solve. 18/20 needed repairs: most traps were rebuilt from real slips, hard-coded `verify_code` was rewritten to compute the answer, and wording was tightened. The p1 wrong-number series (#2) was rebuilt.
- Difficulty relabels: 12 of 20 moved down (see `decisions.json` → `difficulty_relabels`). Final mix: **8 CAT-Level, 9 Moderate, 3 Easy**.
- `meta-hard-p2 #2` (quadratic comparison) and `#9` (data sufficiency) return option **text** from `verify_code`, so the seeded shuffle cannot desync the key. All 20 were checked against every one of the 24 option permutations.
- Re-deduped at ≥ 0.80 against seed + AI + AptiSetu + sample + Claude banks + the existing multi-model bank (2296 items): max similarity 0.731, **0 dropped**.
- Faculty flags are added to `decisions.json` → `faculty_flags`.

## Gemini batches 8–9 and Meta AI English/Reasoning batches (2026-11-02)

74 items appended (manifest n=171–244). Index is the item's position in the original source file, so dropped items leave gaps.

| Source | Model | Topic | Code | Items | Difficulty |
|---|---|---|---|---:|---|
| `batch-8 #i` | Gemini Argon 4.0 | Sarkari Reasoning | GB8 | 18 | 15 Moderate, 3 Easy |
| `batch-9 #i` | Gemini Argon 4.0 | Sarkari English | GB9 | 19 | 17 Moderate, 2 CAT-Level |
| `meta-eng-p1 #i` / `meta-eng-p2 #i` | Meta AI | Sarkari English | ME1 / ME2 | 8 + 10 | 9 Moderate, 9 Easy |
| `meta-rea-p1 #i` / `meta-rea-p2 #i` | Meta AI | Sarkari Reasoning | MR1 / MR2 | 10 + 9 | 8 Moderate, 11 Easy |

- Every key was checked by blind solve; batch-8 #1 had a wrong key and was repaired, broken seating clues were rebuilt, hard-coded `verify_code` was replaced with computing checks (option text or an `OPTS` map), and CAPITALS underlines were moved to the house `**...**` style. Each item survives all 24 option orders under the importer shuffle.
- Dropped during verification: `batch-9 #11` (bank duplicate, "throw down the gauntlet"), `meta-eng-p1 #1` and `#2` (bank duplicates of CL-SK-SEN-F1-144 / -172), `meta-rea-p2 #6` (odd one out with no single-mistake distractors). `batch-8 #6` was held at 0.817 against MM-SK-SRE-GB2-017.
- Re-deduped at ≥ 0.80 against seed + AI + AptiSetu + sample + Claude banks + the existing multi-model bank (2397 items) and pairwise within the 75 candidates. Max against the bank 0.782 (batch-8 #5 vs MM-SK-SRE-GB5-008). Within the candidates `batch-8 #8` scored 0.914 against `batch-8 #7` (same inequality template) and was **dropped**; the earlier item was kept.
- Difficulty relabels and faculty flags are in `decisions.json` (`difficulty_relabels`, `faculty_flags`); the summary block is `gemini_meta_sarkari_import_2026_11_02`.

