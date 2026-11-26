# Phase 15: CardioStage vs Chatbots

**Goal:** answer a faculty member's question, *"Why would anyone use this instead of ChatGPT or Claude?"*, with evidence instead of opinion.

This phase is about **fair comparisons**: giving every contestant the same information, fixing the rules before seeing results, and reporting what you find even when it isn't what you hoped.

**Files in this phase**

| File | Job |
|---|---|
| `src/cardiostage/llm_compare.py` | Builds the paste-ready prompts, reads the replies strictly, scores everyone on the same patients |
| `data/llm_compare/prompts/` | The 17 prompts exactly as pasted (the pre-registration) |
| `data/llm_compare/responses/` | Every chatbot reply, unedited |
| `data/llm_compare/log.md` | What happened during the run: models, tiers, the one copy mix-up |
| `reports/llm_compare.csv` | The results |
| `tests/test_llm_compare.py` | Checks the prompts and the scoring using fake replies |

```bash
python -m cardiostage.llm_compare prompts   # rebuild the prompts (identical every time)
python -m cardiostage.llm_compare score     # score CardioStage and both chatbots
```

---

## 1. Choosing how to test: API vs chat website

Programs talk to chatbots through an **API**, which is billed per use, separately from any chat subscription. The full API version would have cost about $10–20. The owner chose the **free route**: paste the patients into the chat websites by hand.

That choice changes *what* is measured. It isn't "the best any AI can do". It's **"what a person gets from these chatbots"**, which is exactly what the faculty member asked about. Good experiments match the method to the question.

## 2. Making it fair

Each chatbot got **the same six facts CardioStage's check-up stage uses** (age, sex, chest-pain type, blood pressure, cholesterol, fasting blood sugar), and nothing more:

- **Same situation:** "referred for coronary angiography", the population CardioStage learned from.
- **Same outcome:** at least 50% narrowing of a major artery, CardioStage's exact definition of disease.
- **Same missing data:** Iran's cholesterol shown as "not recorded", as in v2.
- **Hidden:** hospital names and outcomes. A test checks that no prompt contains them.
- **Shuffled:** patients mixed so every batch contains several hospitals and eras. A batch of only 1980s patients could hint at the answer.

## 3. Pre-registration: fixing the rules first

Before any patient was sent, the prompts, the patient order and every metric were **committed to GitHub** (`df96179`). This is the same rule as the final exams in phases 9 and 14. If you choose your measures after seeing results, you can always find one that flatters you.

Rules fixed in advance:
- **One try per batch.** You may not re-ask until you like the answer.
- A missing or unreadable answer **counts as missing**. It's never guessed or filled in.
- The **prompt never changes** to improve scores.

A test also checks that the prompt files on disk are *exactly* what the code builds, so the pre-registration can't drift.

## 4. Running it honestly

17 batches × 2 chatbots = 34 fresh chats. Two things happened that the log records:
- **A copy mix-up:** one "Claude" reply was really ChatGPT's (all 15 numbers identical). Two chatbots matching on 15 patients is practically impossible, so it was caught, discarded unsaved, and the real reply pasted. This wasn't a re-ask, because Claude's actual answer was never seen and replaced.
- **Unequal tiers:** ChatGPT was the free tier; Claude was the owner's **paid** plan (Opus 5.5). That isn't a flaw, but it must be stated every time. Otherwise one chatbot could look better just because it was the paid one.

> **Lesson:** a run log turns surprises into documented facts instead of hidden problems.

## 5. Results (245 sealed patients, 59% sick)

| | CardioStage v2 | ChatGPT, free | Claude, paid |
|---|---|---|---|
| Ranking (AUC) | 0.84 | 0.76 | 0.85 |
| Difference vs CardioStage [95% CI] | | −0.09 [−0.14, −0.03] | +0.01 [−0.03, +0.04] |
| Calibration error | **0.040** | 0.118 | 0.109 |
| Average predicted | 59% | 49% | 52% |
| Reassured / sick among them | 11% / **0** | 3% / 3 | 7% / 1 |

