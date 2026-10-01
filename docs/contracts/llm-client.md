# LLM client contract

All LLM access uses the OpenAI-compatible Chat Completions interface, so the backend can be switched between a self-hosted server (e.g. Ollama or vLLM, locally or on a remote GPU exposed through a tunnel) and a hosted API without code changes.

## Configuration (environment variables)
| Variable | Meaning |
|---|---|
| `LLM_BASE_URL` | Base URL of the OpenAI-compatible endpoint |
| `LLM_API_KEY` | Key for that endpoint (placeholder value for local servers that ignore it) |
| `LLM_MODEL` | Model identifier understood by that endpoint |

## Requirements for the client module (in `agent/`)
- One module wraps all calls; no other code imports an LLM SDK directly.
- Supports streaming of tokens.
- Configurable timeout and retry; clear error if the endpoint is unreachable (remote GPU sessions can disappear).
- Temperature and max tokens are parameters; experiment runs record the values used.
- A fake implementation exists for tests.
