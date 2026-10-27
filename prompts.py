"""Prompt layer shared by the app and scripts/build_bank.py (no Streamlit import)."""
from __future__ import annotations

import json
import os

import engine

# Order verified live on 2026-10-26: 3.8-flash/3.7-flash returned 503 (high demand), 2.5-flash 404 for new keys.
# Free tier is 20 requests/day PER MODEL, so a longer list also stretches the daily quota.
MODEL_CANDIDATES = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3.8-flash",
                    "gemini-3.7-flash", "gemini-flash-latest"]


def model_candidates(custom: str | None = None) -> list[str]:
    """Optional pinned model first, then the fallback list (404/503/429 fall through)."""
    custom = custom or os.environ.get("GEMINI_MODEL")
    return ([custom] if custom else []) + [m for m in MODEL_CANDIDATES if m != custom]

import families  # noqa: E402

SECTIONS = families.FAMILIES[families.DEFAULT_FAMILY]["sections"]  # mgmt_law (default app)


def sections_for(family: str | None = None) -> dict:
    return families.get_family(family)["sections"]

DIFFICULTIES = engine.DIFFICULTIES

DIFFICULTY_RUBRIC = {
    "Easy": "Single concept, one or two steps, direct application. A prepared aspirant should solve it in under 60 seconds.",
    "Moderate": "Two linked concepts or one concept with a twist; 90-120 seconds. Distractors reflect the most common procedural slip.",
    "CAT-Level": "Non-linear jump: needs an insight (a symmetry, a negative remainder, an invariant, a premise attack) rather than more computation. Brute force should be possible but slow; the elegant path takes 2-3 minutes. Distractors must be the answers a strong but hasty solver would actually get.",
}

TOPIC_RULES = {
    "CAT Quant": "verify_code is REQUIRED. Use clean integers. Every distractor must be the result of a specific, nameable mistake (e.g. additive fallacy, wrong base, ordered vs unordered). Mention the fastest shortcut.",
    "CAT VARC RC": "Write an ORIGINAL 120-220 word passage (no copyrighted text) followed by one question. Distractors must follow the taxonomy: Extreme scope, Out-of-scope, Half-true, Reversal. Label the trap type of each wrong option in the explanation.",
    "CAT DILR": "Write a small self-contained set (arrangement, tournament, scheduling or table). It MUST have exactly one solution; verify uniqueness in the explanation by showing why other cases fail. Prefer sets that reward a global check (conservation, parity) before grid-building. When the set needs data, present it as a GitHub-markdown table inside question_text. Where the answer is computable, include verify_code.",
    "CLAT RC": "Write an ORIGINAL legal-principle passage (100-200 words) and a fact situation. The answer must follow ONLY from the stated principle, not outside legal knowledge. Include an exception in the principle at Moderate+.",
    "CLAT Legal Reasoning": "CLAT UG style: write an ORIGINAL passage (about 350-450 words) that states one or more legal principles or rules (with an exception or condition at Moderate+), followed by a short fact situation and one question. The answer must follow STRICTLY from the stated principle, never from outside legal knowledge or general morality. Vary the area (contract, tort, criminal law, constitutional law/fundamental rights, consumer law, IPR). Distractors must be realistic traps: applying general morality or fairness, ignoring the exception or one of several conditions, reversing the principle, or importing an outside rule. Name the trap behind each wrong option in the explanation.",
    "CLAT Logical Reasoning": "Argument-based (assumption, strengthen/weaken, inference, conditional logic). Use the negation test or contrapositive in the explanation.",
    "CLAT Current Affairs & GK": "CLAT UG style: a 300-400 word news-based passage about ONE real, verifiable event, then an MCQ on the event or related static GK. EVERY fact (in the passage, options and explanation) must come from a source you can cite. Output a 'source_url' (a public page stating the facts) and an 'as_of' date (YYYY-MM-DD). No invented names, numbers or dates; if you cannot ground a fact, do not write the question. NOTE: this topic is excluded from live/auto generation (engine.NO_AI_GENERATION_TOPICS) because the generator has no web grounding; seed questions are hand-verified.",
    "IPMAT Quant": "IPMAT (IIM Indore/Rohtak) Class 11-12 level MCQ: algebra, AP/GP, logarithms, P&C, probability, coordinate geometry, number theory. verify_code is REQUIRED. Use clean integers or simple fractions. Every distractor must come from a specific, nameable mistake. Mention the fastest shortcut.",
    "Sarkari Quantitative Aptitude": "SSC CGL/CHSL, RRB NTPC/Group D and IBPS/SBI PO/Clerk level arithmetic MCQ: percentages, profit & loss, SI/CI, ratio, averages, time & work, pipes, time-speed-distance, mensuration, simplification. verify_code is REQUIRED. Clean numbers solvable in 30-90 seconds. Every distractor must come from a specific, nameable mistake. Mention the fastest shortcut.",
    "Sarkari Reasoning": "SSC/Railway/Bank reasoning MCQ: coding-decoding, series, analogy, blood relations, directions, syllogisms, seating, inequalities. Exactly one defensible answer; for syllogisms use only the given statements. Name the trap behind each wrong option.",
    "Sarkari English": "SSC/Bank English MCQ: synonyms/antonyms, idioms, fill in the blank, error spotting, sentence improvement, cloze. Standard Indian-exam grammar rules; exactly one defensible answer; state the rule in the explanation.",
    "Sarkari General Awareness": "Static GK / current affairs for SSC, Railway and Bank exams. EVERY fact must come from a source you can cite: output 'source_url' and 'as_of' (YYYY-MM-DD). NOTE: excluded from live/auto generation (engine.NO_AI_GENERATION_TOPICS); items are hand-added and verified only.",
    "IPMAT Verbal": "IPMAT verbal ability MCQ: vocabulary in context, grammar/sentence correction, idioms, para-completion, or a short ORIGINAL passage (80-150 words) with an inference/assumption question. Exactly one defensible answer; name the trap behind each wrong option in the explanation.",
}

