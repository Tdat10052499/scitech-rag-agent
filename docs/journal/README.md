# Journal

Each member writes in their own folder to avoid merge conflicts: `docs/journal/<CODE>/Wn.md`, where CODE is DAT, FAO or LDN (see `docs/plan/README.md`) and `Wn` is the phase ("Week N", see `docs/plan/calendar.md`).

One entry per working day, newest at the bottom; put the Day ID next to the date:

```
## 2026-10-16 (D04, Week 2)
- Tasks: W2-D1-FAO-1
- Done: ...
- Results: numbers, commands run, commit hash / PR link
- Problems / blockers: ...
- Next: ...
```

Record experiment settings (model, parameters, data snapshot) so results can be reproduced. AI agents read these entries to find unfinished work, so be specific.
