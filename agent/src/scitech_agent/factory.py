"""Build the configured agent from environment variables (W4-D2-DAT-1).

`agent_from_env()` wires `Agent` to the retriever named by `RETRIEVER` and to the LLM of
`LLM_BASE_URL` / `LLM_MODEL`, with `RETRIEVAL_TOP_K` and `RETRIEVAL_MIN_SCORE`. A setting that
stops the agent from being built raises `AgentError` with the contract code the user should see
(`llm_unavailable` for the LLM settings, `retrieval_failed` for the retriever, `internal` for the
agent settings); the cause goes to the log only. Nothing here contacts Qdrant or the LLM server,
and the embedding model loads on the first search.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

from scitech_agent.agent import ERROR_MESSAGES, Agent, AgentConfig
from scitech_agent.events import AgentError
from scitech_agent.llm import LLMConfigError, OpenAICompatibleLLM
from scitech_agent.retrieval.hybrid import retriever_from_env

logger = logging.getLogger(__name__)


def agent_from_env(env: Mapping[str, str] | None = None) -> Agent:
    """The agent of `RETRIEVER`, `RETRIEVAL_*` and `LLM_*`. Raises `AgentError` if it cannot be
    built (missing or invalid settings, no BM25 index)."""
    env = os.environ if env is None else env
    try:
        config = AgentConfig.from_env(env)
    except ValueError as exc:
        raise _startup_error("internal", "agent settings", exc) from exc
    try:  # before the retriever: a missing LLM setting fails without loading the BM25 index
        llm = OpenAICompatibleLLM.from_env(env)
    except LLMConfigError as exc:
        raise _startup_error("llm_unavailable", "LLM settings", exc) from exc
    try:
        retriever = retriever_from_env(env)
    except Exception as exc:  # unknown RETRIEVER, missing or unreadable BM25 index ...
        llm.close()
        raise _startup_error("retrieval_failed", "retriever", exc) from exc
    logger.info("agent ready: retriever %s, LLM %s", type(retriever).__name__, llm.describe())
    return Agent(retriever, llm, config)


def _startup_error(code: str, what: str, exc: Exception) -> AgentError:
    logger.error("cannot build the agent (%s): %s", what, exc)
    return AgentError(code, ERROR_MESSAGES[code])
