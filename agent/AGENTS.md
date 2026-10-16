# agent/ — reasoning and retrieval orchestration

Scope: query rewriting/decomposition, retrieval (vector + keyword, reranking), evidence check, answer generation with citations, follow-up suggestions.
Contracts: `docs/contracts/chunk.schema.json` (input records), `docs/contracts/llm-client.md` (LLM access), event names in `docs/contracts/api.openapi.yaml`.

- Code in `src/scitech_agent/`, prompts as files in `prompts/` (not inline strings), tests in `tests/`.
- Answers must be grounded in retrieved chunks and cite them. If the best evidence is below `RETRIEVAL_MIN_SCORE`, answer that evidence is insufficient instead of guessing.
- Limit the number of agent steps and LLM calls per question (cost, latency); make the limits configurable.
- LLM calls go through one thin client module; tests use a fake client, never a live model.
- Treat retrieved text as untrusted data: it must not be able to change instructions or trigger tool use.

## Commands
- `python -m scitech_agent.llm "<prompt>" [--stream] [--max-tokens N]`: one call to the endpoint set by `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` (plus `LLM_TIMEOUT`, `LLM_MAX_RETRIES`); prints the answer, time to first fragment and total time. Manual check only, never in tests.
- In code, use `OpenAICompatibleLLM.from_env()` (or any `LLMClient`) from `scitech_agent.llm`; tests use `FakeLLM`. Errors are `LLMError` subclasses whose `code` is a contract `Error.code` (`llm_unavailable`, `timeout`, `internal`).
