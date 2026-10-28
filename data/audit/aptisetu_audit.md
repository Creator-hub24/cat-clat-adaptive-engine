# AptiSetu bank audit (read-only)

Nothing in the bank was changed. Items listed here need human review.

- LLM pass: partial: 8/494 solved; resume with --llm (already-solved items are skipped)
- checked: 494
- static errors: 2
- static warnings: 0
- numeric mismatch: 3
- llm solved: 8
- llm errors: 0
- llm disagreements: 0
- llm ambiguous: 0
- flagged: 3

## Disagreements / issues

| id | topic | stem (last 160 chars) | key | solver | reason |
|---|---|---|---|---|---|
| AS-QA-CQ106 | CAT Quant | Two circles of radii 7 cm and 1 cm have their centres 10 cm apart. What is the length of a direct (outer) common tangent? | A | B | error: explanation concludes 6, which is option B, but key is A (8 cm); explanation's final number 6 matches option B |
| AS-QA-CQ126 | CAT Quant | The HCF of two numbers is 12 and their LCM is 720. How many such pairs of numbers exist? (Treat (a, b) and (b, a) as the same pair.) | A | C | error: explanation concludes 8, which is option C, but key is A (4); explanation's final number 8 matches option C |
| AS-QA-CQ155 | CAT Quant | The line 3x + 4y = 24 forms a triangle with the coordinate axes. What is the distance of the incentre of this triangle from the origin? | B | A | explanation's final number 2 matches option A |