SYSTEM_PROMPT = """You are a master CAT/CLAT faculty member with 10+ years of classroom coaching.
You write ORIGINAL exam-grade questions (never copy past papers) and you teach through the explanation.
Pedagogical constraints you must obey:
1. Exactly 4 options keyed A, B, C, D, exactly one correct.
2. Every wrong option is a deliberate, realistic trap; the most tempting one is the 'main distractor'.
3. The explanation must (a) solve step by step, (b) name the shortcut or reading signal, (c) explain why the main distractor is wrong and what thinking error produces it.
4. Match the difficulty rubric exactly; difficulty comes from insight, not ugly numbers.
5. Output ONLY one JSON object, no markdown fences, with keys:
   question_text (string), options (object with keys A,B,C,D), correct_answer (one of A,B,C,D),
   pedagogical_explanation (string), trap_type (string, the main distractor's trap), concept_tag (string),
   and for computable questions (Quant, numeric/arrangement DILR) verify_code (string).
6. verify_code: short plain Python that computes the answer and assigns it to a variable named `answer`
   (a number equal to the correct option's value, or the correct option letter). Only math, itertools and
   fractions may be imported. No input, files, network or printing needed.
7. Tabular data must be written as a markdown table inside question_text. Never use HTML."""

REQUIRED_KEYS = engine.REQUIRED_KEYS


def retrieve_examples(bank: list[dict], topic: str, difficulty: str, k: int = 2) -> list[dict]:
    """Simple lexical retrieval: same topic first (same difficulty ranked higher), then same exam."""
    exam = topic.split()[0]
    def score(q):
        return (q["topic"] == topic) * 2 + (q["difficulty"] == difficulty) + (q["exam"] == exam) * 0.5
    ranked = sorted(bank, key=score, reverse=True)
    return [q for q in ranked if score(q) > 0][:k]


def build_prompt(topic: str, difficulty: str, examples: list[dict], avoid: list[str] | None = None) -> str:
    shots = "\n\n".join(
        json.dumps({k: ex[k] for k in list(REQUIRED_KEYS) + ["verify_code"] if k in ex}, ensure_ascii=False)
        for ex in examples
    )
    return f"""Topic: {topic}
Difficulty: {difficulty}
Difficulty rubric: {DIFFICULTY_RUBRIC[difficulty]}
Topic rules: {TOPIC_RULES[topic]}

Reference examples of house style (do NOT reuse their content, numbers or passages):
{shots}

{avoid_block(avoid)}Now write ONE new question as a single JSON object."""


def avoid_block(avoid: list[str] | None) -> str:
    if not avoid:
        return ""
    lines = "\n".join(f"- {a}" for a in avoid[-15:])
    return f"Already in the bank (write something clearly DIFFERENT in concept, numbers and setting):\n{lines}\n\n"


