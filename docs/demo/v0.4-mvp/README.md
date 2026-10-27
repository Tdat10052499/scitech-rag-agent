# Demo v1 (Gate W4, `v0.4-mvp`)

Screen recordings of the three gate paths, made on 2026-10-27 (D13) in Chrome on DAT's laptop. Setup: full local index (Qdrant `scitech_chunks` and BM25), `AGENT_MODE=real`, hybrid retrieval with k = 5, and the LLM `llama3.2:3b` on Kaggle through a tunnel. These GIFs are demo video v1. They are short and have no sound, unlike the 3-minute narrated video in the plan.

| File | Shows |
|---|---|
| `demo-answer-insufficient.gif` (about 26 s) | LongRAG question (gs-010): answer with `[2]` and `[1]`; click on `[2]` highlights source 2; 4 follow-up chips; one chip sent as turn 2; "New conversation"; "Which language model will have the highest MMLU score in 2027?" shows "Not enough evidence in the corpus". |
| `demo-error.gif` (about 9 s) | Backend restarted with `LLM_BASE_URL` on a closed port: the sources arrive, then "The language model is not reachable right now. Please try again later." (`llm_unavailable`); the input stays usable. |
| `ui-1-normal-answer.png` | Frame of the first GIF: answer with citations, source 2 highlighted. |
| `ui-2-insufficient.png` | Last frame of the first GIF: insufficient evidence. |
| `ui-3-errors.png` | Last frame of the second GIF: error after the sources. |

Known issue visible in the recording: "6.16% [2]" attaches a figure to a source that may not state it (#115).
