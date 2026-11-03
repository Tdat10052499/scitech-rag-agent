# Demo script (W8-D3-DAT-1)

Status: draft by DAT, 2026-11-02, written ahead of the plan (D21). The questions were chosen from the W7 run A2 (`evaluation/runs/20261102T112100Z-answers-w7-a2-rewrite.json`, #179). That run used the product configuration: hybrid retrieval, rewrite on, evidence check off. Every question below must be asked once on the final build during the dry run (W8-D4-DAT-1, D24) before it is used live. Drafted with AI assistance (Claude); DAT is responsible for the final text.

Length: 3 to 5 minutes. Presenter: DAT. The data page is cut (replan), so the demo shows only the chat.

## Where the demo runs

**Decided (DAT, 2026-11-02): the live demo runs on the hosted Space.** The laptop stack is the fallback; start it before the session too, so a switch takes seconds.

| | Laptop (frozen stack) | Hosted Space (`https://teichi-scitech-rag-agent.hf.space`, `docs/runbooks/hosting.md`) |
|---|---|---|
| LLM | `llama3.2:3b` on the laptop GPU: the model of every evaluation number | `qwen/qwen3.8-27b` on Groq: **not** the evaluated model |
| Speed | first token p50 0.42 s, full turn p50 4.3 s (`performance.md` run B) | first token 1.2 to 1.5 s, answer done in 1.4 to 2.1 s (4 script questions, one run each, 2026-11-02) |
| Risk | laptop, Qdrant and Ollama must all be up | room Wi-Fi; Groq quota (`CHAT_TOTAL_PER_MINUTE=2`, so wait about 30 s between questions); the Space sleeps after 48 h without visits (open it before the session) |

Say once, at the opening: "This public copy uses a larger hosted model; the evaluation numbers in the report are for the 3B model on the laptop."

## 0. Before the session (about 10 minutes before)

- **Space (live demo):** open `https://teichi-scitech-rag-agent.hf.space` about 10 minutes before (it may be asleep or rebuilding after a merge to `main`; wait for the chat to load), and ask the warm-up question there. Do not merge to `main` on the presentation day, because every merge rebuilds the Space (`.github/workflows/deploy-hf-space.yml`).
- **Laptop (fallback):** start it with the steps below and leave it open in a second tab.

- **Stack:** start the frozen stack on the demo laptop. Native Windows: Qdrant from its folder, Ollama, backend, frontend (README, "Run the real app on Windows without Docker"). Docker: `make up`.
- **Index:** Qdrant `scitech_chunks` must show 121,926 points.
- **Check the settings in `.env`:**
  - `AGENT_REWRITE=on`
  - `AGENT_SELF_CHECK=off`
  - `QDRANT_URL=http://127.0.0.1:6333`
  - `BM25_RELOAD_SECONDS` empty
- **Warm-up:** ask one warm-up question that is not part of the script. The first question loads the models: the embedding model takes about 15 s, `llama3.2:3b` about 5 s.
- **Clean start:** open a new browser tab, so the conversation has no history.

## 1. Opening (about 20 s)

"This is a research assistant for computational linguistics. It searches 121,860 arXiv cs.CL papers, answers only from the passages it finds, cites every claim, and says so when the papers do not answer the question."

## 2. Cited answer (about 60 s)

Ask:

> How can a language model get better at maths problems by using more computation at answer time?

Show:

1. The answer starts streaming in about 1.5 s on the Space (1.2 to 1.5 s in the check of 2026-11-02, `docs/runbooks/hosting.md` §5). On the laptop the first token arrived at a median of 0.42 s (`docs/runbooks/performance.md`).
2. The `[n]` markers in the text. Click one: the sources panel shows that paper with title, authors, date and arXiv link.
3. The answer names test-time scaling (Beam Search, DVTS), as in the golden reference.

Say: "Each number points to a passage the system retrieved. The model is told to use only those passages."

## 3. Follow-up question (about 60 s)

Ask, in the same conversation:

> What goes wrong with those methods?

Show:

- **The pronoun is resolved.** The rewrite step turns "those methods" into a standalone query, with an answer about the limits of test-time scaling for maths reasoning (`gs-019`). In A2 this answer scored faithfulness 1.0 and cited the relevant paper.
- **Suggested follow-ups:** the follow-up chips under the answer. Click one to show that the suggestions are new questions on the same topic.

Say: "Without the rewrite, 'those methods' would be searched literally. Retrieval on the raw follow-up questions found almost nothing: recall@5 was 0.09 in R1."

## 4. Refusal (about 45 s)

Ask, in a new conversation or the same one:

> How many GPU hours did it take to train the student model in the Reverse-Enhanced Thinking (RevThink) framework?

Show:

- The system says the sources do not give this. The RevThink paper is in the corpus, but its abstract has no compute figure (`gs-u03`, refused in A1 and A2).
- The refusal note in the UI.
- No follow-up suggestions after a refusal (fixed in #167).

Optional, if time allows, to show an off-topic question:

> What is the best pizza recipe?

It is refused, with no follow-ups. This is the case from the clean-clone check on 2026-10-30 that led to #167.

Say: "When the evidence is not there, it says so instead of guessing."

## 4b. Reading a paper's full text (optional, about 45 s)

Ask, in a new conversation:

> Which library did 2302.00083 use for sparse retrieval?

Show:

- The sources: titles end with "(full text, section: ...)". The index holds abstracts only. Because the question names a paper by arXiv id, the agent reads that paper's HTML full text at request time and does not index it (ADR 0012).
- The answer is Pyserini, cited from the Retrieval section. The abstract does not say this.
- If an answer that used full text cites nothing, or gives a number that its cited sources do not contain, a "Note" line under it says so.

Passed on the Space in the trap test of 2026-11-03 (question 3.1). If the sources show only the abstract, the Space could not reach arxiv.org. Skip this part and say so.

Say: "For a paper you name, it can also read the full text, and it still cites the section it used."

## 5. Closing (about 20 s)

"Behind this are:
- a hybrid search over 121,926 chunks that answers in under 135 ms at p95;
- a language model behind an OpenAI-compatible interface: here a hosted model, and in the evaluation a local 3-billion-parameter model on a laptop GPU;
- an evaluation on 65 golden questions.

The results are in the report."

## 6. Backup questions

All of these were answered with faithfulness 1.0 and the relevant paper cited in A2. Use them if a script question goes wrong.

| Item | Question |
|---|---|
| `gs-046` | In one study that gave GPT-4 news headlines published after its knowledge cutoff, how well did the model predict the stock market's first reaction? |
| `gs-047` | The first broad evaluation of ChatGPT as a zero-shot Text-to-SQL system used how many benchmark datasets, and in which setting did it beat a fine-tuned model? |
| `gs-017` | How does high-precision scoring fix the problem of tied relevance scores when a retrieval system runs in low precision? |
| `gs-010` | How much better is LongRAG than ordinary RAG and long-context LLMs on multi-hop question answering over long documents? |

## 7. Do not ask live

The following are known weak cases, all documented in the report.

| What | Why |
|---|---|
| "How many parameters does the largest Gemini model have?" (`gs-u05`) | Answered instead of refused in A1 and A2 (`evaluation/reports/answer-errors-w7.md` §4.3) |
| Deeper questions about one paper without its arXiv id, for example on LongRAG after 3 or more turns | Without an id there is no full text, so the answer repeats the abstract (video test, 2026-10-30). Name the id instead (section 4b) |
| Exact numbers from a paper's figures, for example perplexity in 2302.00083 | Numbers shown only in figures are not in the text the agent reads (likely the case here, not checked on the whole paper). On the laptop model this produced invented numbers, flagged by the "Note" line (2026-11-03) |
| "Which products use X?" | The corpus has no product data. The answer was generic and cited unrelated sources (video test) |
| Multi-hop or comparison questions that need two papers | Recall@5 was 0.32 and 0.50 for these types (R1). Answers often cite the wrong papers |

## 8. If something fails live

- **"The answer service is unavailable":** check the backend window for `llm_unavailable` (Ollama stopped) or `retrieval_failed` (Qdrant window closed). Restart that part; the backend rebuilds the agent on the next request.
- **Slow first answer:** this is the model warm-up. Say so and wait. Do not ask again, because a second request queues behind the first.
- **Wrong or weak answer:** switch to a backup question (section 6) and say that the report has an error analysis of such cases.
- **Space down, rate-limited (HTTP 429) or very slow:** switch to the laptop tab and say so in one sentence. Wait about 30 s between questions on the Space (`CHAT_TOTAL_PER_MINUTE=2`).
- **Fallback:** screenshots of sections 2 to 4 taken in the dry run (W8-D4-DAT-1), stored with the slides.
