# Deck outline for the presentation of 2026-11-12

The PowerPoint skeleton `ASAP product presentation.pptx` (16 slides) is attached to the pull request that added this file. Binary files are not committed; this page lists what each slide is for, who fills it, and where its numbers come from.

How we work with it: DAT and FAO fill their slides in the attached file and send it back as an attachment in a comment. Then the content is copied into the main deck.

| # | Slide | Owner | State |
|---|---|---|---|
| 1 | Cover: ASAP (Automated Scientific Aggregation Platform) | LDN | done |
| 2 | Who presents which section | LDN | done, everyone checks |
| 3 | Problem: why we built ASAP | LDN | done |
| 4 | Architecture: system picture and request flow | DAT | to fill (placeholder) |
| 5 | Data: from 3.2 million records to a searchable index | FAO | to fill (placeholder) |
| 6 | Agent: what the agent does with a question | DAT | to fill (placeholder) |
| 7 | Evaluation: how we tested it | LDN | done |
| 8 | Question 1, retrieval | LDN | done |
| 9 | Question 2, answers | LDN | done |
| 10 | Key finding: most unsupported sentences have no citation | LDN | done |
| 11 | Can we trust the judge? | LDN | done |
| 12 | Interface: answer with sources | LDN | done |
| 13 | Interface: not enough evidence, and an error | LDN | done |
| 14 | Live demo | DAT | to fill (placeholder) |
| 15 | Limits | LDN | done |
| 16 | Conclusion | LDN draft | everyone checks |

## Sources of the numbers

- Slides 7 to 11 and 15: `evaluation/reports/final.md` (sections 1 to 5 and 8). Retrieval: hybrid recall@5 0.508, dense 0.458, BM25 0.508; recall@10 0.583, 0.492, 0.567. Faithfulness: 0.491 (MVP) and 0.527 (with rewrite). Evidence check refused 60 of 60 answerable questions. In the run with rewrite, 64 of 85 unsupported sentences have no citation, and 67 of 88 cited sentences are supported. Judge against people: 47 of 55 sentences (faithfulness), 15 of 22 answers (relevance).
- Slide 3: report chapter 1 (121,860 cs.CL records; about 730 new papers per week in the October 2026 live test).
- Slides 12 and 13: figures 5.1 to 5.3 of chapter 5. They are screenshots of the showcase page with example data and a simulated error text, not output of the agent. The slides say so.

## Notes

- RQ3 (usefulness of follow-up suggestions) is not evaluated; the user study was cancelled (ADR 0013). The slides say so and make no claim about it.
- Faithfulness means "supported by the cited passages", not "true".

Drafted with AI assistance (Claude); LDN is responsible for the content.
