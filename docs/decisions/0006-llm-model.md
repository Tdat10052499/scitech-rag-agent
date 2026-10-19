# 0006. LLM model and serving

- Status: proposed (results filled from the D06 run, 2026-10-19; waiting for LDN's review on #58)
- Date: 2026-10-19
- Deciders: DAT (author), LDN (reviews the rating method and the results)

> The method was fixed before the run and reviewed by LDN on #58 (0ead41a). Results and Decision below come from the run on D06. No result in this file is an estimate unless it says so.

## Context
ADR 0001 fixes the interface: one OpenAI-compatible endpoint (`docs/contracts/llm-client.md`), with the open-source model on an external GPU and a hosted API or small local model as fallback. This ADR picks the model, the serving setup and the fallback, so W3-W7 run on one setup.

Constraints:
- **GPU:** free Kaggle sessions, 2 × Tesla T4 (15,360 MiB each). The weekly quota (30 h of session time) is shared with FAO's embedding runs (`docs/runbooks/llm-serving.md`, section 5).
- **Calls per question:** the agent makes 2 LLM calls per question today (answer and follow-ups, `agent/src/scitech_agent/agent.py`), and 3 once query rewriting uses the LLM (W4). Latency per question is a multiple of one call.
- **Evaluation load:** W7 runs hundreds of calls (4 RQ2 conditions × 60 items, plus the judge), so speed matters for the schedule, not only for the demo.
- **Judge:** `evaluation/PLAN.md` section 5 says the faithfulness judge must differ from the generator and is chosen here.

Speed was measured on D02 (`docs/runbooks/llm-serving.md`, section 4; n = 5 per cell, two sessions). Quality was not measured.

| Setup | TTFT | 200-token answer |
|---|---|---|
| Kaggle T4, 3B, through the tunnel | ~0.4 s | ~4 s |
| Kaggle T4, 7B, through the tunnel | ~0.4 s | ~8-9 s |
| Laptop CPU (i7-1260P), 3B | ~2.2-2.9 s | ~15-19 s |

## Options considered
Generator candidates (Ollama tags already measured for speed on D02):
1. `qwen2.5:3b`
2. `llama3.2:3b`
3. `qwen2.5:7b`

The exact quantisation of each tag is read with `ollama show <tag>` on the run day and recorded in the results table; the default tag quantisation is what the runbook measured.

Serving: Ollama on Kaggle behind a Cloudflare quick tunnel (runbook section 1), against vLLM. vLLM is not tested here: Ollama already serves all three tags on a T4, and a second server stack is not worth the setup time in the compressed schedule (ADR 0010).

Fallback (for a lost GPU session or a demo without Kaggle):
- A. A 3B model on the laptop CPU with Ollama (measured, ~15-19 s per 200 tokens).
- B. A hosted API through the same interface (not measured; needs a key and has a cost).

## Method (revised after LDN's review on #58: separate grounded column, LDN rates all 30, golden set version recorded)
**Items:** the 10 golden items of W1-D4-LDN-1 (`gs-001` to `gs-010`, all `dev`, English). The replan on `docs/plan/week-02.md` (W2-D4-DAT-1) uses these instead of waiting for 30. If #56 is merged before the run, its wording is used (it changes gs-001, gs-003, gs-005 and gs-007, rule 10); otherwise the wording on `main`. The results record the commit and the sha256 of `evaluation/golden_set/golden.jsonl` that were used.

**Input ("hand-pasted context"):**
- The context of each item is the title and abstract of each document in its `relevant_doc_ids`, taken from the cleaned corpus (snapshot 307).
- It is formatted exactly as the agent formats sources: `format_sources` and the system prompt `agent/prompts/answer.md`. The comparison therefore tests the prompt the product uses.
- No retrieval is involved, so retrieval errors cannot mix into the answer scores.

**Settings:**
- `temperature = 0` and `max_tokens = 512`, the agent defaults in `AgentConfig`.
- One run per model and item, so 30 answers in total.
- All three models run in one Kaggle session, through the same tunnel. The order of models is rotated per item, because the runbook saw the decode rate fall within a session (section 4.1).

**Measures per answer:**

| Measure | How | Scale |
|---|---|---|
| Relevance | Rated by hand against the question and the `reference_answer` (which guides the rating but is not the only valid answer), worded as "answer relevance" in `evaluation/PLAN.md` section 4.2, so it can be compared with the W7 numbers | 1 = does not address the question, 2 = partly (for example, answers only one part of a two-part question such as gs-001), 3 = fully |
| Grounded | Rated by hand against the pasted abstracts. Kept apart from relevance, as faithfulness is in `evaluation/PLAN.md` section 4.2, because 3B models often add claims from memory (prior-knowledge threat, section 7) | Yes = every factual claim is in the pasted abstracts; no = at least one is not |
| Citation adherence | Counted automatically: sentences with at least one `[n]`, and invalid markers (a number outside 1..number of sources). The script cannot tell factual sentences from others, so a sentence that only says the evidence is insufficient counts as uncited | Sentences cited of all sentences; count of invalid markers |
| Language | Answer in the language of the question (all 10 are English). Checked by a heuristic (at least 90% of the letters are ASCII), so a raters' note overrides it | Count of answers not in English |
| Speed | TTFT, total time and completion tokens from the streamed call, as in `bench_llm.py` | Seconds; tokens/s |

**Tooling:** `notebooks/llm-serving/compare_llm.py` builds the contexts, runs the calls, writes the blind rating sheets and computes the results table and the decision rule; steps in `docs/runbooks/llm-serving.md`, section 7.

**Blind rating:**
- The 30 answers are shuffled with a fixed seed, and the model names are replaced by codes (A01-A30) before rating. The key stays closed until both sheets are back.
- LDN rates all 30 on both columns, on D06 after the run.
- DAT rates all 30 on relevance only. Grounded is rated by LDN alone, because DAT built the agent and does not annotate faithfulness (`evaluation/PLAN.md` section 9, decision 6); a single rater for grounded is a limitation of this ADR.
- Relevance agreement is reported as the number of equal ratings out of 30; where the two ratings differ, both are shown. Each rater's means are reported separately.
- 30 pairs show whether the written scale is understood, not that the ratings are reliable, so no kappa is reported.

**Decision rule (fixed before the run):**
1. Highest mean relevance.
2. If the means differ by 0.2 or less (2 of 10 ratings), the difference counts as noise at n = 10. The tie then goes to the model with fewer ungrounded answers, then fewer invalid citations, then to the faster model.
3. The means are compared for each rater. If the top two models differ by more than 0.2 in one rater's means but not in the other's, it is a tie and step 2 applies.
4. `qwen2.5:7b` is chosen only if it is better than the best 3B model by more than that margin, because it is about 2 times slower per answer.

**What n = 10 can and cannot show:** the ranking is indicative only. One rating changes a mean by 0.1, so one disagreement between raters can reach the 0.2 margin. The items are English-only and have no `unanswerable` or `follow_up` type, so refusal behaviour and multi-turn use are not tested here. Those come in W4 (evidence check) and W7 (RQ2).

## Results
Run on 2026-10-19, 06:34-06:38 UTC, in one Kaggle session (2 × T4), through the tunnel; Ollama version **not recorded** (TBD if the session log has it). Script `compare_llm.py` at 6b0b94c. Golden set: #56's `golden.jsonl` at 5f1dbfb (sha256 `a21855e5183ea08aef98eb3c522527a02a5a81d6350fc028f9e1175180968378`, as recorded in ADR 0007), so gs-001, gs-003, gs-005 and gs-007 use #56's wording. Raw answers, the key and both rating sheets are kept outside git (DAT's `data/adr0006/`; the answers quote the abstracts). 30 answers, 0 failed; 3 warm-up calls (one per model, not scored) took 93.2 s, 40.1 s and 7.0 s, which is model loading.

| Model (tag, quantisation) | Mean relevance LDN / DAT (1-3) | Relevance 1 / 2 / 3 (LDN) | Ungrounded answers (LDN, of 10) | Sentences cited | Invalid `[n]` | Not English | TTFT median s | Total median s | tok/s median |
|---|---|---|---|---|---|---|---|---|---|
| `qwen2.5:3b` (not recorded) | 2.80 / 2.40 | 1 / 0 / 9 | 1 | 9 of 26 | 0 | 1 | 0.71 | 1.8 | 79.7 |
| `llama3.2:3b` (not recorded) | 2.80 / 2.40 | 0 / 2 / 8 | 1 | 11 of 20 | 0 | 0 | 0.75 | 1.5 | 86.3 |
| `qwen2.5:7b` (not recorded) | 2.60 / 2.40 | 1 / 2 / 7 | 0 | 15 of 21 | 0 | 1 | 0.82 | 2.4 | 38.6 |

Relevance agreement (DAT vs LDN): **18 of 30** equal. In 11 of the 12 differences LDN rated 3 and DAT 2 (A21, gs-002 `qwen2.5:7b`, is the other way round), so the disagreement is mostly a shift at the 2/3 boundary rather than scatter. Both raters gave 1 to the same two answers. The 12 pairs are listed in the `summarise` output.

What the table shows, and what it does not:
- **gs-007** ("name two approaches"): both qwen models answered only `[1] [2]` (6-7 tokens), with no text; `llama3.2:3b` named both approaches. These are the two relevance 1 ratings. LDN rated both "grounded: yes" because they make no claim, so the ungrounded column does not count them.
- **Not English** counts the same two answers: they have no letters, so the heuristic fails them. No answer was in another language.
- **Answers with no `[n]` at all:** `llama3.2:3b` 4 of 10 (gs-003, 008, 009, 010), `qwen2.5:3b` 1 (gs-004), `qwen2.5:7b` 0.
- **Ungrounded:** `qwen2.5:3b` on gs-004 (an example not in the abstracts) and `llama3.2:3b` on gs-003 (opens with "The evidence is insufficient." although the abstract gives the figures), from LDN's notes.
- **Speed:** the total-time gap between the 3B models (1.5 s vs 1.8 s) comes partly from answer length: `llama3.2:3b` wrote 682 completion tokens over the 10 items, `qwen2.5:3b` 952 (inferred from the token counts; not tested separately).

## Decision
By the decision rule fixed before the run:
- All three means are within 0.2 for both raters (DAT gave all three 2.40), so the result is a tie (rule 2). `qwen2.5:7b` is not better by more than the margin, so it is out of the tie-break (rule 4).
- Between the 3B models: ungrounded 1 vs 1, invalid citations 0 vs 0, then speed: `llama3.2:3b` (1.5 s total median) over `qwen2.5:3b` (1.8 s).

So:
- **Generator:** `llama3.2:3b` (Ollama default tag; quantisation not recorded, read with `ollama show` at the next session and pinned in `evaluation/SNAPSHOT.md`), `LLM_MODEL=llama3.2:3b`.
- **Serving:** Ollama on Kaggle 2 × T4 behind a Cloudflare tunnel, through `LLM_BASE_URL`.
- **Fallback:** A, the same `llama3.2:3b` on the laptop CPU with Ollama, for the demo; it needs no key or cost.
- **Judge for faithfulness** (`evaluation/PLAN.md` section 5): not the generator. The candidate is the hosted API of ADR 0001; it is named in `evaluation/SNAPSHOT.md`.

At n = 10 this is a choice between models whose answer quality could not be told apart, made on speed. It is not evidence that `llama3.2:3b` answers better. `qwen2.5:7b` had no ungrounded answer and cited the most sentences, which matters for a product that must cite, but the rule fixed before the run does not weigh citation coverage, and it is not changed after seeing the results.

## Consequences
- The model name, tag, quantisation and Ollama version are pinned in `evaluation/SNAPSHOT.md` and are not changed after feature freeze (D16), so W7 runs on one setup (runbook section 6).
- The quick tunnel is unauthenticated. Sessions stay short, the URL is shared only inside the team, and it is never committed.
- If the GPU session is lost during a run, the fallback answers the demo. Evaluation runs wait for a new session instead of mixing models.
- The default `LLM_TIMEOUT=60` is below the cold start of a new session (74-79 s, runbook 4.1). The first call after a new session may time out once. The client's retry is expected to cover it (not observed yet, DAT journal D04), and the runbook should say to warm the model up first.
- `llama3.2:3b` left 4 of 10 answers without any `[n]`. The agent's citation check (W4) must handle an answer with no citation, not only invalid numbers.
- Revisit if the 3B answers fail the faithfulness pilot (W4-D4-LDN-1), or if the GPU quota runs out before W7. If they do, `qwen2.5:7b` is the next candidate: it had no ungrounded answer here, at about 2 times the time per answer.
