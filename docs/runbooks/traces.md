# Per-request traces

Since W5-D4-DAT-1 the agent writes one JSON line per question to `data/logs/traces.jsonl` (git-ignored). Code: `agent/src/scitech_agent/trace.py`; tests: `agent/tests/test_trace.py`.

## Where and when

- Path: `AGENT_TRACES` (a file path, or `off`). Empty: `<DATA_DIR>/logs/traces.jsonl`, relative to the directory the backend or script runs from. The file is appended to, never rotated or cleared.
- Written by the agent built with `scitech_agent.factory.agent_from_env()`, so by the backend in `AGENT_MODE=real` and by evaluation scripts that use that factory. The demo agent (`AGENT_MODE=demo`) and the agent tests write nothing.
- One line per request, also when it fails (`status: "error"`) or the client goes away while the answer streams (`status: "cancelled"`). A write error is logged and never fails the request.
- UTF-8, not ASCII-escaped: Vietnamese text stays readable.

## Fields (`trace_version` 1)

| Field | Type | Content |
|---|---|---|
| `trace_version` | int | 1. Changes when a field is renamed or removed. |
| `trace_id` | string | `msg-...`; equals `done.message_id` sent to the UI, so feedback can be joined to the trace. |
| `timestamp` | string | Start of the request, ISO 8601 UTC with milliseconds. |
| `session_id` | string | The `session_id` of `/chat` (the frontend makes a random UUID per conversation; `batch-...` in `run_batch`). |
| `status` | string | `ok`, `error` or `cancelled`. |
| `error` | string or null | Contract `Error.code` when `status` is `error`. |
| `message` | string | The question as the user typed it. |
| `query` | string | The search query: the rewrite (`AGENT_REWRITE=on`, follow-up messages) or `message`. |
| `rewritten` | bool | `query != message`. |
| `retrieved` | list | Every hit of the retriever, in its order: `{chunk_id, doc_id, score}` (score on the retriever's scale: cosine, BM25 or RRF). No chunk text. |
| `evidence` | object | `min_score` (`RETRIEVAL_MIN_SCORE`), `above_min_score` (hits kept), `self_check` (`off`, `skipped`, `error`, `unreadable`, `yes`, `partly`, `no`), `decision` (`answer`, `refuse_no_evidence`, `refuse_self_check`; null if retrieval failed). |
| `sources` | list | `chunk_id`s sent as `sources` (`[n]` is the n-th); empty on a refusal. |
| `answer_raw` | string or null | LLM answer text before the citation filter (invalid `[n]` still there); null when no answer call was made. |
| `answer` | string | Text streamed to the user (filtered markers, refusal hint included). |
| `citations` | list | `chunk_id`s cited by the answer, in order of first use. |
| `insufficient_evidence` | bool or null | `done.insufficient_evidence`; null when the request did not finish. |
| `followups` | list | Suggested follow-up questions sent to the user. |
| `llm_calls` | int | LLM calls made (rewrite, self-check, answer, follow-ups). |
| `latency_ms` | object | Milliseconds per step that is switched on and ran: `rewrite`, `retrieve`, `self_check`, `answer` (call to end of stream, includes the time the client takes to receive it), `first_token` (request start to first answer fragment), `followups`, `total`. |
| `model` | object | `LLM_MODEL`, `LLM_TIMEOUT`, `LLM_MAX_RETRIES` (never the URL or the key). |
| `config` | object | The `AgentConfig` values (top_k, min_score, flags, limits, token limits) and the retriever class (`HybridRetriever`, ...). |

For latency figures (W7), keep only `status == "ok"` and `evidence.decision == "answer"`: on a refusal, `first_token` is the time to the fixed refusal text, not to an LLM token.

Not logged: names, IP addresses, browser data, the chunk texts, API keys or endpoint URLs. The earlier turns of a conversation are not repeated: they are the earlier lines with the same `session_id`.

## Evaluation without the API

`Agent.run_batch(items)` answers each item in its own new session and returns `BatchResult`s (`id`, `question`, `error`, `sources`, `trace`). An item is a string, a `BatchItem`, or a golden-set object (`id`, `question`, optional `history` of `{"role", "content"}` turns, which become the session's earlier turns). A failed question gets `error` (a contract code) and the batch goes on. `BatchResult.to_dict()` gives `answer_id`, `answer`, `answer_raw`, `sources` (`n`, `chunk_id`, `doc_id`, `title`, `text`, `score`, as `scitech_eval.answers.read_answers` expects), `citations`, `followups`, `insufficient_evidence` and the trace under `trace`.

An evaluation run should set `AGENT_TRACES` to its own file (for example next to its run file), so its traces do not mix with the backend's or the user study's in the default file.

```python
from scitech_agent.factory import agent_from_env
agent = agent_from_env()  # writes to AGENT_TRACES: set it per run
results = agent.run_batch(golden_items)
records = [r.to_dict() for r in results]
```

## User study

Traces of study sessions contain the questions participants type. Before a session, note the time or move the file aside; after it, keep only the lines of the study's `session_id`s for analysis, and delete the file when the study data is deleted.
