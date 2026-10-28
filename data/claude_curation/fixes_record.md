# Curation record (all decisions final)

The fixes below are applied in verified_questions.json, except the File 1 option fixes and the File 5 retag, which scripts/import_claude_bank.py applies from decisions.json on every run.

## File 1
- #25: dropped (near-duplicate of AS-CU-QR-G-Q141). Decision stands.
- #62: option C changed from 72 to 99 (key A = 90); item included (additions.json + decisions.json).
- #138: option D changed from 'over' to 'against' (key B = 'to'); item included (additions.json + decisions.json).
- File-1 trap fixes (#18 D, #49 C, #119 C, #175 D, #198 B) are already applied in clean_passing.json.

## File 2: applied
- #9: Trap (C): 12 adds the two divisors (7 + 5) instead of working out 7 × 2 + 3 = 17.
- #28: Trap (D): 7 cm divides r³ by r² (343 ÷ 49), dropping the 4/3 and using the sphere's radius instead of the vessel's.
- #33: Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #35: Trap (B): 13 counts the 16 multiples of 3 and removes the 3 multiples of 15, but forgets to add the 10 multiples of 5.
- #54: Trap (C): 5 counts ABD, ADC and ABC and then counts ABD and ADC a second time.
- #55: Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #66: Trap (A): 27th adds 2 days to the last Monday (25th) instead of 4, which gives a Wednesday. | Trap (D): 30th adds 2 days to the last Thursday (28th) instead of 1, which gives a Saturday. | Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #68: Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #69: Trap (C): 7 km adds the 4 km north leg to the 3 km east leg instead of letting the north and south legs cancel. | Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #78: Trap (B): 100 adds 48 instead of the doubled gap 56 (gaps 7, 14, 28, 56). | Trap (D): 112 adds 60 instead of the doubled gap 56.
- #87: Trap (D): 11 counts only the 6 single cells, the 4 side-by-side pairs and the whole rectangle.
- #90: Trap (A): 871469 swaps the codes of L and E at the end. | Trap (C): 871946 swaps the codes of B and L.
- #99: Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #106: Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #110: Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #120: Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #146: Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #156: Append to verify_code: OPTS = <options>; answer = [k for k, v in OPTS.items() if v == answer][0]  (re-tested: matches key)
- #171: Trap (B): the writer blames a mistaken belief and gives advice calmly; there is no anger or scorn towards the students.
- #134 (not applied): reword the stem sentence to 'Each person either always tells the truth or always lies.'
- RC spacing (not applied): collapse double spaces in #163, 165–167, 169, 173, 176, 178, 179.

## File 2: near-duplicate fails (excluded; restructure or drop)
- #1: Near-duplicate of AS-QA-CQ89: same numbers (two items at ₹1,200, +20%/-20%), same question.
- #6: Near-duplicate of AS-CU-QR-G-Q31: same fill+drain template, numbers swapped (6/9 h -> 10/15 h); same rule that dropped file-1 #25.
- #7: Near-duplicate of file-1 #53: same usual-time template, numbers swapped (4/5, 20 min -> 5/6, 15 min).
- #17: Near-duplicate of file-1 #46: same SI multiple-of-sum template, numbers swapped.
- #32: Near-duplicate of file-1 #52: identical data (A+B 12, B+C 15, C+A 20); only asks A alone instead of all three.
- #40: Near-duplicate of AS-CU-GMA-UG62: identical series 2, 6, 12, 20, 30, ? (answer 42).
- #60: Near-duplicate of file-1 #81: same series 3, 4, 8, 17, 33 extended by one term; file-1 answer 58 is printed in this stem.
- #61: Near-duplicate of AS-CU-GMA-G-R33: same series 3, 5, 9, 17, 33 with a 2 prepended; same answer 65.
- #63: Near-duplicate of AS-CU-GMA-G-R34: identical letter series A, C, F, J, O, ?.
- #70: Near-duplicate of AS-CU-GMA-G-R30: identical scenario (morning, shadow to the right, facing south).
- #82: Near-duplicate of AS-QA-CQ141: same right-angle count question for 12 h instead of 24 h (22 vs 44; 44 is even an option).
- #85: Near-duplicate of file-1 #66: same row-exchange template, numbers swapped.
- #89: Near-duplicate of file-1 #105: identical series 5, 6, 14, 45, 184, ? (answer 925).

## File 3

### Applied trap fixes (already in verified_questions.json)

- file-3 #86: Trap (D): 4e uses (2x + 2)eˣ, adding 2 instead of x², which gives 4e at x = 1.
- file-3 #93: Trap (A): 0 uses the limits 0 and π, over which the positive and negative areas of cos x cancel.
- file-3 #95: Trap (B): 7 uses y = 2x + 1, adding the constant to dy/dx instead of integrating.
- file-3 #99: Trap (A): 2 reads off the constant of the second equation, x - y = 2, instead of applying Cramer's rule.
- file-3 #101: Trap (C): -6 takes -(3 × 2), the product of the off-diagonal entries, as the product of the roots.
- file-3 #102: Trap (A): 1 gives the determinant ∣A∣ = 6 - 5 instead of the sum of the entries of A⁻¹.
- file-3 #102: Trap (C): 10 adds the entries 3, 5 and 2 of A and leaves out the entry 1.
- file-3 #106: Trap (C): 16 gives the numerator of 16/x instead of the minimum value.
- file-3 #109: Trap (D): ln(3/2) evaluates only the 1/(x + 1) part and drops its minus sign.
- file-3 #117: Trap (D): 5/36 uses (1/6) × (5/6), one six and one non-six, without the other factors.
- file-3 #118: Trap (C): 26 evaluates Z at (6, 2), on the line x + y = 6, which is not the minimising corner.
- file-3 #119: Trap (D): 3/2 divides the sum of the values 1 + 2 + 3 by 4 instead of weighting by the probabilities.
- file-3 #128: Trap (D): 8π uses the correct r² = 8 but takes the height as 3 (the radius) instead of 4.
- file-3 #152: Trap (A): 2 solves 2k = 3 + 1, adding 1 instead of subtracting it.
- file-3 #163: Trap (C): π/4 drops the sign of tan⁻¹(-1) = -π/4 instead of adding π.
- file-3 #164: Trap (C): 7/25 gives the size of cos 2θ = -7/25 and drops its sign; the question asks for sin 2θ.
- file-3 #169: Trap (B): 1 multiplies only the main-diagonal entries 1 × 1 × 1 and ignores the other terms of the determinant.
- file-3 #169: Trap (D): 3 adds the main-diagonal entries 1 + 1 + 1 instead of computing the determinant.
- file-3 #172: Trap (A): 8 adds t = 2 to the coordinate sum 6 instead of adding 2 × (2 + 1 + 2).
- file-3 #177: Trap (C): 1/2 gives P(not A) only and forgets to multiply by P(not B) = 2/3.
- file-3 #190: Trap (B): 5/9 uses 3 instead of √3 for the magnitude of the normal (1, 1, 1).

### Near-duplicate fails (excluded; rebuild with a different structure if wanted)

- file-3 #24: Near-duplicate of file-1 #121: same ANCIENT antonym item; three of four options repeated (modern/old/historic).
- file-3 #30: Near-duplicate of AS-CU-VA-UE51: same GENEROUS antonym item; distractors wealthy/polite/kind repeated, key miserly -> stingy.
- file-3 #43: Near-duplicate of file-1 #141: same VERBOSE antonym item; key concise and distractor talkative repeated.
- file-3 #85: Near-duplicate of AS-CU-MA-UM31: identical question (3 × 3, ∣A∣ = 4, find ∣adj A∣; answer 16).
- file-3 #112: Near-duplicate of AS-CU-MA-UM13: same differential equation with only the exponent of dy/dx changed (4 -> 2); asks order + degree instead of order and degree.
- file-3 #113: Near-duplicate of AS-CU-MA-UM14: identical question (dy/dx = y/x, y(1) = 2, y at x = 3; answer 6).

### Soft note
- file-3 #20: "team of players ___" accepts "are" in British usage; consider a strictly singular subject.

## File 4 (batches 31-40: CAT Quant, CAT DILR, CAT VARC, CLAT RC)

Status: 193 of 200 pass; 7 near-duplicate fails. Fixes below are already applied in verified_questions.json.

### Applied fixes (trap explanations and verify_code)

- file-4 #11: Trap (A): 3 rounds 360/140 ≈ 2.57 up to 3, treating 140° as the angle at the centre.
- file-4 #53: Trap (C): 990 multiplies 99 numbers by an assumed average digit sum of 10 instead of adding the digits place by place.
- file-4 #55: Trap (B): 15 removes only one number from each of the five chains k, k + 5, k + 10, k + 15, which still leaves pairs 5 apart.
- file-4 #55: Trap (C): 8 takes two numbers from only four of the five chains and forgets the fifth chain.
- file-4 #68: Trap (A): 6 forgets to take the three ₹5 coins out of the coin count and solves x + y = 12, x + 2y = 18.
- file-4 #71: Trap (D): 2021 to 2022 rose by 11 on a base of 110, only 10%; choosing it means comparing rises without dividing by the base.
- file-4 #105: Trap (C): 48 treats the ring as a straight line (3 × 2 × 2 × 2 × 2) and forgets the 4 choices for the fountain.
- file-4 #107: verify_code: replace bin(mask).count('1') with sum(mask >> b & 1 for b in range(5)); patched code returns A.
- file-4 #107: Trap (C): pressing every lamp once leaves lamps 1, 2, 4 and 5 on, so it does not switch all lamps off.

### Near-duplicate fails (excluded; rebuild with a different structure if wanted)

- file-4 #6: Near-duplicate of AS-CU-QR-UG26: identical question (tangent from a point 13 cm from the centre, r = 5; answer 12).
- file-4 #16: Near-duplicate of file-2 #73: same count-the-squares template with the grid size swapped (3 × 3 -> 4 × 4).
- file-4 #18: Near-duplicate of AS-CU-QR-UG29: same median list with one value removed.
- file-4 #19: Near-duplicate of file-1 #187: same sum-of-first-n-odd-numbers template with n swapped (20 -> 30).
- file-4 #21: Near-duplicate of AS-QA-CQ74: same concentric-circle chord problem with the same numbers (chord 24, r = 5, answer 13).
- file-4 #34: Near-duplicate of AS-QA-CQ77 / AS-QA-M4-QA-20: same "no two identical letters together" template with the word swapped (BANANA/BALLOON -> MISSISSIPPI).
- file-4 #50: Near-duplicate of AS-QA-M2-QA-18: same count-perfect-square-divisors template with the number swapped (10800 -> 10!).

### Tagging note
- file-4 #180-199 (batch 40): tagged topic "CLAT RC" but each item is a legal principle + facts question (Legal Reasoning style). Answers follow from the stated principle only. Retagged to CLAT Legal Reasoning (see File 5).


## File 5 (batches 41-54: CLAT RC, CLAT Legal, CLAT Logical, IPMAT Quant, IPMAT Verbal)

Status: 265 of 280 pass; 15 near-duplicate fails; 0 ambiguous. Blind solve agrees with every key. Fixes below are already applied in verified_questions.json.

### Retag applied (decision made)
- file-4 #180-199 (batch 40, 20 items): topic changed from "CLAT RC" to "CLAT Legal Reasoning" in verified_questions.json.

### Applied fixes (verify_code, format, trap explanations)

- file-5 #159: verify_code: compute 30 and match it against numeric opts {A: 10, B: 30, C: 60, D: 70}; patched code returns B.
- file-5 #166: Trap (C): 6 counts only the divisors that are multiples of 4 (4, 8, 12, 24, 36, 72) and misses those with a single factor 2.
- file-5 #172: Trap (D): 23 adds 3 to f(2) to get 10 and then applies f, giving f(10) = 23.
- file-5 #189: Trap (D): 38 adds 3 for each of the 9 steps from x = 1 to x = 10 but starts from f(3) = 11 instead of f(1) = 5 (11 + 27).
- file-5 #199: Trap (D): 20 divides by 15 instead of 25 in the second step: 75/5 + 75/15 = 15 + 5.
- file-5 #200: Trap (C): 4 counts the divisors of 45 that are at most 9 (1, 3, 5, 9) instead of the factor pairs d × e with d < e.
- file-5 #200: Trap (D): 5 counts the divisors of 45 other than 45 itself (1, 3, 5, 9, 15).
- file-5 #203: Format: Option D changed from 30 to 24 so that its trap ("only partitions with distinct parts") produces the value; verify_code opts updated; key C unchanged.
- file-5 #203: Trap (D): 24 counts only the partitions with three different parts (33 minus the 9 with two equal parts).
- file-5 #205: Trap (C): 4999 rounds 7! to 5000 and then subtracts 1.
- file-5 #210: Trap (D): 45 counts the triples in which one particular variable exceeds 9 and reports that count, not the number left.
- file-5 #215: Trap (C): 1/2 adds the chance 1/6 for only three of the six letters (3 × 1/6).
- file-5 #217: Trap (C): 3 doubles the plain geometric sum 3/2, taking the average weight of the terms as 2.
- file-5 #221: Format: Stem said "underlined word" but nothing is underlined; now "word in bold" with **ephemeral**.
- file-5 #237: Format: Stem said "underlined word" but nothing is underlined; now "word in bold" with **scepticism**.
- file-5 #250: Format: Option letters did not match the error-segment labels (B->(C), C->(D), D->(B)); segment labels changed to (P)-(S) and options relabelled so the error part (Q) stays at key D; explanation updated.
- file-5 #264: Format: Option A lacked the final period; added for parallel form.
- file-5 #265: Format: Stem said "underlined word" but nothing is underlined; now "word in bold" with **enervate**.

### Near-duplicate fails (excluded; rebuild with a different structure if wanted)

- file-5 #67: Near-duplicate of file-5 #3: same fact pattern as #3 (spreading fire; a neighbour demolishes or breaks into a structure in its path to stop it), same necessity outcome; only the branch of law (tort vs criminal) differs.
- file-5 #103: Near-duplicate of file-2 #112: same contrapositive template with the words swapped (rain/match cancelled -> train late/meeting postponed).
- file-5 #151: Near-duplicate of file-2 #134: identical liar puzzle (A says B lies, B says C lies, C says A and B both lie) with names swapped.
- file-5 #155: Near-duplicate of file-4 #73: identical "exactly one statement true" puzzle (X: "Y did it", Y: "I did not", Z: "X is lying") with names swapped.
- file-5 #167: Near-duplicate of AS-CU-QR-G-Q116 / AS-CU-QR-G-Q46: same sum-of-squares-of-roots template with the quadratic swapped.
- file-5 #173: Near-duplicate of AS-CU-QR-G-Q114: same unit-digit-of-a-power template with the numbers swapped (8^35 -> 7^45).
- file-5 #174: Near-duplicate of file-3 #80: same 2 × 2 determinant template with the numbers swapped.
- file-5 #177: Near-duplicate of file-3 #106: same AM-GM minimum of t + k/t template with the numbers swapped (t = x²).
- file-5 #179: Near-duplicate of AS-CU-MA-UM5: same triangle-area template (two vertices on the x-axis) with the numbers swapped.
- file-5 #193: Near-duplicate of AS-CU-QR-G-Q39 / AS-QA-CQ69: same remainder-of-a-power template with the numbers swapped.
- file-5 #201: Near-duplicate of AS-QA-CQ109: same "last two digits of a power of 7" template with the exponent swapped (42 -> 2024).
- file-5 #207: Near-duplicate of file-4 #51: identical reflection shortest-path problem (A(1, 2), B(7, 4), x-axis; answer 6√2).
- file-5 #214: Near-duplicate of file-4 #30: identical question (f(0) = 0, f(n + 1) = f(n) + 2n + 1, find f(10); answer 100).
- file-5 #223: Near-duplicate of file-3 #41: same third-conditional item about "known about the delay", reworded (Had I known -> If I had known).
- file-5 #270: Near-duplicate of file-3 #61: same "Hardly had ... when" inversion item with near-identical sentences.

### Tagging decision (final)
- file-5 #0-39 (batches 41-42, tagged "CLAT RC"): all 40 are principle-plus-facts Legal Reasoning items with short passages, not passage-based RC. Content passes. With batch 40 retagged, the bank now has no genuine CLAT RC items. Decision: retagged to CLAT Legal Reasoning by the importer (decisions.json).

### Principle overlap with batch 40 (kept; facts and outcomes differ)
- #9 vs file-4 #196 (inspection); #12 vs file-4 #187 (joint liability); #19 vs file-4 #194 (agency); #21 vs file-4 #182/183 (remoteness); #44 vs file-4 #188 (accident principle; tort vs criminal); #52 vs file-4 #198 (trademark); #63 vs file-4 #195 (bailment); #72 vs file-4 #191 (fair hearing); #76 vs file-4 #198 (trademark); #82 vs file-4 #183 (remoteness); #83 vs file-4 #194 (agency); #85 vs file-4 #186 (child trespasser); #97 vs file-4 #197 (idea-expression); #98 vs file-4 #191 (fair hearing)

### Related items (kept)
- #2: file-5 #58 (chemical escape; act of God vs polluter pays); #13: file-5 #53; #15: file-5 #75 (penalty clauses); #31: file-5 #84; #36: file-5 #77 / #97; #53: file-5 #13; #58: file-5 #2; #75: file-5 #15; #77: file-5 #36 / #97; #84: file-5 #31; #105: file-2 #130 (plastic-bag ban, different argument); #163: AS-QA-CQ111; #166: AS-QA-M2-QA-18 / file-4 #25 (different divisor property); #171: AS-QA-M3-QA-09 (one vs two absolute values); #176: IQ-E-03 / AS-QA-CQ77; #184: AS-QA-CQ57; #186: AS-CU-QR-UG21; #187: AS-CU-QR-G-Q116 (finds k from a root ratio); #189: file-4 #30 (different function type); #192: file-1 #59 (gap 2 vs gap 1); #194: file-4 #24 (with vs without replacement); #202: AS-QA-CQ39 (reciprocals); #213: file-5 #171; #216: AS-QA-M1-QA-21 / file-4 #34; #219: AS-QA-M4-QA-09 / AS-CU-QR-UG23; #224: file-3 #58; #234: file-3 #51 (affect/effect, opposite answer); #250: AS-CU-VA-UE21 / AS-CU-VA-UE57 (different subject); #251: file-3 #69 (principal/principle, pair format)

### Soft notes
- file-5 #60: Borderline on the duty-to-speak exception; key holds under caveat emptor as stated.
- file-5 #126: Paradox resolves by plain arithmetic; acceptable.
- file-5 #165: Trap (C) explanation ("adds the coordinates of B's side only") is vague; acceptable.
- file-5 #180: Trap (D) route (3 + 5 × 3 + 2) is arbitrary; acceptable.
- file-5 #192: Trap (C) explanation is vague; acceptable.
- file-5 #219: Trap (C) explanation ("8 + 4") is vague; acceptable.
- file-5 #224: Modern usage also accepts "their"; "his" is the formal-exam answer.
- file-5 #239: Option C is arguably also true of the passage; key A is the best answer.

### Checks
- No CLAT Current Affairs or GK items.
- CLAT Legal (#40-99): every key follows from the stated principle only.
- Keys: every batch 41-54 is 5/5/5/5 A/B/C/D with a maximum run of 2.
