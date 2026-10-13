# Week 8 (phase 8 of 8): Delivery (2026-11-04 to 2026-11-06)

> Replanned on 2026-10-13, see [ADR 0010](../decisions/0010-compressed-schedule.md). This phase has 3 working days (D20-D22). D22 is the submission day.
> Task IDs are unchanged. Lines starting with **Replan:** say what changed.

Goal: the final report, presentation and a reproducible `v1.0` are delivered.

Gate (D22, Fri 2026-11-06, final): report complete in `docs/report/` (and exported in the instructor's format); slides and demo video ready; a clean clone reproduces the app from the README; tag `v1.0`; submission done at least 3 hours before the instructor's deadline hour.

Rule this phase: code changes only for P0 bugs found in the reproduction check, through PRs as usual.

## D20
Wednesday 2026-11-04

### DAT (@Tdat10052499)

#### W8-D2-DAT-1 [blocking] Clean-clone reproduction check
- **Replan:** moved to the first morning of the phase so README gaps and P0 fixes have two days to land.
- Do: on a fresh folder (or a teammate's machine): clone, follow README only, `make up`, build a `--limit` index, ask 3 questions. Fix README gaps; P0 code fixes via PR.
- Done when: the run succeeds with the README as the only guide; notes in the tracking issue.
- Depends on: W6-D3-DAT-1

#### W8-D1-DAT-1 Report: introduction, architecture, agent
- Module: `docs/report/01-introduction.md`, `docs/report/03-system.md`
- Do: problem, goals and scope; architecture (layers, request flow, contracts); agent design (rewrite, evidence check, follow-ups) with the design decisions (ADRs, including ADR 0010 on what was cut) and their reasons.
- Done when: drafts in a PR.
- Depends on: W7-D5-DAT-1

### FAO (@F4ol4n)

#### W8-D1-FAO-1 Report: data chapter final edit
- Module: `docs/report/02-data.md`
- Do: tighten text to the page budget; check every number has a source (report file or run).
- Done when: chapter approved by DAT.
- Depends on: W7-D4-FAO-1

#### W8-D2-FAO-1 Report: conclusion, limitations, future work (draft)
- Module: `docs/report/06-conclusion.md`
- Do: summary of results per research question, limitations (data scope, small samples, model size, judge bias, features cut by ADR 0010), future work (from error analyses).
- Done when: draft in a PR reviewed by LDN.
- Depends on: W7-D5-LDN-1

### LDN (@Yui-Mika)

#### W8-D1-LDN-1 Report: evaluation and user interface
- Module: `docs/report/04-evaluation.md`, `docs/report/05-interface.md`
- Do: condense `final.md` into the report chapter (keep sample sizes, methods, limitations); describe the UI with screenshots.
- Done when: drafts in a PR.
- Depends on: W7-D5-LDN-1

#### W8-D3-LDN-1 Slides: deck structure, evaluation and UI part
- **Replan:** moved one day earlier so DAT and FAO can write their slides on D21.
- Do: create the deck structure (title, problem, architecture, data, agent, evaluation, demo, limitations, conclusion) and assign the sections to DAT and FAO today; write the evaluation and UI slides by D21 midday.
- Done when: deck shared with all sections assigned.
- Depends on: W7-D5-LDN-1

## D21
Thursday 2026-11-05

### DAT (@Tdat10052499)

#### W8-D3-DAT-1 Demo script and final demo video
- Do: 3-5 minute demo script (question, cited answer, follow-up, refusal case); record the final video as fallback for the live demo; write the agent/architecture slides.
- **Replan:** the data page is cut, so it is removed from the demo script.
- Done when: script in `docs/report/demo-script.md`; video link in the tracking issue.
- Depends on: W8-D2-DAT-1

### FAO (@F4ol4n)

#### W8-D3-FAO-1 Slides: data and big-data part
- Do: 3-4 slides on data volume, pipeline, engine choice, incremental ingestion (or why it was cut) and scaling numbers.
- Done when: slides added to the shared deck.
- Depends on: W8-D1-FAO-1

#### W8-D4-FAO-1 Repository clean-up
- Do: remove dead code and stale TODOs in `pipelines/`; make sure `pipelines/README.md` and runbooks match the final code.
- Done when: PR merged.
- Depends on: W8-D2-DAT-1

### LDN (@Yui-Mika)

#### W8-D2-LDN-1 Figures and tables
- Do: produce final charts (retrieval comparison, ablations, latency/scaling, user ratings) with consistent style, readable labels and units; put sources under `docs/report/figures/` with the script that made them.
- Done when: figures referenced in the chapters.
- Depends on: W8-D1-LDN-1, W7-D2-FAO-1

#### W8-D4-LDN-1 Report assembly and export
- Do (afternoon): assemble chapters in order, add references and appendix (golden-set description, prompts, configs), export to the instructor's required format.
- Done when: exported file reviewed by DAT (D22 morning at the latest).
- Depends on: W8-D2-FAO-1, W8-D2-LDN-1, W8-D1-DAT-1

## D22
Friday 2026-11-06 · Final gate and submission

### DAT (@Tdat10052499)

#### W8-D4-DAT-1 Dry run and final review
- Do (morning): full presentation dry run with timing; collect fixes; final review pass of the whole report for consistency (terms from `docs/02-glossary.md`, numbers matching `final.md`).
- Done when: fix list assigned and done before the release.
- Depends on: W8-D3-DAT-1, W8-D3-FAO-1, W8-D3-LDN-1

#### W8-D5-DAT-1 Release v1.0 and submission
- Do (afternoon): merge last PRs; tag `v1.0` with release notes (features, how to run, known limitations, features cut by ADR 0010); submit report, slides, video and repo link as the instructor requires, at least 3 hours before the deadline hour.
- Done when: submission confirmed; release published.
- Depends on: W8-D4-DAT-1, W8-D4-LDN-1

### FAO (@F4ol4n)

#### W8-D5-FAO-1 Final journal and retrospective input
- Do (after submission): complete your journal; write 5 lines of retrospective (what worked, what to change), including how the compressed schedule worked.
- Done when: merged.
- Depends on: none

### LDN (@Yui-Mika)

#### W8-D5-LDN-1 Final journal and retrospective input
- Do (after submission): complete your journal; write 5 lines of retrospective; archive user-study raw data according to the consent you gave participants.
- Done when: merged.
- Depends on: none

## Cut or merged in the replan
None in Week 8.
