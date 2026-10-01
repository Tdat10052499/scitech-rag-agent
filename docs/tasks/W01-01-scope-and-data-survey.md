# W01-01 Narrow scope and verify data sources

- Area: docs, data
- Milestone: Week 1
- Depends on: none

## Goal
Choose a specific science/technology sub-domain and confirm which open datasets will form the corpus, so later work has a fixed target.

## Context to read
`docs/00-project-brief.md`, `docs/03-data-sources.md`.

## Inputs and outputs
- Inputs: candidate sources in `docs/03-data-sources.md`.
- Outputs: updated `docs/03-data-sources.md` with, per source: access method, format, measured size of the chosen subset, update frequency, licence/terms, rate limits; updated project brief with the chosen sub-domain; a recommendation (which sources, which subset) in an ADR.

## Scope
- May change: `docs/`
- Must not change: code modules.

## Acceptance criteria
- [ ] Sub-domain chosen and written in the brief, with reasons.
- [ ] Every claim about size/licence/rate limits is backed by a link to the source's own documentation or by a measurement you ran.
- [ ] Recommendation recorded in `docs/decisions/0003-*.md`.
- [ ] Open question about "big data" scale answered with actual numbers (records, GB).

## How to test
Review: a teammate can follow the document and obtain the same data.
