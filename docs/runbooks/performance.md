# Runbook: latency of the frozen system

Task: W6-D2-DAT-1 (moved to Week 7, measurement only; tracking issue #156).
Inputs: the answers runner (#148), `evaluation/SNAPSHOT.md`, the golden set on `main`.

> Status: measured on 2026-10-30 on DAT's laptop, two runs of the same 30 questions. Headline numbers come from run B in section 3.

## 1. What was measured
- System: tag `v0.6-rc` (`b61001d`) with the answers-runner files from #148 checked out on top, so the run file records `git_commit` as `b61001d…+dirty`. Configuration as in `evaluation/SNAPSHOT.md`:
  - hybrid retrieval, top_k 5;
  - query rewrite on, self-check off;
  - temperature 0, `answer_max_tokens` 512, up to 4 follow-ups.
- Questions: the first 30 golden questions (`split: all`, `limit: 30`), which include 5 follow-up turns (gs-018, 019, 022, 023, 024). Config `latency30.yaml`, name `latency30`.
- Host: DAT's laptop, which serves every W7 run:
  - CPU and memory: AMD Ryzen AI 7 350, 31 GB RAM;
  - GPU: NVIDIA RTX 5060 Laptop 8 GB, driver 621.01;
  - Windows, no Docker.
- LLM: Ollama 0.40.13 on the same laptop.
  - Generator `llama3.2:3b`, digest `a80c4f17acd5`.
  - `ollama ps` shows 100% GPU, context 4096.
  - There is no network hop to the LLM.
  - The judge `qwen2.5:7b` (`845dbda0ea48`) runs after all answers, so its time is not in the latency figures.
- Index: Qdrant 1.19.2 native, `scitech_chunks` at 121,926 points, same index snapshot as SNAPSHOT.
- Phases, in ms, from the run file's `per_answer[].latency_ms`:
  - `first_token` and `answer` (answer complete) are measured from the start of the request;
  - `total` includes the follow-up suggestions, which the UI shows after the answer;
  - `rewrite` is non-zero only on follow-up turns.
- Statistics: p50 and p95 by linear interpolation (`latency_summary.py`), plus the maximum. A warm-up call precedes each run.

## 2. Reproduce
In one PowerShell window on the laptop, with Qdrant and Ollama running, from the repository root:
```powershell
Get-Content .env | Where-Object { $_ -match "^[A-Z_]+=" } | ForEach-Object { $k, $v = $_ -split "=", 2; Set-Item "env:$k" $v }
$env:PYTHONPATH = "pipelines/src;agent/src;backend/src;evaluation/src"
$env:QDRANT_URL = "http://127.0.0.1:6333"   # not localhost, see section 4
python -m scitech_eval answers --config latency30.yaml --out-dir evaluation/runs
python latency_summary.py evaluation/runs/<stamp>-latency30.json
```
The code does not read `.env` itself, which is why the first line loads it into the window.

## 3. Results

| Run | Qdrant URL | First token p50 / p95 / max | Answer complete p50 / p95 | Total p50 / p95 / max | Errors | Refused |
|---|---|---|---|---|---|---|
| A `20261030T082915Z` | `http://localhost:6333` | 469 / 4454 / 4719 | 1344 / 4400 | 4461 / 7367 / 8594 | 0 | 5 |
| **B `20261030T083604Z`** | `http://127.0.0.1:6333` | **422 / 2632 / 5016** | **1328 / 3196** | **4304 / 6025 / 9125** | 0 | 5 |

All values are in ms, with n = 30 per run. Warm-up took 8.0 s in run A and 6.1 s in run B. Answering all 30 questions took 139 s in run A and 123 s in run B.

Phase breakdown of run B, in ms:

| Phase | n | p50 | p95 | max |
|---|---|---|---|---|
| rewrite (follow-up turns only) | 5 > 0 | 0 | 1356 | 2266 |
| retrieve | 30 | 31 | 47 | 47 |
| followups | 25 | 2859 | 3044 | 3266 |

There are 25 follow-up suggestion calls because the 5 refused answers (gs-008, 012, 018, 021, 024) do not generate follow-ups.

In short, on this host:
- the first token arrives in under 0.5 s for half of the questions and in under 2.7 s for 95% of them;
- the answer is complete in about 1.3 s at the median;
- the follow-up suggestions add about 2.9 s after the answer is already on screen.

## 4. Finding: use `127.0.0.1`, not `localhost`, on Windows
In run A, 6 of 30 retrievals (gs-002, 006, 010, 014, 025, 026) took about 2.05 s, while the other 24 took 47 ms or less. Run B changed only `QDRANT_URL` to `127.0.0.1`. Every retrieval then took 15–47 ms, and those six questions lost about 2 s of first-token time each.

The explanation consistent with this is that Windows resolves `localhost` to IPv6 `::1` first while native Qdrant listens on IPv4. A new connection then waits before falling back to IPv4. This is inferred from the A/B change, not from a network trace.

**Action:** on the laptop, set `QDRANT_URL=http://127.0.0.1:6333` in `.env` for every W7 run and for the user study. Inside the Docker stack the URL is set by compose and is not affected.

## 5. Remaining slow cases in run B (LLM side, not explained)
- **gs-001, first token 5.0 s.** It is the first question after warm-up. Run A also had a slow first question (4.4 s).
- **gs-009, gs-013, gs-025, first token about 2.4 s.** Retrieval and rewrite are normal for these questions. The cause is not determined from the run file, for example prompt length or how Ollama handles the prompt.
- **gs-019 and gs-022, first token about 2.6 s.** About 2.2 s of this is the rewrite call. The other three follow-up turns rewrite in 0.2–0.3 s.

## 6. Limits
- n = 30 and one run per condition. With n = 30, p95 sits between the 28th and 29th sorted values, so a single outlier moves it, and the A/B comparison has no repetition.
- One host, a local GPU with no network hop and a single user at a time. The numbers do not carry over to the Kaggle endpoint (ADR 0006), to FAO's laptop (the user-study host), or to concurrent users.
- Timer resolution: the values cluster on multiples of about 15.6 ms (15, 31, 47, 203, …). This matches the default Windows clock tick, so phases under about 16 ms are not resolved.
- The runner measures in-process. Browser, nginx and SSE overhead of the real UI are not included.
- Quality metrics are out of scope here. For reference, both runs gave the same judge counts: 77 sentences, 37 supported, and 5 answerable questions refused.
