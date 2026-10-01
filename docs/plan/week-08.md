# Week 8: Delivery (2026-11-23 to 2026-11-27)

Goal: the final report, presentation and a reproducible `v1.0` are delivered.

Gate (Friday, final): report complete in `docs/report/` (and exported in the instructor's format); slides and demo video ready; a clean clone reproduces the app from the README; tag `v1.0`; submission done.

Rule this week: code changes only for P0 bugs found in the reproduction check, through PRs as usual.

## W8-D1
Monday 2026-11-23 · D36

### DAT (@Tdat10052499)

#### W8-D1-DAT-1 Report: introduction, architecture, agent
- Module: `docs/report/01-introduction.md`, `docs/report/03-system.md`
- Do: problem, goals and scope; architecture (layers, request flow, contracts); agent design (rewrite, decompose, evidence check, follow-ups) with the design decisions (ADRs) and their reasons.
- Done when: drafts in a PR.
- Depends on: W7-D5-DAT-1

### FAO (@F4ol4n)

#### W8-D1-FAO-1 Report: data chapter final edit
- Module: `docs/report/02-data.md`
- Do: tighten text to the page budget; check every number has a source (report file or run).
- Done when: chapter approved by DAT.
- Depends on: W7-D4-FAO-1

### LDN (@Yui-Mika)

#### W8-D1-LDN-1 Report: evaluation and user interface
- Module: `docs/report/04-evaluation.md`, `docs/report/05-interface.md`
- Do: condense `final.md` into the report chapter (keep sample sizes, methods, limitations); describe the UI with screenshots.
- Done when: drafts in a PR.
- Depends on: W7-D5-LDN-1

## W8-D2
Tuesday 2026-11-24 · D37

### DAT (@Tdat10052499)

#### W8-D2-DAT-1 [blocking] Clean-clone reproduction check
- Do: on a fresh folder (or a teammate's machine): clone, follow README only, `make up`, build a `--limit` index, ask 3 questions. Fix README gaps; P0 code fixes via PR.
- Done when: the run succeeds with the README as the only guide; notes in the tracking issue.
- Depends on: W6-D3-DAT-1

### FAO (@F4ol4n)

#### W8-D2-FAO-1 Report: conclusion, limitations, future work (draft)
- Module: `docs/report/06-conclusion.md`
- Do: summary of results per research question, limitations (data scope, small samples, model size, judge bias), future work (from error analyses).
- Done when: draft in a PR reviewed by LDN.
- Depends on: W7-D5-LDN-1

### LDN (@Yui-Mika)

#### W8-D2-LDN-1 Figures and tables
- Do: produce final charts (retrieval comparison, ablations, latency/scaling, user ratings) with consistent style, readable labels and units; put sources under `docs/report/figures/` with the script that made them.
- Done when: figures referenced in the chapters.
- Depends on: W8-D1-LDN-1, W7-D2-FAO-1

## W8-D3
Wednesday 2026-11-25 · D38

### DAT (@Tdat10052499)

#### W8-D3-DAT-1 Demo script and final demo video
- Do: 3-5 minute demo script (question, cited answer, follow-up, refusal case, data page); record the final video as fallback for the live demo.
- Done when: script in `docs/report/demo-script.md`; video link in the tracking issue.
- Depends on: W8-D2-DAT-1

### FAO (@F4ol4n)

#### W8-D3-FAO-1 Slides: data and big-data part
- Do: 3-4 slides on data volume, pipeline, engine choice, incremental ingestion and scaling numbers.
- Done when: slides added to the shared deck.
- Depends on: W8-D1-FAO-1

### LDN (@Yui-Mika)

#### W8-D3-LDN-1 Slides: deck structure, evaluation and UI part
- Do: create the deck structure (title, problem, architecture, data, agent, evaluation, demo, limitations, conclusion) and write the evaluation and UI slides; assign the other sections to DAT and FAO.
- Done when: deck shared with all sections assigned.
- Depends on: W8-D2-LDN-1

## W8-D4
Thursday 2026-11-26 · D39

### DAT (@Tdat10052499)

#### W8-D4-DAT-1 Dry run and final review
- Do: full presentation dry run with timing; collect fixes; final review pass of the whole report for consistency (terms from `docs/02-glossary.md`, numbers matching `final.md`).
- Done when: fix list assigned and done by end of day.
- Depends on: W8-D3-DAT-1, W8-D3-FAO-1, W8-D3-LDN-1

### FAO (@F4ol4n)

#### W8-D4-FAO-1 Repository clean-up
- Do: remove dead code and stale TODOs in `pipelines/`; make sure `pipelines/README.md` and runbooks match the final code.
- Done when: PR merged.
- Depends on: W8-D2-DAT-1

### LDN (@Yui-Mika)

#### W8-D4-LDN-1 Report assembly and export
- Do: assemble chapters in order, add references and appendix (golden-set description, prompts, configs), export to the instructor's required format.
- Done when: exported file reviewed by DAT.
- Depends on: W8-D2-FAO-1, W8-D2-LDN-1, W8-D1-DAT-1

## W8-D5
Friday 2026-11-27 · D40 · Final gate

### DAT (@Tdat10052499)

#### W8-D5-DAT-1 Release v1.0 and submission
- Do: merge last PRs; tag `v1.0` with release notes (features, how to run, known limitations); submit report, slides, video and repo link as the instructor requires.
- Done when: submission confirmed; release published.
- Depends on: W8-D4-DAT-1, W8-D4-LDN-1

### FAO (@F4ol4n)

#### W8-D5-FAO-1 Final journal and retrospective input
- Do: complete your journal; write 5 lines of retrospective (what worked, what to change).
- Done when: merged.
- Depends on: none

### LDN (@Yui-Mika)

#### W8-D5-LDN-1 Final journal and retrospective input
- Do: complete your journal; write 5 lines of retrospective; archive user-study raw data according to the consent you gave participants.
- Done when: merged.
- Depends on: none
