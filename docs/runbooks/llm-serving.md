# Runbook: LLM serving (OpenAI-compatible endpoint on Kaggle GPU)

Task: W1-D3-DAT-1 (D02, 2026-10-14). Input for ADR 0006 (model and serving, D06).
Contract: `docs/contracts/llm-client.md` (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`).
Files: `notebooks/llm-serving/kaggle_ollama_server.ipynb` (server + tunnel), `notebooks/llm-serving/bench_llm.py` (measurement).

> Status: measured on 2026-10-14 (sections 4.1-4.3, two Kaggle sessions); cause of the within-session slowdown open.

## 1. Start a server (Kaggle, about 5 minutes)
1. Kaggle → New Notebook → File → Import Notebook → `notebooks/llm-serving/kaggle_ollama_server.ipynb`.
2. Settings → Accelerator: **GPU T4 x2**; Settings → Internet: on (requires a phone-verified Kaggle account). The menu shows "Turn off internet" when internet is on.
3. Run All. Check: cell 1 prints two Tesla T4; cell 3 prints `{"version": ...}`; cell 6 prints `LLM_BASE_URL = https://<random>.trycloudflare.com/v1`; cell 8 prints `alive: True` every minute.
4. Stop: interrupt cell 8, run cell 9, then **Stop Session** (saves GPU quota).

## 2. Call it from the laptop
```bash
pip install -r notebooks/llm-serving/requirements.txt
export LLM_BASE_URL=https://<random>.trycloudflare.com/v1   # PowerShell: $env:LLM_BASE_URL="..."
export LLM_API_KEY=not-needed                               # Ollama ignores the key
export LLM_MODEL=qwen2.5:3b
python notebooks/llm-serving/bench_llm.py --runs 1 --prompts en --out bench_smoke.jsonl
```
The URL changes on every session: never commit it, share it only inside the team.

## 3. Measurement method
- Script: `bench_llm.py`, streaming Chat Completions through the `openai` client, `temperature=0`, `max_tokens=200`, no retries.
- Per model: 1 warm-up call (loads the model; recorded, not summarised), then 5 runs × 2 prompts (EN, VI; about 150 words each requested).
- TTFT = time from request to first content chunk. Decode rate = (completion tokens − 1) / (time after first token). Token counts come from the server's `usage` field.
- Raw results: JSONL per run (not committed: `*.jsonl` is git-ignored).

## 4. Results

### 4.1 On the Kaggle server (no network), 2026-10-14, two sessions
Conditions: Kaggle notebook, 2 × Tesla T4 (15,360 MiB each, driver 580.178.04), 4 vCPU, 31 GB RAM; Ollama 0.40.4; default Ollama quantisation of each tag; all three models kept loaded (`OLLAMA_KEEP_ALIVE=-1`); n = 5 per model, prompt and session. S1 = first session (about 09:00 UTC), S2 = second session (about 09:25 UTC).

| Model (Ollama tag, size) | Prompt | TTFT median s (S1 / S2) | Decode tok/s median (min-max), S1 | Decode tok/s median (min-max), S2 | Tokens median |
|---|---|---|---|---|---|
| qwen2.5:3b (1.9 GB) | en | 0.04 / 0.04 | 80.6 (79.3-81.5) | 74.4 (68.2-77.8) | 200 |
| qwen2.5:3b | vi | 0.03 / 0.03 | 80.0 (79.1-81.0) | 73.2 (67.0-77.1) | 200 |
| llama3.2:3b (2.0 GB) | en | 0.04 / 0.04 | 78.0 (73.4-81.5) | 80.6 (77.4-82.4) | 170 |
| llama3.2:3b | vi | 0.04 / 0.04 | 75.4 (73.0-80.5) | 79.3 (77.2-81.8) | 200 |
| qwen2.5:7b (4.7 GB) | en | 0.05 / 0.05 | 26.8 (22.1-30.2) | 28.5 (25.2-31.8) | 120 |
| qwen2.5:7b | vi | 0.05 / 0.05 | 25.4 (22.2-29.5) | 27.9 (24.7-30.9) | 200 |

Other observations:
- Warm TTFT is 0.03-0.08 s in every run. Medians differ between sessions by up to 9% (qwen2.5:3b 80 → 74 tok/s), so a single session is not a stable estimate.
- Cold start (warm-up call, includes loading the model), S1 / S2: qwen2.5:3b 74.4 / 78.7 s (first model after server start), llama3.2:3b 37.0 / 38.9 s, qwen2.5:7b 2.5 / 2.6 s. Reproduced in both sessions (n = 2), so budget about 2 minutes after a new session before the first answer. Why the first model takes much longer than the others is not established.
- Session setup: Ollama install < 1 min; model download 24 s (1.9 GB), 26 s (2.0 GB), 44 s (4.7 GB).
- GPU memory with all three models loaded: 3,337 MiB and 12,265 MiB on the two GPUs (same in both sessions).
- **Decode rate falls across consecutive runs of the same model.** qwen2.5:7b fell in both sessions (S1 30.2 → 22.1, S2 31.8 → 24.7 tok/s, about −22 to −27% over 10 calls); qwen2.5:3b fell in S2 (77.8 → 67.0) but not in S1; llama3.2:3b fell slightly in both. GPU log of S2 (nvidia-smi every 2 s, 186 samples with a model loaded): **no thermal slowdown** (no SW/HW thermal bit; temperature 46-79 °C); **power capping is frequent on GPU1** (SW power cap in 43 of 64 loaded samples, power up to 74 W, T4 limit 70 W) and occasional on GPU0 (15 of 122; up to 71 W). SM clock ranged 300-1,590 MHz. Hypothesis (not tested): under a fixed power cap, rising temperature increases leakage power, so the clock and the decode rate drop over a run; the 7B model, which shows the clearest decline, loads mostly the capped GPU1. A test would align per-call timestamps in the bench JSONL with the GPU log, or run one model per session. Practical consequence: long evaluation runs (W7) may be slower per call than these medians; measure throughput on the real batch.

### 4.2 Through the tunnel, from the laptop (2026-10-14, second Kaggle session)
Conditions: laptop (Windows, Python 3.14, `openai` 3.31.0) → Cloudflare quick tunnel → Ollama on Kaggle 2 × T4; models already loaded; n = 5 per model and prompt.

| Model | Prompt | TTFT median (min-max) s | Decode tok/s median (min-max) | Tokens median |
|---|---|---|---|---|
| qwen2.5:3b | en | 0.37 (0.35-0.39) | 52.2 (50.2-58.0) | 200 |
| qwen2.5:3b | vi | 0.36 (0.35-0.64) | 55.3 (50.0-59.1) | 200 |
| llama3.2:3b | en | 0.39 (0.32-0.63) | 68.2 (63.8-72.7) | 170 |
| llama3.2:3b | vi | 0.39 (0.36-0.42) | 67.0 (63.8-72.0) | 200 |
| qwen2.5:7b | en | 0.39 (0.37-0.48) | 24.3 (22.7-26.5) | 120 |
| qwen2.5:7b | vi | 0.37 (0.36-0.67) | 24.9 (23.2-25.1) | 200 |

Reading:
- The tunnel adds about 0.3-0.35 s to TTFT (0.03-0.05 s on the server, section 4.1). Total time for a 200-token answer: about 3.5-4.5 s (3B) and 8-9 s (7B).
- Same session (S2) on the server vs through the tunnel, decode medians: qwen2.5:3b 73-74 vs 52-55 tok/s (about −27%), llama3.2:3b 79-81 vs 67-68 (about −15%), qwen2.5:7b 28 vs 24-25 (about −12%). The loss is larger for faster models, consistent with (not proof of) the network path limiting how fast streamed chunks arrive. Remaining confounders: the tunnel runs came later in the session (see the within-session decline in 4.1), and run order was not randomised.
- No errors in 33 calls; one tunnel URL stayed up for the whole run.

First attempt (09:02 UTC) failed: Ollama exited with code 1 (cause unknown, no error line in `ollama.log`) and the clean-up cell, run by Run All, then sent SIGTERM to the tunnel. The notebook now runs both in their own process session, restarts Ollama from a watchdog cell, and skips clean-up unless `CLEANUP = True`. `trycloudflare.com` is blocked by the egress allowlist of Claude's environments, so tunnel measurements must run from a team member's machine.

### 4.3 Laptop CPU (Ollama on Windows)
Conditions: maintainer laptop, Intel Core i7-1260P (integrated Iris Xe, about 15.6 GB RAM, ADR 0001), Windows, Ollama 0.40.3 (Kaggle: 0.40.4); n = 3 per model and prompt.

| Model | Prompt | TTFT median (min-max) s | Decode tok/s median (min-max) | Tokens median |
|---|---|---|---|---|
| qwen2.5:3b | en | 2.27 (2.19-2.30) | 13.9 (12.5-14.7) | 145 |
| qwen2.5:3b | vi | 2.22 (2.17-3.25) | 14.3 (12.6-14.7) | 183 |
| llama3.2:3b | en | 2.66 (2.25-2.80) | 12.9 (12.0-13.6) | 172 |
| llama3.2:3b | vi | 2.92 (2.72-3.05) | 12.5 (12.3-14.5) | 200 |

Cold start (warm-up): TTFT 7.9 s (qwen2.5:3b), 9.5 s (llama3.2:3b). A 200-token answer takes about 15-19 s, roughly 4-5 times slower than the 3B models on Kaggle through the tunnel. Usable as an offline fallback for a demo, not for evaluation runs (W7 needs hundreds of calls).

### 4.4 Summary for ADR 0006 (speed only)
| Setup | TTFT | 200-token answer |
|---|---|---|
| Kaggle T4, 3B, on the server | ~0.04 s | ~2.5-3 s |
| Kaggle T4, 3B, via tunnel | ~0.4 s | ~4 s |
| Kaggle T4, 7B, via tunnel | ~0.4 s | ~8-9 s |
| Laptop CPU, 3B | ~2.2-2.9 s | ~15-19 s |

All three are fast enough to stream; quality decides between 3B and 7B (ADR 0006, D06). The agent makes several LLM calls per question (rewrite, answer, follow-ups), so per-question latency is a multiple of these numbers.

## 5. GPU quota
Kaggle shows a weekly GPU quota of 30 h; after the two spike sessions on 2026-10-14 (about 2 h of session time in total, including idle time), 27 h 57 min remained. The quota counts session time, not GPU work, so stop sessions as soon as a run ends. The same quota is shared by the LLM (ADR 0006, W4-W7 runs) and FAO's embedding runs (W3), so heavy runs are planned in the tracking issue.

## 6. Limits and risks
- Speed only: answer quality (including Vietnamese) is **not** measured here; ADR 0006 compares quality on the 10 golden items (W1-D4-LDN-1).
- Small n (5 per cell on GPU, 3 on CPU, 1 for cold start), two Kaggle sessions, one GPU type; Kaggle hardware and load vary between sessions.
- English answers often stopped before 200 tokens, so total times differ between prompts; compare decode rates, not totals.
- The quick tunnel is **unauthenticated**: anyone with the URL can use the server (including pulling or deleting models). Keep sessions short and the URL private; for longer use, put an authenticating proxy or a named Cloudflare tunnel with access control in front (not done in this spike).
- Kaggle sessions are time-limited and stop when idle; the endpoint can disappear at any time. The LLM client must time out and report a clear error (`llm-client.md`).
- Moving to a local GPU later only changes `LLM_BASE_URL`; do not switch before feature freeze (D16) so W7 experiments use one setup.
