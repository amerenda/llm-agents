# llm-agents

Container images for LLM agent services that run on the k3s cluster. Each agent is a self-contained service that registers with the `llm-manager` backend and exposes a specialized API.

## Available Agents

| Agent | Port | Platform | Description |
|-------|------|----------|-------------|
| `piper` | 8091 | arm64 (RPi5) | Text-to-speech using [Piper](https://github.com/rhasspy/piper) |

### Piper TTS

FastAPI service wrapping the Piper TTS binary. Exposes an HTTP API for speech synthesis with Prometheus metrics.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/metrics` | Prometheus metrics |
| GET | `/v1/status` | Node info, available voices |
| GET | `/v1/voices` | List installed voice models |
| POST | `/v1/audio/speech` | Synthesize text to WAV audio |

**Speech request body:**

```json
{
  "input": "Text to speak",
  "voice": "en_US-lessac-medium",
  "response_format": "wav"
}
```

Voice models are loaded from a PVC mounted at `/voices` (`.onnx` files). The agent auto-registers with the llm-manager backend on startup and sends heartbeats every 30 seconds.

**Authentication:** All endpoints except `/health` and `/metrics` require an `X-Agent-PSK` header.

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8091` | Listen port |
| `LLM_MANAGER_AGENT_PSK` | *(required)* | Shared PSK for authentication |
| `BACKEND_URL` | *(required)* | llm-manager backend URL for registration |
| `POD_IP` | | Pod IP (set via Kubernetes downward API) |
| `PIPER_VOICES_DIR` | `/voices` | Directory containing `.onnx` voice models |
| `PIPER_DEFAULT_VOICE` | `en_US-lessac-medium` | Fallback voice |

## Adding a New Agent

1. Create a directory: `<agent-name>/`
2. Add `main.py` (or equivalent), `Dockerfile`, and `requirements.txt`
3. Implement at minimum:
   - `/health` endpoint (for k8s probes)
   - `/metrics` endpoint (for Prometheus)
   - Self-registration with the llm-manager backend on startup
   - Heartbeat loop (every 30s)
   - PSK authentication middleware
4. Add a `test_<agent-name>.py` with basic endpoint tests
5. Add k8s manifests in the gitops repo under `apps/llm-agents/<agent-name>/`
6. Update the CI workflow to detect changes and build the new agent (see below)

## CI/CD

The GitHub Actions workflow (`.github/workflows/build.yaml`) uses path-based change detection to only build agents that were modified.

On push to `main`:

1. **Detect changes** -- `dorny/paths-filter` checks which agent directories changed.
2. **Test** -- Runs `pytest` for the affected agent.
3. **Build** -- Builds a Docker image with Kaniko and pushes to `amerenda/llm-agents:<agent>-<tag>`.
4. **Deploy** -- Opens a PR against `k3s-dean-gitops`, updating the image tag in the agent's deployment manifest. Merging triggers ArgoCD rollout.

To add CI for a new agent, add a new filter entry in the `detect-changes` job and corresponding `test-<name>`, `build-<name>`, and `deploy-<name>` jobs (follow the piper pattern).
