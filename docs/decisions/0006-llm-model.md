# 0006. LLM model and serving

- Status: proposed (draft for W2-D4-DAT-1; the comparison runs on D06, 2026-10-19)
- Date: 2026-10-19
- Deciders: DAT (author), LDN (reviews the rating method)

> Draft. The method is fixed before the run, so LDN can review it first. Cells marked **TBD** are filled from the D06 run. No result in this file is an estimate unless it says so.

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

## Method (to be reviewed by LDN before the run)
**Items:** the 10 golden items of W1-D4-LDN-1 (`gs-001` to `gs-010`, all `dev`, English) as merged on `main`. The replan on `docs/plan/week-02.md` (W2-D4-DAT-1) uses these instead of waiting for 30.

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
| Answer quality | Rated by hand against the question, the pasted sources and the `reference_answer` (which guides the rating but is not the only valid answer) | 1 = does not address the question or contradicts the sources, 2 = partly, 3 = fully and only from the sources. The same 1-3 scale as "answer relevance" in `evaluation/PLAN.md` section 4, with "only from the sources" added |
| Citation adherence | Counted automatically: sentences with at least one `[n]`, and invalid markers (a number outside 1..number of sources) | Share of factual sentences cited; count of invalid markers |
| Language | Answer in the language of the question (all 10 are English) | Yes / no |
| Speed | TTFT, total time and completion tokens from the streamed call, as in `bench_llm.py` | Seconds; tokens/s |

**Blind rating:**
- The 30 answers are shuffled, and the model names are replaced by codes before rating.
- DAT rates all 30.
- LDN independently rates a random 9 (3 per model) with the same written scale. Agreement is reported as the number of equal ratings out of 9; where the two ratings differ, both are shown.
- With 9 pairs, a kappa would be too unstable to report.

**Decision rule (fixed before the run):**
1. Highest mean quality.
2. If the means differ by 0.2 or less (2 of 10 ratings), the difference counts as noise at n = 10. The tie then goes to the model with fewer invalid citations, then to the faster model.
3. `qwen2.5:7b` is chosen only if it is better than the best 3B model by more than that margin, because it is about 2 times slower per answer.

**What n = 10 can and cannot show:** the ranking is indicative only. One rating changes a mean by 0.1. The items are English-only and have no `unanswerable` or `follow_up` type, so refusal behaviour and multi-turn use are not tested here. Those come in W4 (evidence check) and W7 (RQ2).

## Results
Run on **TBD** (Kaggle session, Ollama version **TBD**, tunnel). Raw answers and ratings: **TBD** (path outside git or in `evaluation/runs/`, as LDN prefers).

| Model (tag, quantisation) | Mean quality (1-3) | Ratings 1 / 2 / 3 | Factual sentences cited | Invalid `[n]` | TTFT median s | Total median s | tok/s median |
|---|---|---|---|---|---|---|---|
| `qwen2.5:3b` (TBD) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| `llama3.2:3b` (TBD) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| `qwen2.5:7b` (TBD) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

Rater agreement (DAT vs LDN): **TBD** of 9 equal.

## Decision
**TBD after the run:**
- **Generator:** model, tag, quantisation, `LLM_MODEL` value.
- **Serving:** Ollama on Kaggle 2 × T4 behind a Cloudflare tunnel, through `LLM_BASE_URL`.
- **Fallback:** A or B above. DAT's proposal before the run is A for the demo, because it needs no key or cost. The fallback model is the faster 3B model if the generator is 7B.
- **Judge for faithfulness** (`evaluation/PLAN.md` section 5): not the generator. The candidate is the hosted API of ADR 0001; it is named in `evaluation/SNAPSHOT.md`.

## Consequences
- The model name, tag, quantisation and Ollama version are pinned in `evaluation/SNAPSHOT.md` and are not changed after feature freeze (D16), so W7 runs on one setup (runbook section 6).
- The quick tunnel is unauthenticated. Sessions stay short, the URL is shared only inside the team, and it is never committed.
- If the GPU session is lost during a run, the fallback answers the demo. Evaluation runs wait for a new session instead of mixing models.
- The default `LLM_TIMEOUT=60` is below the cold start of a new session (74-79 s, runbook 4.1). The first call after a new session may time out once. The client's retry is expected to cover it (not observed yet, DAT journal D04), and the runbook should say to warm the model up first.
- Revisit if the 3B answers fail the faithfulness pilot (W4-D4-LDN-1), or if the GPU quota runs out before W7.
