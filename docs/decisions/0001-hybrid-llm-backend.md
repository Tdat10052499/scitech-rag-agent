# 0001. Hybrid LLM backend behind an OpenAI-compatible interface

- Status: accepted
- Date: 2026-10-01
- Deciders: project maintainer

## Context
The team wants to self-host an open-source LLM for reproducibility and control. The maintainer's laptop has only an integrated GPU (Intel Iris Xe, shared memory) and about 15.6 GB RAM, which is not suitable for running capable models locally at acceptable speed. Free GPU sessions (e.g. Colab, Kaggle) are time-limited and can be interrupted.

## Options considered
1. Fully local self-hosting on CPU/integrated GPU.
2. Self-hosted open-source model on an external GPU (Colab/Kaggle/university server), reached through an OpenAI-compatible endpoint.
3. Hosted API only.

## Decision
Use the OpenAI-compatible interface (`docs/contracts/llm-client.md`) so the backend is swappable. Run the open-source model on an external GPU for development and experiments; keep a hosted API or a small local model as a fallback for demos.

## Consequences
- Reproducibility: pin and record model name/version and parameters for every experiment.
- Risk: external GPU sessions can end; always have a fallback and a recorded demo.
- The report must state that "self-hosted" here means self-controlled model weights, not necessarily running on the team's own machine.
- Whether the course requires fully local execution is an open question (see project brief).
