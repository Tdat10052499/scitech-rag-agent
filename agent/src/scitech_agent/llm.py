"""LLM client (W2-D1-DAT-1): the one module that talks to the language model.

Contract: `docs/contracts/llm-client.md`. Every call goes to an OpenAI-compatible Chat Completions
endpoint (`POST {LLM_BASE_URL}/chat/completions`), so the backend can switch between Ollama or
vLLM on a remote GPU (through a tunnel), a local server and a hosted API by changing three
environment variables. No other code imports an LLM SDK or calls the endpoint directly.

- `OpenAICompatibleLLM`: `chat()` returns the whole answer, `stream_chat()` yields text fragments.
  Configurable timeout; limited retries with exponential backoff on connection errors, timeouts,
  HTTP 408/429 and 5xx. A stream is only retried before its first fragment, so text is never
  duplicated. Failures raise `LLMError` subclasses whose `code` is a contract `Error.code`.
- `FakeLLM`: scripted outputs for tests; never touches the network.

Manual check against a running server (runbook `docs/runbooks/llm-serving.md`, section 2):
    python -m scitech_agent.llm "What is retrieval-augmented generation?" --stream
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

Message = Mapping[str, str]  # {"role": "system" | "user" | "assistant", "content": "..."}

DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 512
# Retried: timeout, rate limit, server and gateway errors. Cloudflare answers 52x/530 when the
# quick tunnel or the Kaggle server behind it is gone (runbook `docs/runbooks/llm-serving.md`).
RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 530})

logger = logging.getLogger(__name__)


# --- Errors -------------------------------------------------------------------------------------


class LLMError(Exception):
    """An LLM call failed. `code` is the contract `Error.code` the backend should send."""

    code = "internal"


class LLMUnavailableError(LLMError):
    """The endpoint cannot be reached or keeps failing (server down, tunnel gone, 5xx, 429)."""

    code = "llm_unavailable"


class LLMTimeoutError(LLMError):
    """The endpoint did not answer within the configured timeout."""

    code = "timeout"


class LLMConfigError(LLMError, ValueError):
    """Required configuration is missing or invalid."""


# --- Configuration ------------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    timeout: float = 60.0  # seconds without data from the server before giving up
    max_retries: int = 2  # retries after the first attempt
    backoff: float = 0.5  # first retry pause in seconds, doubled for each retry

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMConfig:
        """Read `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT`, `LLM_MAX_RETRIES`."""
        env = os.environ if env is None else env
        missing = [k for k in ("LLM_BASE_URL", "LLM_MODEL") if not env.get(k, "").strip()]
        if missing:
            raise LLMConfigError(f"missing environment variable(s): {', '.join(missing)}")
        try:
            timeout = float(env.get("LLM_TIMEOUT") or 60)
            max_retries = int(env.get("LLM_MAX_RETRIES") or 2)
        except ValueError as exc:
            raise LLMConfigError(f"LLM_TIMEOUT / LLM_MAX_RETRIES must be numbers: {exc}") from None
        if not env["LLM_BASE_URL"].strip().startswith(("http://", "https://")):
            raise LLMConfigError("LLM_BASE_URL must start with http:// or https://")
        if timeout <= 0 or max_retries < 0:
            raise LLMConfigError("LLM_TIMEOUT must be > 0 and LLM_MAX_RETRIES >= 0")
        return cls(
            base_url=env["LLM_BASE_URL"].strip().rstrip("/"),
            # Local servers such as Ollama ignore the key, so a placeholder is accepted.
            api_key=env.get("LLM_API_KEY", "").strip() or "not-needed",
            model=env["LLM_MODEL"].strip(),
            timeout=timeout,
            max_retries=max_retries,
        )


# --- Interface ----------------------------------------------------------------------------------


class LLMClient(Protocol):
    model: str

    def chat(
        self,
        messages: Sequence[Message],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """Return the assistant's whole answer."""
        ...

    def stream_chat(
        self,
        messages: Sequence[Message],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Iterator[str]:
        """Yield the answer as text fragments, in order."""
        ...


def _check_messages(messages: Sequence[Message]) -> list[dict[str, str]]:
    if not messages:
        raise ValueError("messages must not be empty")
    out = []
    for m in messages:
        if not isinstance(m.get("role"), str) or not isinstance(m.get("content"), str):
            raise ValueError(f"each message needs string 'role' and 'content': {m!r}")
        out.append({"role": m["role"], "content": m["content"]})
    return out


# --- Real client --------------------------------------------------------------------------------


class OpenAICompatibleLLM:
    """Client for an OpenAI-compatible Chat Completions endpoint, built on `httpx`."""

    def __init__(
        self,
        config: LLMConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.model = config.model
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=config.base_url,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=httpx.Timeout(config.timeout, connect=min(config.timeout, 10.0)),
            transport=transport,
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> OpenAICompatibleLLM:
        return cls(LLMConfig.from_env(env))

    def describe(self) -> dict[str, Any]:
        """Settings to record with experiment results. Leaves out the key and the URL (a tunnel
        URL must not be committed, see the runbook)."""
        return {
            "model": self.config.model,
            "timeout": self.config.timeout,
            "max_retries": self.config.max_retries,
        }

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OpenAICompatibleLLM:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _body(
        self, messages: Sequence[Message], temperature: float, max_tokens: int, stream: bool
    ) -> dict[str, Any]:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be > 0")
        return {
            "model": self.config.model,
            "messages": _check_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    def chat(
        self,
        messages: Sequence[Message],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        body = self._body(messages, temperature, max_tokens, stream=False)

        def call() -> str:
            response = self._http.post("/chat/completions", json=body)
            _raise_for_status(response.status_code, response.text)
            try:
                return response.json()["choices"][0]["message"].get("content") or ""
            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
                raise LLMError(f"unexpected response from the LLM endpoint: {exc!r}") from None

        return self._with_retries(call)

    def stream_chat(
        self,
        messages: Sequence[Message],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Iterator[str]:
        body = self._body(messages, temperature, max_tokens, stream=True)
        attempt = 0
        while True:
            started = False
            try:
                with self._http.stream("POST", "/chat/completions", json=body) as response:
                    if response.status_code >= 400:
                        _raise_for_status(response.status_code, response.read().decode())
                    for fragment in _sse_fragments(response.iter_lines()):
                        started = True
                        yield fragment
                return
            except (httpx.HTTPError, _RetryableStatus) as exc:
                if started or attempt >= self.config.max_retries:
                    raise _to_llm_error(exc) from exc
                logger.warning("LLM stream attempt %d failed (%s); retrying", attempt + 1, exc)
            self._sleep(self.config.backoff * 2**attempt)
            attempt += 1

    def _with_retries(self, call: Callable[[], str]) -> str:
        for attempt in range(self.config.max_retries + 1):
            try:
                return call()
            except (httpx.HTTPError, _RetryableStatus) as exc:
                if attempt >= self.config.max_retries:
                    raise _to_llm_error(exc) from exc
                logger.warning("LLM attempt %d failed (%s); retrying", attempt + 1, exc)
            self._sleep(self.config.backoff * 2**attempt)
        raise AssertionError("unreachable")


class _RetryableStatus(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status


def _error_detail(text: str) -> str:
    """The server's error message, from an OpenAI-style `{"error": {"message": ...}}` body."""
    try:
        error = json.loads(text).get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
    except (ValueError, AttributeError):
        pass
    return text.strip()[:300]


def _raise_for_status(status: int, text: str) -> None:
    if status < 400:
        return
    if status in RETRY_STATUSES:
        raise _RetryableStatus(status, _error_detail(text))
    # Other 4xx: bad request, wrong key, unknown model... retrying will not help.
    raise LLMError(f"LLM endpoint returned HTTP {status}: {_error_detail(text)}")


def _to_llm_error(exc: Exception) -> LLMError:
    if isinstance(exc, httpx.TimeoutException) or (
        isinstance(exc, _RetryableStatus) and exc.status == 408
    ):
        return LLMTimeoutError(f"LLM endpoint timed out: {exc}")
    return LLMUnavailableError(f"LLM endpoint unavailable: {exc}")


def _sse_fragments(lines: Iterable[str]) -> Iterator[str]:
    """Text fragments from an OpenAI-style Chat Completions event stream."""
    for line in lines:
        if not line.startswith("data:"):
            continue  # blank separators, comments (": keep-alive"), "event:" lines
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            return
        try:
            chunk = json.loads(data)
        except ValueError:
            detail = data[:200]
            raise LLMError(f"malformed stream chunk from the LLM endpoint: {detail!r}") from None
        if chunk.get("error"):
            raise LLMError(f"LLM endpoint error during the stream: {_error_detail(data)}")
        for choice in chunk.get("choices") or []:
            text = (choice.get("delta") or {}).get("content")
            if text:
                yield text


# --- Fake for tests -----------------------------------------------------------------------------

Script = str | Exception | Callable[[list[dict[str, str]]], str]


@dataclass(frozen=True)
class LLMCall:
    messages: list[dict[str, str]]
    temperature: float
    max_tokens: int
    stream: bool


class FakeLLM:
    """Scripted LLM for tests. Each call consumes the next script item: a string is the answer,
    an exception is raised, a callable gets the messages and returns the answer. When the script
    is used up, `default` is answered (or an error is raised if there is none). Every call is
    recorded in `calls`."""

    def __init__(
        self,
        outputs: Iterable[Script] = (),
        *,
        default: str | None = None,
        model: str = "fake-llm",
    ) -> None:
        self.model = model
        self.outputs = list(outputs)
        self.default = default
        self.calls: list[LLMCall] = []

    def _next(
        self, messages: Sequence[Message], temperature: float, max_tokens: int, stream: bool
    ) -> str:
        checked = _check_messages(messages)
        self.calls.append(LLMCall(checked, temperature, max_tokens, stream))
        if self.outputs:
            item = self.outputs.pop(0)
        elif self.default is not None:
            item = self.default
        else:
            raise AssertionError("FakeLLM: no scripted output left")
        if isinstance(item, Exception):
            raise item
        return item(checked) if callable(item) else item

    def chat(
        self,
        messages: Sequence[Message],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        return self._next(messages, temperature, max_tokens, stream=False)

    def stream_chat(
        self,
        messages: Sequence[Message],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Iterator[str]:
        text = self._next(messages, temperature, max_tokens, stream=True)
        return iter(split_fragments(text))

    def describe(self) -> dict[str, Any]:
        return {"model": self.model}


def split_fragments(text: str) -> list[str]:
    """Split text into word-sized fragments that join back to the same text."""
    fragments, current = [], ""
    for ch in text:
        if ch.isspace() and current and not current[-1].isspace():
            fragments.append(current)
            current = ""
        current += ch
    if current:
        fragments.append(current)
    return fragments


# --- Manual check -------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scitech_agent.llm",
        description="Send one prompt to the LLM endpoint configured by the LLM_* variables.",
    )
    parser.add_argument("prompt")
    parser.add_argument("--stream", action="store_true", help="use stream_chat")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=200)
    args = parser.parse_args(argv)
    messages = [{"role": "user", "content": args.prompt}]
    try:
        llm = OpenAICompatibleLLM.from_env()
    except LLMConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"# {json.dumps(llm.describe())} temperature={args.temperature} "
        f"max_tokens={args.max_tokens} stream={args.stream}",
        file=sys.stderr,
    )
    started = time.perf_counter()
    first: float | None = None
    try:
        with llm:
            if args.stream:
                for fragment in llm.stream_chat(messages, args.temperature, args.max_tokens):
                    first = first or time.perf_counter() - started
                    print(fragment, end="", flush=True)
                print()
            else:
                print(llm.chat(messages, args.temperature, args.max_tokens))
    except LLMError as exc:
        print(f"error ({exc.code}): {exc}", file=sys.stderr)
        return 1
    total = time.perf_counter() - started
    ttft = f"first fragment {first:.2f} s, " if first is not None else ""
    print(f"# {ttft}total {total:.2f} s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
