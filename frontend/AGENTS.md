# frontend/ — user interface

Scope: chat UI that shows streamed answers, citations (sources) and clickable follow-up questions.

- Talks to the backend only through `docs/contracts/api.openapi.yaml` (including SSE event names).
- The framework choice is not made yet: record it in `docs/decisions/` before scaffolding, and add the module's commands to this file and to the `Makefile`.
- Show source citations next to every answer and a clear message when the agent reports insufficient evidence.
