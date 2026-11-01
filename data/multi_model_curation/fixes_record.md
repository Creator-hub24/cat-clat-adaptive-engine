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
