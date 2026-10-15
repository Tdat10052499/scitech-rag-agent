# Golden set format

The golden set is the list of questions we use to measure the system (see [`../PLAN.md`](../PLAN.md), section 3). This file says exactly how one item is written, so that the person writing it, the person checking it, and the scripts that read it all agree.

Items live in `golden.jsonl`: one JSON object per line, UTF-8, no trailing commas, no comments.

## Fields

| Field | Required | Type | Meaning |
|---|---|---|---|
| `id` | yes | string | `gs-NNN`, three digits, unique, never reused. Items 001-030 are `dev`, 031-060 are `test`. Unanswerable items use `gs-uNN`. |
| `question` | yes | string | The question as a user would type it. One question, no history needed (except `follow_up`). |
| `type` | yes | string | One of `factual`, `explanatory`, `comparison`, `multi_hop`, `follow_up`, `unanswerable`. |
| `relevant_doc_ids` | yes | list of strings | arXiv ids (no version suffix) of the papers whose title/abstract is needed to answer. Empty list only when `type` is `unanswerable`. |
| `reference_answer` | yes | string | A short correct answer written from the abstracts, 1-3 sentences. For `unanswerable`, write why the corpus cannot answer. |
| `notes` | yes | string | Starts with the question style: `plain` (everyday wording), `expert` (technical terms) or `specific` (aimed at one paper). Then where the answer is in the abstract. One or two sentences. |
| `author` | yes | string | `LDN`, `FAO` or `DAT`. |
| `split` | yes | string | `dev` or `test`. |
| `language` | no | string | `en` (default) or `vi`. |
| `history` | only for `follow_up` | list of objects | Earlier turns, each `{"role": "user" or "assistant", "content": "..."}`, oldest first. |
| `standalone_query` | only for `follow_up` | string | The question rewritten so it needs no history; used to check query rewriting. |

## Rules

1. `doc_id` is the arXiv id without a version suffix: `2401.03205`, not `2401.03205v2`. Old-style ids keep the slash: `cs/0501001`. This is the same `doc_id` as in `docs/contracts/chunk.schema.json`.
2. Every id in `relevant_doc_ids` must exist in the corpus (the sample while we only have the sample; the full snapshot afterwards).
3. A question must be answerable from titles and abstracts only, because that is all the corpus contains (ADR 0003). Do not write questions that need the full text.
4. The question must not copy the abstract's wording so closely that keyword search trivially wins; paraphrase.
5. `comparison` and `multi_hop` items list two or more ids. `factual` and `explanatory` usually list one.
6. `reference_answer` states only what the abstracts say. It is not checked against outside knowledge.
7. `unanswerable` items: the topic looks related to the corpus but no paper answers it. Before adding one, search the corpus to confirm. They are counted separately and excluded from recall@k and MRR.
8. Once an item is in the `test` split, do not edit its question or answer after results have been produced on it. Fix typos only, and say so in the PR.
9. The corpus is much larger than the sample, so other papers may answer a question too. `relevant_doc_ids` lists the documents that are needed to give the reference answer, not every paper on the topic. After a retrieval run, the top-10 results of all retrievers that are not in the list are read once by the item's author, and any that really contain the answer are added (pooling), for all retrievers alike; the PR says which items changed.

## Types

- `factual`: one fact in one abstract (a number, a name, a finding).
- `explanatory`: asks how or why; the answer is a short explanation.
- `comparison`: asks how two methods or papers differ; needs two documents.
- `multi_hop`: the answer combines information from two or more documents.
- `follow_up`: only makes sense after an earlier turn; carries `history` and `standalone_query`.
- `unanswerable`: no supporting paper in the corpus; the correct behaviour is to say so.

## Example lines

```json
{"id": "gs-002", "question": "Is it always better to give an AI more retrieved documents when it answers a question?", "type": "explanatory", "relevant_doc_ids": ["2410.05983"], "reference_answer": "No. For many long-context models, answer quality first improves and then declines as more passages are retrieved, because retrieved \"hard negatives\" (irrelevant passages) hurt.", "notes": "plain. Answer is in the abstract of 2410.05983. Other papers may say similar things (see the pooling rule in FORMAT.md).", "author": "LDN", "split": "dev"}
{"id": "gs-009", "question": "What is In-Context RALM, and why is it easier to deploy than other retrieval-augmented language models?", "type": "explanatory", "relevant_doc_ids": ["2302.00083"], "reference_answer": "In-Context RALM leaves the language model unchanged and simply prepends retrieved grounding documents to the input, with no extra training. Other retrieval-augmented approaches modify the model architecture, which complicates deployment; this one works with off-the-shelf retrievers and even with API-only models.", "notes": "specific. Names the method. Answer is in the abstract of 2302.00083, and the idea matches how our own system supplies retrieved chunks to the LLM.", "author": "LDN", "split": "dev"}
```

## Checking a file

Before opening a PR that changes `golden.jsonl`, run the checker (added with the harness in W2-D4; until then, parse each line with `python -m json.tool` and check the rules above by hand):

- every line is valid JSON and has all required fields;
- `id` values are unique, `type` and `split` use allowed values;
- every id in `relevant_doc_ids` is in the corpus file;
- `follow_up` items have `history` and `standalone_query`; `unanswerable` items have an empty `relevant_doc_ids`.

A second person (FAO for items written by LDN) checks about three random items per batch: is the question answerable from the listed abstracts, and does the reference answer match?
