"""Answer generation with citations (W4-D1-DAT-1).

The answer prompt (`prompts/answer.md`) gets the recent conversation and the numbered evidence,
each in its own delimited data block. The LLM cites a source as `[n]`, `n` being the 1-based
position of the chunk in `sources` (api.openapi.yaml). Two helpers enforce that on the output:

- `CitationFilter` runs on the streamed fragments: it drops markers whose numbers are not
  sources, writes `[1, 3]` or `[1-3]` as `[1][2][3]` (the only form the frontend links), and
  holds back at most a short unfinished marker between fragments.
- `parse_citations` maps the markers of the final text to `chunk_id`s.

A marker directly after a letter, digit or `_` (`x[0]`, code) is text, not a citation.

Manual check with the real retriever and LLM (never in tests):
`python -m scitech_agent.answer --golden evaluation/golden_set/golden.jsonl -n 5` prints, per
question, the answer, its citations and whether each cited document is in `relevant_doc_ids`,
as Markdown for a PR.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from scitech_agent.llm import Message
from scitech_agent.retrieval import ScoredChunk

_ITEM = r"\d+(?:\s*[-–]\s*\d+)?"
# Optional spaces before the marker are part of it, so a dropped marker takes them along.
_MARKER = re.compile(rf"([ \t]*)\[\s*({_ITEM}(?:\s*[,;]\s*{_ITEM})*)\s*\]")
# What may still become a marker at the end of a fragment.
_OPEN_TAIL = re.compile(r"[ \t]*(?:\[[\d\s,;\-–]*)?\Z")
_MAX_HELD = 40
_WORD_CHAR = re.compile(r"\w")
_MAX_RANGE = 20


class ConversationTurn(Protocol):
    question: str
    answer: str


@dataclass(frozen=True)
class Citation:
    number: int  # 1-based position in `sources`
    chunk_id: str


def _numbers(group: str) -> list[int]:
    numbers: list[int] = []
    for item in re.split(r"\s*[,;]\s*", group.strip()):
        bounds = [int(b) for b in re.split(r"\s*[-–]\s*", item)]
        if len(bounds) == 2 and 0 <= bounds[1] - bounds[0] < _MAX_RANGE:
            numbers.extend(range(bounds[0], bounds[1] + 1))
        elif len(bounds) == 1:
            numbers.append(bounds[0])
    return numbers


def _rewrite(match: re.Match[str], count: int, before: str) -> str:
    """Valid numbers of one marker as `[a][b]`; nothing (spaces included) when none is valid."""
    if _WORD_CHAR.match(before):
        return match.group(0)
    valid = list(dict.fromkeys(n for n in _numbers(match.group(2)) if 1 <= n <= count))
    if not valid:
        return ""
    return match.group(1) + "".join(f"[{n}]" for n in valid)


def clean_citations(text: str, count: int, before: str = "") -> str:
    """`text` with every citation marker rewritten for `count` sources. `before` is the
    character that precedes `text` (for streamed text)."""
    out: list[str] = []
    last = 0
    for match in _MARKER.finditer(text):
        start = match.start() + len(match.group(1))  # the "["
        prev = text[start - 1] if start > 0 else before
        out.append(text[last : match.start()])
        out.append(_rewrite(match, count, prev))
        last = match.end()
    out.append(text[last:])
    return "".join(out)


class CitationFilter:
    """Applies `clean_citations` to a stream of fragments; `feed` returns what can be sent now
    and `flush` the rest at the end. The joined output equals `clean_citations` of the joined
    input."""

    def __init__(self, count: int) -> None:
        self.count = count
        self._held = ""
        self._before = ""  # last character already returned

    def feed(self, fragment: str) -> str:
        text = self._held + fragment
        tail = _OPEN_TAIL.search(text)
        cut = tail.start() if tail and len(text) - tail.start() <= _MAX_HELD else len(text)
        self._held = text[cut:]
        return self._emit(text[:cut])

    def flush(self) -> str:
        text, self._held = self._held, ""
        return self._emit(text)

    def _emit(self, text: str) -> str:
        out = clean_citations(text, self.count, self._before)
        if out:
            self._before = out[-1]
        return out

    def filter(self, fragments: Iterable[str]) -> Iterator[str]:
        for fragment in fragments:
            out = self.feed(fragment)
            if out:
                yield out
        rest = self.flush()
        if rest:
            yield rest


def parse_citations(answer: str, evidence: Sequence[ScoredChunk]) -> list[Citation]:
    """Citations of `answer` in order of first use, without duplicates; numbers that are not
    sources are dropped."""
    seen: dict[int, Citation] = {}
    for match in _MARKER.finditer(answer):
        start = match.start() + len(match.group(1))
        if start > 0 and _WORD_CHAR.match(answer[start - 1]):
            continue
        for n in _numbers(match.group(2)):
            if 1 <= n <= len(evidence) and n not in seen:
                seen[n] = Citation(n, evidence[n - 1].chunk_id)
    return list(seen.values())


def strip_citations(text: str) -> str:
    """`text` without citation markers: an earlier answer's numbers refer to other sources."""
    return _MARKER.sub("", text)


