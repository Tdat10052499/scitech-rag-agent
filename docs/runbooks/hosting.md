# Public hosting on a Hugging Face Space

Added on 2026-11-02 so the app can be used without DAT's laptop. The laptop must not stay on, and
a tunnel was ruled out. Files: `deploy/hf-space/`.

## 1. What runs where

| Part | Where | Notes |
|---|---|---|
| UI, backend, Qdrant, BM25 | one container in a Hugging Face Docker Space, `cpu-basic` (needs a PRO account, see below) | nginx on port 7860 serves the UI and forwards `/health`, `/chat` and `/feedback` to uvicorn on 127.0.0.1:8000. Qdrant runs on 127.0.0.1:6333 inside the container. |
| Index | a private Hugging Face dataset repo | It holds a Qdrant snapshot and the BM25 directory. `fetch_index.py` downloads it at every start, because the free Space disk is not persistent. |
| LLM | a hosted OpenAI-compatible API, e.g. Groq | ADR 0001: only `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` change. |

Since 2026-11-02, creating a Docker Space on `cpu-basic` returns HTTP 402 without a Hugging Face PRO subscription; only static Spaces stay free. DAT bought PRO for the defense period (cancel after 2026-11-10).

`cpu-basic` limits ([Hugging Face docs](https://huggingface.co/docs/hub/en/spaces-gpus), read 2026-11-02):

- 2 vCPU, 16 GB RAM, 50 GB disk;
- the Space sleeps after 48 h without visits, and the next visit wakes it;
- the wake-up is a full start: download the index, restore Qdrant, load the embedding model. It is not measured yet (fill in §5).

> **Model difference.** The hosted model is not `llama3.2:3b`, the evaluation model (`evaluation/RUNS.md` §7). Every number in the report belongs to the evaluated setup, not to the hosted demo. Say this in the report and on the demo slide.

## 2. Limits that protect the API quota

A hosted free tier limits tokens per minute (TPM). One `/chat` turn makes up to 3 LLM calls (rewrite, answer, follow-ups). The answer prompt holds 5 chunks of up to 320 words. That is an estimate of roughly 3,000–5,000 tokens per turn, not measured.

nginx limits `/chat` in two ways:

- per visitor, `CHAT_PER_MINUTE` per minute (default 3, burst 3); a visitor over the limit gets HTTP 429, and the UI shows "The server rejected the request (HTTP 429)";
- for all visitors together, `CHAT_TOTAL_PER_MINUTE` (default 4); excess requests wait in a short queue.

Set `CHAT_TOTAL_PER_MINUTE` to about the model's TPM / 5,000. Read the TPM on the provider's limits page (Groq: console > Settings > Limits); the figures change and differ per model.

Other settings:

- The API key stays a Space **secret**. The browser never sees it: only the backend calls the LLM.
- Traces are off by default (`AGENT_TRACES=off`), because they hold visitors' questions.
- nginx keeps no access log.

## 3. One-time setup (DAT, on the laptop)

1. **Accounts.**
   - Create a Hugging Face account.
   - Create a token with write access and run `pip install -U huggingface_hub`, then `hf auth login`. Never paste the token into a file in the repository.
   - Create an LLM API account and key (e.g. Groq). Choose a non-reasoning instruct model and note its TPM.
2. **Check the API with the local stack first.** In the laptop shell, set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` to the hosted API, then run `make run` and ask the demo questions (`docs/report/demo-script.md`). This catches a model that ignores the `[n]` format before anything is public.
3. **Upload the index.** Qdrant must be running with the frozen collection (121,926 points). From the repository root:

   ```powershell
   python deploy/hf-space/push_space.py index --repo <hf-user>/scitech-index
   ```

   The script uploads `qdrant/scitech_chunks.snapshot` and `bm25/` (from `data/index/bm25`) to a private dataset repo.
4. **Upload the code.**

   ```powershell
   python deploy/hf-space/push_space.py code --space <hf-user>/scitech-rag-agent
   ```

   This creates the Docker Space if it does not exist, then builds the image. Add `--dry-run <dir>` to see the files without uploading them.
5. **Space settings** (Settings > Variables and secrets):

| Name | Kind | Value |
|---|---|---|
| `INDEX_REPO` | variable | `<hf-user>/scitech-index` |
| `HF_TOKEN` | secret | a **read-only** token (for the private dataset) |
| `LLM_BASE_URL` | variable | e.g. `https://api.groq.com/openai/v1` |
| `LLM_MODEL` | variable | the chosen model |
| `LLM_API_KEY` | secret | the API key |
| `EMBEDDING_MODEL` | variable | `BAAI/bge-small-en-v1.5` |
| `EMBEDDING_QUERY_PREFIX` | variable | `Represent this sentence for searching relevant passages:` |
| `RETRIEVER` | variable | `hybrid` |
| `QDRANT_SEARCH_EXACT` | variable | `true` |
| `AGENT_REWRITE` / `AGENT_SELF_CHECK` | variable | `on` / `off` (the A2 product configuration) |
| `CHAT_PER_MINUTE`, `CHAT_TOTAL_PER_MINUTE` | variable | §2 |

   Changing a variable restarts the Space.
6. **Check it.**
   - Open `https://<hf-user>-scitech-rag-agent.hf.space`.
   - In the Space log, the start prints `fetch_index: scitech_chunks has 121926 points`, then `Application startup complete.` The `AGENT_MODE=real: agent ready` line is logged at INFO and does not appear in the Space log. A `/chat` that reaches the LLM confirms real mode (a wrong key shows `answer failed: LLM endpoint returned HTTP 401`).
   - Ask the demo questions.

## 4. Updates

- **Code change (automatic):** `.github/workflows/deploy-hf-space.yml` runs step 4 after every push to `main` whose CI passes, or by hand (Actions > Deploy HF Space > Run workflow). One-time setup: a Hugging Face fine-grained token with write access to the Space only, saved in GitHub > Settings > Secrets and variables > Actions as `HF_TOKEN` (separate from the read-only `HF_TOKEN` inside the Space). Without it the workflow fails at its first step. It runs only from `main`; before this branch is merged, push by hand.
- **Code change (by hand):** run step 4 again from a clean `main`.
- **New index:** run step 3 again, then restart the Space (Settings > Restart).
- The live index of ADR 0011 is **not** used here. The Space serves the frozen evaluation index.

## 5. Verified so far

On 2026-11-02, in the cloud dev container, the image was built and run with a 5-chunk BM25 index, a 3-point Qdrant snapshot and a fake LLM:

- `fetch_index` restored the snapshot (3 points);
- `/health` was ok, and `/` served the UI;
- `/chat` streamed `sources`, `token`, `followups` and `done`;
- the 6th question in a minute from one visitor got 429, while another visitor still got 200.

**Not checked there:**

- the apt `nginx` and `libunwind8` install, and the CPU torch install (that network blocks deb.debian.org and download.pytorch.org);
- the real 121,926-chunk index;
- a hosted LLM.

These are checked by the first real Space build. TODO: wake-up time and first-token latency on the Space.

First real Space build, 2026-11-02 (`Teichi/scitech-rag-agent`, PRO, `cpu-basic`, LLM `qwen/qwen3.8-27b` on Groq):

- the image built, so the apt and CPU torch installs work;
- `fetch_index` downloaded the index in 2 s and restored `scitech_chunks` in 5 s, with 121926 points;
- from container start to `Application startup complete.` took about 30 s (16:23:46 to about 16:24:15 in the log);
- the first `/chat` failed with HTTP 401 from Groq because of a wrong `LLM_API_KEY`; after the secret was fixed, DAT reported that the app answers.

Latency on the Space, 2026-11-02 about 17:28 UTC, measured from DAT's laptop (Vietnam) with a small `httpx` script over `/chat`, one run per question, Space warm, 35 s between questions because of `CHAT_TOTAL_PER_MINUTE=2`:

| Question (demo script) | First `token` event | Stream done |
|---|---:|---:|
| maths at answer time (`gs-019` turn 1) | 1.3 s | 1.8 s |
| "What goes wrong with those methods?" (same session) | 1.5 s | 2.1 s |
| RevThink GPU hours (`gs-u03`, refused) | 1.2 s | 1.7 s |
| pizza recipe (off-topic, refused) | 1.2 s | 1.4 s |

All four returned HTTP 200. Four single runs are not a distribution: no p50 or p95, and they are not comparable with `performance.md` (other model, other host). The answers' content was not checked by the script.

Not measured yet: the wake-up time after 48 h of sleep.
