# W01-02 Review and freeze contracts

- Area: docs
- Milestone: Week 1
- Depends on: W01-01 (for the `source` enum and metadata fields)

## Goal
Make `docs/contracts/` precise enough that data, agent, backend and frontend can be built in parallel.

## Context to read
`docs/contracts/*`, `docs/01-architecture.md`.

## Inputs and outputs
- Outputs: reviewed `chunk.schema.json`, `api.openapi.yaml`, `llm-client.md`; a note in each file "frozen on <date>"; list of open questions as issues.

## Scope
- May change: `docs/contracts/`, `docs/01-architecture.md`.

## Acceptance criteria
- [ ] Each module owner confirmed the contract in a comment on the issue.
- [ ] OpenAPI file validates with an OpenAPI linter.
- [ ] Chunk schema validated against a sample record.

## Notes / risks
Late contract changes cost the most; finish this before Week 2 starts.
