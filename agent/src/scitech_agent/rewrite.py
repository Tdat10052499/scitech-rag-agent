"""Conversation-aware query rewriting (W5-D1-DAT-1).

A follow-up such as "What datasets did they test it on?" retrieves unrelated chunks when it is
searched as typed (#110). Before retrieval, one non-streamed LLM call (`prompts/rewrite.md`) turns
the message into a standalone search query from the latest turns of the session. Only retrieval
uses the rewritten query: the answer prompt still gets the message as typed, with the
conversation.

`parse_rewrite` does not trust the output: it takes the first non-empty line, drops a label
("Query:"), quotes and citation markers, and returns `None` for an empty or overlong query, so
the caller keeps the original message. The agent also keeps it when the call fails, and makes no
call when the session has no earlier turn (`Agent.rewrite`, flag `AGENT_REWRITE`).

Manual check with the real LLM (never in tests), on the follow-up items of the golden set:
`python -m scitech_agent.rewrite` prints, per item, the message, the rewritten query and the
expected `standalone_query`; `--search` also retrieves with both and shows whether a relevant
document is in the top k.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from scitech_agent.answer import ConversationTurn, _escape, format_conversation, strip_citations
from scitech_agent.llm import LLMClient, Message

MAX_QUERY_CHARS = 400  # longer output is an answer or an explanation, not a query

_FENCE = re.compile(r"```[a-zA-Z]*")
_LABEL = re.compile(
    r"^\s*(?:standalone\s+|rewritten\s+|search\s+)*(?:query|question)\s*:\s*", re.IGNORECASE
)
_QUOTES = "\"'`“”‘’"


def rewrite_user_message(message: str, history: Sequence[ConversationTurn]) -> str:
    return (
        f"Conversation so far:\n\n{format_conversation(history)}\n\n"
        f"Message:\n<message>\n{_escape(message, 'message')}\n</message>"
    )


def rewrite_messages(
    system_prompt: str, message: str, history: Sequence[ConversationTurn]
) -> list[Message]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": rewrite_user_message(message, history)},
    ]


def parse_rewrite(text: str) -> str | None:
    """The query in the LLM output, or `None` when there is none usable."""
    for line in _FENCE.sub("", text).splitlines():
        line = _LABEL.sub("", line).strip().strip(_QUOTES).strip()
        if line:
            break
    else:
        return None
    query = " ".join(strip_citations(line).split())
    if not re.search(r"\w", query) or len(query) > MAX_QUERY_CHARS:
        return None
    return query


def rewrite_query(
    llm: LLMClient,
    system_prompt: str,
    message: str,
    history: Sequence[ConversationTurn],
    *,
    temperature: float = 0.0,
    max_tokens: int = 96,
) -> str | None:
    """One LLM call; the standalone query or `None`. LLM failures raise `LLMError`."""
    text = llm.chat(
        rewrite_messages(system_prompt, message, history),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return parse_rewrite(text)


# --- Manual check -------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Turn:
    question: str
    answer: str


def golden_history(item: dict) -> list[_Turn]:
    """The `history` of a golden item (user/assistant messages) as question-answer turns."""
    turns: list[_Turn] = []
    question = None
    for entry in item.get("history", []):
        if entry.get("role") == "user":
            question = entry.get("content", "")
        elif entry.get("role") == "assistant" and question is not None:
            turns.append(_Turn(question, entry.get("content", "")))
            question = None
    return turns


def main(argv: Sequence[str] | None = None) -> int:
    from scitech_agent.agent import AgentConfig, load_prompt
    from scitech_agent.llm import LLMConfigError, LLMError, OpenAICompatibleLLM

    if hasattr(sys.stdout, "reconfigure"):  # a Windows console may not encode every query
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        prog="python -m scitech_agent.rewrite",
        description="Rewrite the follow-up golden questions with the configured LLM (LLM_*); "
        "print Markdown.",
    )
    parser.add_argument("--golden", default="evaluation/golden_set/golden.jsonl")
    parser.add_argument("--ids", default="", help="comma-separated ids (default: all follow_up)")
    parser.add_argument(
        "--search", action="store_true", help="also retrieve (RETRIEVER, RETRIEVAL_TOP_K)"
    )
    parser.add_argument("--out", default="", help="also write the Markdown to this file (UTF-8)")
    args = parser.parse_args(argv)
    lines: list[str] = []

    def emit(line: str = "") -> None:
        lines.append(line)
        print(line, flush=True)

    with open(args.golden, encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]
    ids = [i for i in args.ids.split(",") if i]
    if ids:
        by_id = {item["id"]: item for item in items}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise SystemExit(f"error: not in {args.golden}: {', '.join(missing)}")
        items = [by_id[i] for i in ids]
    else:
        items = [item for item in items if item.get("type") == "follow_up"]
    try:
        llm = OpenAICompatibleLLM.from_env()
    except LLMConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    config = AgentConfig.from_env()
    retriever = None
    if args.search:
        from scitech_agent.retrieval.hybrid import retriever_from_env

        retriever = retriever_from_env()
    prompt = load_prompt("rewrite")
    emit(f"Model: `{llm.describe()}`\n")
    failures = 0
    found = {"message": 0, "rewritten": 0}
    with llm:
        for item in items:
            history = golden_history(item)[-config.rewrite_history_turns :]
            try:
                query = rewrite_query(
                    llm,
                    prompt,
                    item["question"],
                    history,
                    temperature=config.temperature,
                    max_tokens=config.rewrite_max_tokens,
                )
            except LLMError as exc:
                failures += 1
                emit(f"### {item['id']}: error `{exc.code}`\n")
                continue
            emit(f"### {item['id']}")
            emit(f"- message: {item['question']}")
            emit(f"- rewritten: {query if query else '(unusable, original kept)'}")
            emit(f"- expected: {item.get('standalone_query', '')}")
            if retriever is not None:
                relevant = set(item.get("relevant_doc_ids", []))
                for name, text in (("message", item["question"]), ("rewritten", query)):
                    if not text:
                        continue
                    docs = [h.doc_id for h in retriever.search(text, k=config.top_k)]
                    hit = bool(relevant & set(docs))
                    found[name] += hit
                    shown = ", ".join(f"**{d}**" if d in relevant else d for d in docs)
                    emit(f"- top {config.top_k} for {name}: {shown} ({'hit' if hit else 'miss'})")
            emit()
        if retriever is not None:
            emit(
                f"Relevant document in the top {config.top_k}: message {found['message']}"
                f"/{len(items)}, rewritten {found['rewritten']}/{len(items)}"
            )
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