# --- Prompt building --------------------------------------------------------------------------


def _escape(text: str, tag: str) -> str:
    """Data cannot open or close a `<tag>` block itself."""
    return re.sub(rf"<(/?{tag})", r"&lt;\1", text, flags=re.IGNORECASE)


def _inside_source(text: str) -> str:
    return _escape(text, "source")


def format_sources(evidence: Sequence[ScoredChunk]) -> str:
    """Numbered sources; the numbers are the citation markers `[n]` of the answer."""
    blocks = [
        f'<source id="{n}">\nTitle: {_inside_source(chunk.title)}\n'
        f"Text: {_inside_source(chunk.text)}\n</source>"
        for n, chunk in enumerate(evidence, start=1)
    ]
    return "\n\n".join(blocks)


def format_conversation(history: Sequence[ConversationTurn]) -> str:
    lines = []
    for turn in history:
        lines.append(f"User: {_escape(turn.question, 'conversation')}")
        lines.append(f"Assistant: {_escape(strip_citations(turn.answer), 'conversation')}")
    return "<conversation>\n" + "\n".join(lines) + "\n</conversation>"


def answer_user_message(
    question: str,
    evidence: Sequence[ScoredChunk],
    history: Sequence[ConversationTurn] = (),
) -> str:
    parts = []
    if history:
        parts.append(f"Conversation so far:\n\n{format_conversation(history)}")
    parts.append(f"Sources:\n\n{format_sources(evidence)}")
    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


def answer_messages(
    system_prompt: str,
    question: str,
    evidence: Sequence[ScoredChunk],
    history: Sequence[ConversationTurn] = (),
) -> list[Message]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": answer_user_message(question, evidence, history)},
    ]


# --- Manual check -------------------------------------------------------------------------------


def _golden(path: str, ids: Sequence[str], limit: int) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]
    if ids:
        by_id = {item["id"]: item for item in items}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise SystemExit(f"error: not in {path}: {', '.join(missing)}")
        return [by_id[i] for i in ids]
    return items[:limit]


def main(argv: Sequence[str] | None = None) -> int:
    from scitech_agent.agent import Agent, AgentConfig
    from scitech_agent.events import AgentError, SourcesEvent, TokenEvent
    from scitech_agent.llm import LLMConfigError, OpenAICompatibleLLM
    from scitech_agent.retrieval.hybrid import retriever_from_env

    if hasattr(sys.stdout, "reconfigure"):  # a Windows console may not encode every answer
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        prog="python -m scitech_agent.answer",
        description="Answer golden questions with the configured retriever (RETRIEVER, "
        "RETRIEVAL_*) and LLM (LLM_*); print Markdown.",
    )
    parser.add_argument("--golden", default="evaluation/golden_set/golden.jsonl")
    parser.add_argument("-n", type=int, default=5, help="first N items (ignored with --ids)")
    parser.add_argument("--ids", default="", help="comma-separated golden ids, e.g. gs-001,gs-007")
    parser.add_argument("--out", default="", help="also write the Markdown to this file (UTF-8)")
    args = parser.parse_args(argv)
    lines: list[str] = []

    def emit(line: str = "") -> None:
        lines.append(line)
        print(line, flush=True)

    items = _golden(args.golden, [i for i in args.ids.split(",") if i], args.n)
    try:
        llm = OpenAICompatibleLLM.from_env()
    except LLMConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    config = AgentConfig.from_env()
    emit(f"Model: `{llm.describe()}`; config: `{config}`\n")
    failures = 0
    with llm:
        agent = Agent(retriever_from_env(), llm, config)
        for item in items:
            started = time.perf_counter()
            evidence: list[ScoredChunk] = []
            parts: list[str] = []
            try:
                for event in agent.run(item["id"], item["question"]):
                    if isinstance(event, SourcesEvent):
                        evidence = event.chunks
                    elif isinstance(event, TokenEvent):
                        parts.append(event.text)
            except AgentError as exc:
                failures += 1
                emit(f"### {item['id']}: error `{exc.code}`\n")
                continue
            answer = "".join(parts)
            relevant = set(item.get("relevant_doc_ids", []))
            emit(
                f"### {item['id']} ({item.get('type', '')}, {time.perf_counter() - started:.1f} s)"
            )
            emit(f"**Q:** {item['question']}\n")
            emit(f"**A:** {answer}\n")
            emit("| [n] | chunk_id | cited | in relevant_doc_ids |")
            emit("|---|---|---|---|")
            cited = {c.number for c in parse_citations(answer, evidence)}
            for n, chunk in enumerate(evidence, start=1):
                mark = "yes" if n in cited else ""
                rel = "yes" if chunk.doc_id in relevant else ""
                emit(f"| {n} | `{chunk.chunk_id}` | {mark} | {rel} |")
            emit()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
