"""Tests of the LLM client (W2-D1-DAT-1). No network: the real client runs against an
`httpx.MockTransport`, everything else uses `FakeLLM`."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator

import httpx
import pytest

from scitech_agent.llm import (
    FakeLLM,
    LLMConfig,
    LLMConfigError,
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
    OpenAICompatibleLLM,
    main,
    split_fragments,
)

MESSAGES = [{"role": "user", "content": "What is RAG?"}]
ENV = {"LLM_BASE_URL": "http://llm.test/v1/", "LLM_API_KEY": "secret-key", "LLM_MODEL": "m-1"}


def make_client(
    handler: Callable[[httpx.Request], httpx.Response], max_retries: int = 2
) -> tuple[OpenAICompatibleLLM, list[float]]:
    pauses: list[float] = []
    config = LLMConfig(
        base_url="http://llm.test/v1", api_key="secret-key", model="m-1", max_retries=max_retries
    )
    client = OpenAICompatibleLLM(
        config, transport=httpx.MockTransport(handler), sleep=pauses.append
    )
    return client, pauses


def completion(text: str) -> httpx.Response:
    message = {"role": "assistant", "content": text}
    return httpx.Response(200, json={"choices": [{"message": message}]})


def sse(*fragments: str, done: bool = True) -> bytes:
    lines = [": keep-alive", ""]
    for f in fragments:
        chunk = {"choices": [{"index": 0, "delta": {"content": f}}]}
        lines += [f"data: {json.dumps(chunk)}", ""]
    lines += ['data: {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}', ""]
    if done:
        lines += ["data: [DONE]", ""]
    return "\n".join(lines).encode()


# --- Configuration ------------------------------------------------------------------------------


def test_config_from_env_reads_contract_variables() -> None:
    config = LLMConfig.from_env({**ENV, "LLM_TIMEOUT": "12.5", "LLM_MAX_RETRIES": "0"})
    assert config.base_url == "http://llm.test/v1"  # trailing slash removed
    assert (config.model, config.timeout, config.max_retries) == ("m-1", 12.5, 0)
    assert "secret-key" not in repr(config)


def test_config_defaults_and_placeholder_key() -> None:
    config = LLMConfig.from_env({"LLM_BASE_URL": "http://x/v1", "LLM_MODEL": "m"})
    assert (config.api_key, config.timeout, config.max_retries) == ("not-needed", 60.0, 2)


@pytest.mark.parametrize(
    "env",
    [
        {"LLM_MODEL": "m"},
        {"LLM_BASE_URL": "http://x/v1", "LLM_MODEL": " "},
        {**ENV, "LLM_TIMEOUT": "soon"},
        {**ENV, "LLM_TIMEOUT": "0"},
        {**ENV, "LLM_MAX_RETRIES": "-1"},
    ],
)
def test_config_errors_are_clear(env: dict[str, str]) -> None:
    with pytest.raises(LLMConfigError):
        LLMConfig.from_env(env)


def test_describe_leaves_out_key_and_url() -> None:
    client, _ = make_client(lambda r: completion("x"))
    described = json.dumps(client.describe())
    assert "m-1" in described
    assert "secret-key" not in described and "llm.test" not in described


# --- chat ---------------------------------------------------------------------------------------


def test_chat_sends_openai_request_and_returns_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return completion("RAG combines retrieval with generation.")

    client, _ = make_client(handler)
    assert client.chat(MESSAGES, temperature=0.2, max_tokens=50) == (
        "RAG combines retrieval with generation."
    )
    request = seen[0]
    assert request.method == "POST"
    assert request.url == "http://llm.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer secret-key"
    assert json.loads(request.content) == {
        "model": "m-1",
        "messages": MESSAGES,
        "temperature": 0.2,
        "max_tokens": 50,
        "stream": False,
    }


def test_chat_retries_5xx_then_succeeds() -> None:
    responses = iter([httpx.Response(503), httpx.Response(502), completion("ok")])
    client, pauses = make_client(lambda r: next(responses))
    assert client.chat(MESSAGES) == "ok"
    assert pauses == [0.5, 1.0]  # exponential backoff


def test_chat_gives_up_after_max_retries() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, json={"error": {"message": "boom"}})

    client, _ = make_client(handler, max_retries=2)
    with pytest.raises(LLMUnavailableError, match="boom") as info:
        client.chat(MESSAGES)
    assert len(calls) == 3
    assert info.value.code == "llm_unavailable"


def test_unreachable_endpoint_is_llm_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client, pauses = make_client(handler, max_retries=1)
    with pytest.raises(LLMUnavailableError, match="unavailable"):
        client.chat(MESSAGES)
    assert len(pauses) == 1


def test_timeout_maps_to_timeout_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    client, _ = make_client(handler, max_retries=0)
    with pytest.raises(LLMTimeoutError) as info:
        client.chat(MESSAGES)
    assert info.value.code == "timeout"


def test_client_error_is_not_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404, json={"error": {"message": 'model "m-1" not found'}})

    client, _ = make_client(handler)
    with pytest.raises(LLMError, match="not found") as info:
        client.chat(MESSAGES)
    assert len(calls) == 1
    assert type(info.value) is LLMError and info.value.code == "internal"


def test_malformed_response_is_llm_error() -> None:
    client, _ = make_client(lambda r: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(LLMError, match="unexpected response"):
        client.chat(MESSAGES)


@pytest.mark.parametrize("messages", [[], [{"role": "user"}], [{"role": "user", "content": 1}]])
def test_invalid_messages_are_rejected_before_any_call(messages: list) -> None:
    client, _ = make_client(lambda r: pytest.fail("no request expected"))
    with pytest.raises(ValueError):
        client.chat(messages)


# --- stream_chat --------------------------------------------------------------------------------


def test_stream_chat_yields_fragments_in_order() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=sse("RAG ", "retrieves", " evidence."))

    client, _ = make_client(handler)
    assert list(client.stream_chat(MESSAGES)) == ["RAG ", "retrieves", " evidence."]
    assert json.loads(seen[0].content)["stream"] is True


def test_stream_chat_ends_without_done_marker() -> None:
    client, _ = make_client(lambda r: httpx.Response(200, content=sse("a", "b", done=False)))
    assert "".join(client.stream_chat(MESSAGES)) == "ab"


def test_stream_chat_retries_before_first_fragment() -> None:
    responses = iter([httpx.Response(503), httpx.Response(200, content=sse("ok"))])
    client, pauses = make_client(lambda r: next(responses))
    assert list(client.stream_chat(MESSAGES)) == ["ok"]
    assert pauses == [0.5]


class _BreaksAfterFirstChunk(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        yield b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
        raise httpx.ReadError("connection reset")


def test_stream_chat_does_not_retry_after_text_was_sent() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, stream=_BreaksAfterFirstChunk())

    client, _ = make_client(handler)
    received = []
    with pytest.raises(LLMUnavailableError):
        for fragment in client.stream_chat(MESSAGES):
            received.append(fragment)
    assert received == ["Hello"]
    assert len(calls) == 1  # a retry would repeat "Hello"


def test_stream_chat_error_event_in_stream() -> None:
    body = b'data: {"error": {"message": "out of memory"}}\n\n'
    client, _ = make_client(lambda r: httpx.Response(200, content=body))
    with pytest.raises(LLMError, match="out of memory"):
        list(client.stream_chat(MESSAGES))


def test_stream_chat_client_error_not_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    client, _ = make_client(handler)
    with pytest.raises(LLMError, match="invalid api key"):
        list(client.stream_chat(MESSAGES))
    assert len(calls) == 1


# --- FakeLLM ------------------------------------------------------------------------------------


def test_fake_llm_follows_script_and_records_calls() -> None:
    llm = FakeLLM(["first answer", lambda msgs: f"echo: {msgs[-1]['content']}"])
    assert llm.chat(MESSAGES, temperature=0.3, max_tokens=10) == "first answer"
    assert "".join(llm.stream_chat(MESSAGES)) == "echo: What is RAG?"
    assert [(c.temperature, c.max_tokens, c.stream) for c in llm.calls] == [
        (0.3, 10, False),
        (0.0, 512, True),
    ]
    assert llm.calls[0].messages == MESSAGES


def test_fake_llm_streams_several_fragments() -> None:
    fragments = list(FakeLLM(["Transformers use self-attention [1]."]).stream_chat(MESSAGES))
    assert len(fragments) > 1
    assert "".join(fragments) == "Transformers use self-attention [1]."


def test_fake_llm_raises_scripted_errors() -> None:
    llm = FakeLLM([LLMUnavailableError("gpu session gone")])
    with pytest.raises(LLMUnavailableError):
        llm.chat(MESSAGES)


def test_fake_llm_default_and_exhaustion() -> None:
    assert FakeLLM(default="same").chat(MESSAGES) == "same"
    with pytest.raises(AssertionError, match="no scripted output"):
        FakeLLM().chat(MESSAGES)


@pytest.mark.parametrize("text", ["", "one", "  leading and  double  spaces\n", "a\nb c"])
def test_split_fragments_round_trips(text: str) -> None:
    assert "".join(split_fragments(text)) == text


# --- Manual-check CLI ---------------------------------------------------------------------------


def test_cli_reports_missing_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert main(["hello"]) == 2
    assert "LLM_BASE_URL" in capsys.readouterr().err
