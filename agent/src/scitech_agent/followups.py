"""Follow-up suggestions (W4-D3-DAT-1).

After the answer, one non-streamed LLM call (`prompts/followups.md`) suggests up to
`AgentConfig.max_followups` next questions as a JSON array of strings. The user message has the
recent conversation, the sources (title and the start of the text) and the answer, each in its
own delimited data block, so the questions stay grounded in what the corpus returned.

`parse_followups` does not trust the output: it takes the first JSON array of strings in the
text (code fences or a sentence around it are ignored), falls back to lines that end with `?`
when there is no array (small models sometimes drop the brackets), and returns `[]` for anything
else. It strips bullets, quotes and citation markers, and drops blanks, overlong lines,
duplicates and questions already asked in the conversation (case, spacing and end punctuation
are ignored when comparing).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from typing import Any

from scitech_agent.answer import ConversationTurn, _escape, format_conversation, strip_citations
from scitech_agent.retrieval import ScoredChunk

SNIPPET_CHARS = 300  # start of each source text shown to the prompt
MAX_QUESTION_CHARS = 200  # longer "questions" are explanations, not chips

_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_FENCE = re.compile(r"```[a-zA-Z]*")


# --- Prompt building --------------------------------------------------------------------------


def _snippet(text: str) -> str:
    if len(text) <= SNIPPET_CHARS:
        return text
    return text[:SNIPPET_CHARS].rsplit(" ", 1)[0] + " ..."


def format_source_snippets(evidence: Sequence[ScoredChunk]) -> str:
    blocks = [
        f'<source id="{n}">\nTitle: {_escape(chunk.title, "source")}\n'
        f"Text: {_escape(_snippet(chunk.text), 'source')}\n</source>"
        for n, chunk in enumerate(evidence, start=1)
    ]
    return "\n\n".join(blocks)


def followups_user_message(
    question: str,
    answer: str,
    evidence: Sequence[ScoredChunk],
    history: Sequence[ConversationTurn] = (),
    limit: int = 4,
) -> str:
    parts = []
    if history:
        parts.append(f"Conversation so far:\n\n{format_conversation(history)}")
    parts.append(f"Sources:\n\n{format_source_snippets(evidence)}")
    parts.append(f"Question: {_escape(question, 'answer')}")
    parts.append(f"<answer>\n{_escape(strip_citations(answer), 'answer')}\n</answer>")
    parts.append(f"Write at most {limit} follow-up questions.")
    return "\n\n".join(parts)


# --- Parsing ----------------------------------------------------------------------------------


def _key(question: str) -> str:
    """Comparison key: case, inner spacing and end punctuation do not make a new question."""
    return re.sub(r"\s+", " ", question).strip().rstrip("?.!").strip().lower()


def _json_array(text: str) -> list[Any] | None:
    """The first JSON array in `text` that holds a string or an object (`[1]` in a sentence is
    skipped), else the first array at all (`[]`: no suggestions), else None."""
    text = _FENCE.sub("", text)
    decoder = json.JSONDecoder()
    first: list[Any] | None = None
    for match in re.finditer(r"\[", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if not isinstance(value, list):
            continue
        if any(isinstance(item, (str, dict)) for item in value):
            return value
        if first is None:
            first = value
    return first


def _as_text(item: Any) -> str:
    if isinstance(item, dict):  # [{"question": "..."}]
        item = item.get("question", "")
    return item if isinstance(item, str) else ""


def parse_followups(text: str, limit: int, asked: Iterable[str] = ()) -> list[str]:
    """At most `limit` clean, distinct questions from the LLM output; `[]` if none can be read.
    `asked` are the questions of the conversation, which are never suggested again."""
    if limit <= 0:
        return []
    items = _json_array(text)
    if items is None:
        lines = (_BULLET.sub("", line).strip() for line in text.splitlines())
        items = [line for line in lines if line.endswith("?")]
    seen = {_key(q) for q in asked}
    questions: list[str] = []
    for item in items:
        question = strip_citations(_BULLET.sub("", _as_text(item))).strip().strip("\"'").strip()
        question = re.sub(r"\s+", " ", question)
        key = _key(question)
        if not key or key in seen or len(question) > MAX_QUESTION_CHARS:
            continue
        seen.add(key)
        questions.append(question)
        if len(questions) == limit:
            break
    return questions