**How to read the difference column:** each chatbot was compared with CardioStage *on the same resampled patients* (a **paired bootstrap**). If the interval excludes 0, the difference is real. ChatGPT's (−0.14 to −0.03) excludes 0, so it's clearly worse. Claude's (−0.03 to +0.04) includes 0, so it's **a tie**.

What it means:
1. **Ranking:** paid Claude matches CardioStage; free ChatGPT falls behind (worst at Hungary, 0.62, and Switzerland, 0.52, close to a coin flip).
2. **Honest percentages:** both chatbots guessed too low across the board. CardioStage's calibration error is about **3 times smaller**. For someone asking "what's my chance?", that matters.
3. **Safety:** CardioStage reassured the most people and none were sick. The numbers are small, and the 14.4% cut-off was tuned for CardioStage, but a chatbot's percentages come with *no* tested cut-off at all.
4. **Where chatbots win:** typical angina. Both chatbots told sick from healthy better there (0.78 and 0.75 vs 0.60). They learned from textbooks; CardioStage learned from 1980s data that got this symptom wrong (phase 14). Even so, Claude's *average* for these patients was far too low (54% vs 82% actually sick).

## 6. Memorisation: when the test may not be unseen

The Cleveland dataset is famous and has been online for decades, so it was probably in the chatbots' training text. If a chatbot had memorised it, it would do suspiciously well on Cleveland but not on lesser-known data.

Claude did slightly **better** than CardioStage on Cleveland (+0.02) and **worse** on Iran (−0.07, its only significant gap). That's *consistent with* memorisation, but with 61 patients per group it's a **hint, not proof**. ChatGPT showed the opposite pattern.

> **Lesson:** "the model never saw these patients" is easy to guarantee for your own model, and almost impossible to guarantee for a large model trained on the internet.

## 7. The answer to the faculty member

> "I tested it. On 245 patients my model had never seen, a free chatbot ranked patients significantly worse than CardioStage. The top paid model ranked them about as well, but both chatbots gave percentages that were systematically too low. CardioStage's percentages were about three times more accurate, and it reassured more patients without missing anyone sick. CardioStage is also free, gives the same answer every time and is fully auditable. And the chatbots were better on the one symptom where CardioStage is weakest, which shows where a future version could combine both."

## 8. Check your understanding
1. Why does pasting into the free websites answer the faculty member's question better than the API would, even though it's less controlled?
2. Why were hospital names hidden and patients shuffled?
3. What would go wrong if the prompt could be changed after the first few batches?
4. The copy mix-up was replaced. Why isn't that a re-ask?
5. Claude's AUC difference interval is [−0.03, +0.04]. What can you conclude, and what can't you?
6. Both chatbots ranked reasonably but had calibration errors near 0.11. Why does that matter to a patient?
7. What pattern would suggest memorisation, and why is it only a hint here?
8. Why must every mention say "free ChatGPT" and "paid Claude"?

## Answers

**1.** The question is what a *person* gets by asking a chatbot instead. People use the chat websites, often the free tier, so testing them measures the real alternative. The API would measure the best possible setup, which most people never use.

**2.** CardioStage doesn't get the hospital name, so the chatbots shouldn't either. Shuffling stops a batch from being all one hospital or era, which could hint at disease rates.

**3.** The prompt could be tuned until the scores looked good. The final numbers would then partly reflect the tuning, not the chatbot, and couldn't be trusted.

**4.** The wrong paste was ChatGPT's reply, so Claude's real answer had never been recorded. Pasting Claude's actual reply from the same chat recorded its first and only answer.

**5.** There's no clear difference in ranking between Claude and CardioStage on these patients. You *can't* conclude they're exactly equal, or that one is better; the interval allows a small edge either way.

**6.** Calibration is about whether the percentage itself is right. A chatbot that says 40% when the true chance is about 60% would mislead someone into feeling safer than they are, even if it puts patients in the right order.

**7.** Doing unusually well on a famous dataset (Cleveland) but worse on a less-known one (Iran). It's only a hint because each group is about 60 patients, so differences of this size could be chance.

**8.** The tiers differ (free ChatGPT, paid Claude Opus 5.5). Without the labels, a reader might think one company's chatbot is better, when part of the gap could be free vs paid.
