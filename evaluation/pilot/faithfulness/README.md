# Faithfulness pilot (W4-D4-LDN-1)

Tests whether two readers (FAO by hand, an LLM judge) apply the written procedure the same way,
before the full run in Week 7. The procedure is section 5 of `evaluation/PLAN.md`; the judge prompt
is `evaluation/prompts/faithfulness-judge.md`. Nothing here is a result yet.

## Files

| File | What | When |
|---|---|---|
| `questions.jsonl` | the 10 pilot questions (`id`, `question`, `type`), all from the answerable `dev` items, single turn, none of gs-001 to gs-010 (ADR 0006 used those) | committed D09 |
| `answers.jsonl` | one answer per question, from the real backend | made D12 (DAT) |
| `labels-template.csv`, `chunks.csv` | the labelling sheet and the text of the cited chunks, made from `answers.jsonl` | made D12 |
| `labels-FAO.csv` | FAO's labels | D12 |
| `labels-judge.csv` | the judge's labels | D13 (LDN) |

## 1. Make `answers.jsonl` (D12, in the integration session)

Ask the 10 questions of `questions.jsonl` once each, in a new conversation, with the settings of
the integration session (model, retriever, `k`), and save one JSON object per line:

```json
{"answer_id": "p-gs-011", "question_id": "gs-011", "answer": "<raw answer text, before any citation is removed>",
 "sources": [{"n": 1, "chunk_id": "2401.00001#0", "doc_id": "2401.00001", "text": "<chunk text as sent to the model>"}],
 "model": "...", "retriever": "...", "commit": "..."}
```

`answer` is the raw text with its `[n]` markers (an invalid `[n]` is kept; the sheet marks it).
`sources` are the passages in the order the model saw them, so `[n]` is the n-th. Commit the file
as it is, and note the Ollama version and quantisation of the model in the commit message.

## 2. Label (FAO, D12)

```powershell
$env:PYTHONPATH = "evaluation/src"
python -m scitech_eval make-sheet evaluation/pilot/faithfulness/answers.jsonl
# copy labels-template.csv to labels-FAO.csv, fill label / reason / partial_note / annotator
python -m scitech_eval check-labels evaluation/pilot/faithfulness/labels-FAO.csv
```

```bash
PYTHONPATH=evaluation/src python -m scitech_eval make-sheet evaluation/pilot/faithfulness/answers.jsonl
PYTHONPATH=evaluation/src python -m scitech_eval check-labels evaluation/pilot/faithfulness/labels-FAO.csv
```

Rules for the annotator: see `evaluation/PLAN.md` section 5. Use only the question, the sentence and
the chunk text in `chunks.csv`. Do not open the judge output and do not look anything up. A
labelling session on 10 answers (about 25 sentences) is a few hours at most; write down the time.

## 3. Judge and agreement (LDN, D13)

The judge gets one sentence per call with the prompt in `evaluation/prompts/faithfulness-judge.md`,
temperature 0, a model that is not the generator (DAT names it in `evaluation/SNAPSHOT.md`). The
agreement (raw agreement and Cohen's kappa on the sentence labels) is computed on D13 and written
in the D13 journal entry. Not written yet: the judge runner and the kappa code.

## Sentence splitting

Rule-based, in `scitech_eval/answers.py`, no extra package. A line break ends a sentence; `.`, `!`
or `?` end one when a capital letter, digit, quote or bracket follows; `[n]` markers right after the
end mark stay with the sentence before. Markers are read as the agent reads them: `[1][2]`,
`[1, 2]`, `[1; 2]` and `[1-3]` all cite sources; `x[1]`, a marker with a 0 and a range longer than
20 do not. No split after `e.g.`, `i.e.`, `et al.`, `vs.`, an initial,
or inside `25.7` or `bge-small-en-v1.5`. Tried on the 30 answers rated for ADR 0006: 69 sentences,
none cut in a wrong place by eye; two answers consist only of citation markers (`[1][2]`), which
the protocol labels *not checkable*. Whether another splitter agrees better with the labels is
decided by this pilot (PLAN.md section 9, item 5).
