"""Follow-up suggestions (W4-D3-DAT-1).

After the answer, one non-streamed LLM call (`prompts/followups.md`) suggests up to
`AgentConfig.max_followups` next questions. The user message has the recent conversation, the
sources (title and text, up to `SOURCE_CHARS`) and the answer, each in its own delimited data
block, so the questions stay grounded in what the corpus returned.

Answerable follow-ups (fix after the Space test of 2026-11-11): the corpus holds abstracts, and
abstracts often name things they do not describe ("we release a GitHub repository"). Questions
about such things were suggested and then refused. The prompt now asks for objects
`{"question", "type", "source", "quote"}` and, given the evidence, `parse_followups` keeps a
question only when its `quote` is found word for word in source `source`:

- `abstract`: the quote is the answer, so the abstract can answer the question;
- `paper`: the quote names a topic the abstract does not describe. The question is kept only
  when the full text can be read (`AGENT_FULLTEXT`, ADR 0012) and the source is an arXiv paper;
  ` (arXiv:<id>)` is then added, so the question names the paper and the agent reads its body.

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
from scitech_agent.evidence import is_refusal
from scitech_agent.retrieval import ScoredChunk

SOURCE_CHARS = 2000  # source text shown to the prompt; a chunk is at most 320 words
MIN_QUOTE_WORDS = 4  # a shorter quote ("the model") is found almost anywhere
MAX_QUESTION_CHARS = 200  # longer "questions" are explanations, not chips
MAX_QUESTION_WORDS = 20  # the prompt's limit, enforced here (#116: pasted paper titles)
_CITATION_NAME = re.compile(r"\bet al\b", re.IGNORECASE)  # "Artexte et al. (2018b)" (#116)

_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_FENCE = re.compile(r"```[a-zA-Z]*")
_ARXIV_ID = re.compile(r"\d{4}\.\d{4,5}")  # new-style ids, the ones `scitech_agent.intent` reads
_ID_SUFFIX = re.compile(r"\s*\(arXiv:\d{4}\.\d{4,5}\)(?=\s*\??$)", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                              "–": "-", "—": "-"})


# --- Prompt building --------------------------------------------------------------------------


def _snippet(text: str) -> str:
    if len(text) <= SOURCE_CHARS:
        return text
    return text[:SOURCE_CHARS].rsplit(" ", 1)[0] + " ..."


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
    """Comparison key: case, inner spacing, end punctuation and an added ` (arXiv:<id>)` do
    not make a new question."""
    question = _ID_SUFFIX.sub("", question.strip())
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


def _chip_sized(question: str) -> bool:
    """Short enough for a chip and without a reference copied from a source ("X et al.")."""
    return (
        len(question) <= MAX_QUESTION_CHARS
        and len(question.split()) <= MAX_QUESTION_WORDS
        and not _CITATION_NAME.search(question)
    )


def _normalise(text: str) -> str:
    """Comparison form for quotes: case, spacing, typographic quotes and dashes ignored."""
    text = strip_citations(text).translate(_QUOTE_CHARS).lower()
    return " ".join(text.split()).strip(" .,;:\"'")


def _grounded(
    item: Any, evidence: Sequence[ScoredChunk], fulltext: bool
) -> tuple[str, str] | None:
    """`(question, arxiv_id)` if the quote of `item` is in its source (see the module
    docstring); `arxiv_id` is set for a `paper` question only, else ``""``. None otherwise."""
    if not isinstance(item, dict):
        return None
    kind = str(item.get("type", "")).strip().lower()
    source = item.get("source")
    if kind not in ("abstract", "paper") or isinstance(source, bool):
        return None
    if not isinstance(source, (int, str)):  # 1.5 is not a source number
        return None
    try:
        n = int(source)
    except (TypeError, ValueError):
        return None
    if not 1 <= n <= len(evidence):
        return None
    chunk = evidence[n - 1]
    quote = _normalise(str(item.get("quote", "")))
    shown = _normalise(f"{chunk.title} {_snippet(chunk.text)}")
    if len(quote.split()) < MIN_QUOTE_WORDS or quote not in shown:
        return None
    question = _as_text(item)
    if kind == "abstract":
        return question, ""
    if not fulltext or chunk.source != "arxiv" or not _ARXIV_ID.fullmatch(chunk.doc_id):
        return None
    return question, chunk.doc_id


def _with_id(question: str, arxiv_id: str) -> str:
    """`question` naming the paper, so `scitech_agent.intent` reads its full text."""
    if not arxiv_id or arxiv_id in question:
        return question
    return f"{question.rstrip('?').rstrip()} (arXiv:{arxiv_id})?"


def opens_with_refusal(answer: str) -> bool:
    """True when the first sentence of `answer` says the evidence is insufficient. Such an
    answer may still cite the sources it checked ("..., while source [2] mentions X"), so it is
    not a refusal for the contract (`is_refusal` with no citation), but follow-ups grounded in
    those sources would ask for more of what they do not hold."""
    sentences = _SENTENCE_END.split(" ".join(strip_citations(answer).split()), maxsplit=1)
    return bool(sentences) and is_refusal(sentences[0])


def parse_followups(
    text: str,
    limit: int,
    asked: Iterable[str] = (),
    evidence: Sequence[ScoredChunk] | None = None,
    fulltext: bool = False,
) -> list[str]:
    """At most `limit` clean, distinct questions from the LLM output; `[]` if none can be read.
    `asked` are the questions of the conversation, which are never suggested again. With
    `evidence`, only objects whose quote is found in their source are kept (`_grounded`); plain
    strings and question lines are dropped. Without it, any question is read (prompt tests)."""
    if limit <= 0:
        return []
    items = _json_array(text)
    if items is None:
        if evidence is not None:
            return []
        lines = (_BULLET.sub("", line).strip() for line in text.splitlines())
        items = [line for line in lines if line.endswith("?")]
    seen = {_key(q) for q in asked}
    questions: list[str] = []
    for item in items:
        found = (_as_text(item), "") if evidence is None else _grounded(item, evidence, fulltext)
        if found is None:
            continue
        raw, arxiv_id = found
        question = strip_citations(_BULLET.sub("", raw)).strip().strip("\"'").strip()
        question = re.sub(r"\s+", " ", question)
        key = _key(question)
        if not key or key in seen or not _chip_sized(question):
            continue
        seen.add(key)
        questions.append(_with_id(question, arxiv_id))
        if len(questions) == limit:
            break
    return questions
