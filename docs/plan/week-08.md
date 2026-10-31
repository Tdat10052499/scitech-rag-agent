# Week 8 (phase 8 of 8): Delivery and presentation (2026-11-04 to 2026-11-10)

> Replanned on 2026-10-13, see [ADR 0010](../decisions/0010-compressed-schedule.md). D20-D22 finish the product (D22 is the internal deadline); D23-D25 prepare and give the presentation on Tuesday 2026-11-10. Sunday 2026-11-08 is a buffer day.
> Task IDs are unchanged. Lines starting with **Replan:** say what changed.

Goal: the final report, presentation and a reproducible `v1.0` are delivered, and the product is presented on 2026-11-10.

Gate (D22, Fri 2026-11-06, internal deadline): report complete in `docs/report/` and exported to PDF; demo video ready; a clean clone reproduces the app from the README; tag `v1.0`.

Presentation (D25, Tue 2026-11-10): slides final, dry run done on D24, live demo with the recorded video as fallback.

Rule this phase: code changes only for P0 bugs found in the reproduction check, through PRs as usual. After `v1.0` (D22) the code is frozen: the presentation shows `v1.0`.
**Replan (2026-10-30, ADR 0011):** exception: the scheduled-ingestion PRs from Week 7 (W7-D6-FAO-1, W7-D7-DAT-1) are merged on D20 and soak-tested until D22 (W8-D6-FAO-1, W8-D6-DAT-1). If the soak fails, the schedule is switched off (`INGEST_ENABLED=0`) and `v1.0` ships with the manual command of ADR 0008.

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

#### W8-D6-FAO-1 Merge and start scheduled ingestion, soak test
- Module: `pipelines/`, `docs/runbooks/data-pipeline.md`
- Do (after Gate W7 is recorded): merge W7-D6-FAO-1 and W7-D7-DAT-1 (DAT reviews); create `scitech_chunks_live` and `data/index/bm25-live` on the serving machine; start `make up` with `INGEST_ENABLED=1`, `BM25_RELOAD_SECONDS=60`; set the laptop to never sleep on power until D22; check the first scheduled run.
- Done when: first scheduled run logged in `data/logs/incremental.log` with points before/after; the frozen `scitech_chunks` point count unchanged (121,926).
- Depends on: W7-D6-FAO-1, W7-D7-DAT-1, W7-D5-DAT-1

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
- Do (afternoon): assemble chapters in order, add references and appendix (golden-set description, prompts, configs), export to PDF (decided in the brief).
- Done when: exported file reviewed by DAT (D22 morning at the latest).
- Depends on: W8-D2-FAO-1, W8-D2-LDN-1, W8-D1-DAT-1

## D22
Friday 2026-11-06 · Final gate (internal deadline)

### DAT (@Tdat10052499)

#### W8-D6-DAT-1 Scheduled ingestion soak check and ADR 0011 result
- Do (D22 morning, before the release): read `data/logs/incremental.log` since D20: at least 12 runs logged (a gap while the laptop slept counts as an uptime gap, not a failed run), none failed or overlapping, no backend error during a BM25 switch; ask one question about a paper announced on D21 and check it is cited. Record the numbers in ADR 0011 and in the release notes; if the check fails, set `INGEST_ENABLED=0` and record why.
- Done when: result in ADR 0011 (Consequences) and the `v1.0` release notes; FAO's data chapter and slides mention the schedule (W8-D1-FAO-1, W8-D3-FAO-1).
- Depends on: W8-D6-FAO-1

#### W8-D5-DAT-1 Release v1.0
- **Replan:** the presentation is on 2026-11-10 and the instructor only asks for the final product there, so this task releases `v1.0` and freezes the report; the dry run (W8-D4-DAT-1) moves to D24. The final report review moves here from W8-D4-DAT-1.
- Do (morning): final review pass of the exported report for consistency (terms from `docs/02-glossary.md`, numbers matching `final.md`); assign and merge fixes.
- Do (afternoon): merge last PRs; tag `v1.0` with release notes (features, how to run, known limitations, features cut by ADR 0010); put report PDF, video link and repo link in the release.
- Done when: release published with the report PDF attached.
- Depends on: W8-D3-DAT-1, W8-D4-LDN-1

## D23
Saturday 2026-11-07 · Presentation preparation

### All members

- (no new task ID) Finish your slides in the shared deck (sections assigned in W8-D3-LDN-1); rehearsal 1 together (timing per section, target about 15 minutes); list fixes. Check the live demo on the `v1.0` stack and the fallback LLM endpoint.

## D24
Monday 2026-11-09 · Dry run

### DAT (@Tdat10052499)

#### W8-D4-DAT-1 Dry run and final review
- **Replan:** moved from D22 to the day before the presentation; the report review is now part of W8-D5-DAT-1 (D22).
- Do: full presentation dry run with timing; collect fixes; check slides against the report (terms from `docs/02-glossary.md`, numbers matching `final.md`); start the LLM session and run the demo questions once.
- Done when: fix list assigned and done by the end of the day.
- Depends on: W8-D3-DAT-1, W8-D3-FAO-1, W8-D3-LDN-1

## D25
Tuesday 2026-11-10 · Product presentation

### All members

- (no new task ID) Before the session: start the stack (`make up`), the LLM endpoint and the fallback; open the recorded demo video. Present the product and answer questions.

### FAO (@F4ol4n)

#### W8-D5-FAO-1 Final journal and retrospective input
- Do (after the presentation): complete your journal; write 5 lines of retrospective (what worked, what to change), including how the compressed schedule worked.
- Done when: merged.
- Depends on: none

### LDN (@Yui-Mika)

#### W8-D5-LDN-1 Final journal and retrospective input
- Do (after the presentation): complete your journal; write 5 lines of retrospective; archive user-study raw data according to the consent you gave participants.
- Done when: merged.
- Depends on: none

## Cut or merged in the replan
None in Week 8.
