# Local Model Harness

A small FastAPI app that exposes a read-only local AI harness against files in a knowledge directory. It is designed to be easy to run locally for demos, troubleshooting, and blog-ready examples.

## What this project is

This is intentionally a harness, not a generic agent framework. It keeps the tool surface narrow, grounds answers in a local knowledge directory, and emits OpenTelemetry spans so the whole request lifecycle can be inspected in a trace UI.

The project is built to support local experimentation with open models while staying easy to observe and reason about.

## Prerequisites

- Python 3.12+
- A local Ollama instance with a reachable model endpoint
- Docker for the local Grafana LGTM stack
- Optional: Azure Monitor / Application Insights later for cloud-side viewing

## Repeatable setup

This project is intentionally pinned for reproducibility.

1. Create and activate the virtual environment:

   ```bash
   python3.12 -m venv .venv
   . .venv/bin/activate
   ```

2. Install the pinned dependencies and dev tools:

   ```bash
   uv sync --locked --group dev
   ```

3. Check the installed Ollama models and set the model explicitly if needed:

   ```bash
   ollama list
   export OLLAMA_MODEL=qwen3.8:27b-mlx
   ```

4. Confirm the app imports and starts:

   ```bash
   pytest -q
   uvicorn app:app --host 127.0.0.1 --port 8000
   ```

5. Health check:

   ```bash
   curl -sS http://127.0.0.1:8000/healthz
   ```

## Smoke test

The repo includes a minimal smoke test that validates the app module imports successfully:

```bash
pytest -q tests/test_smoke_startup.py
```

## Example query

```bash
curl -sS -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Read the local runbook and tell me how to investigate a checkout API readiness failure. Cite the source file."
  }'
```

## Visualizing GenAI spans locally

This project emits OpenTelemetry GenAI spans and metrics in the standard OTel pattern. For local visualization, the recommended setup is Grafana LGTM.

### Start Grafana LGTM

```bash
docker run --rm \
  --name lgtm \
  -p 3000:3000 \
  -p 4317:4317 \
  -p 4318:4318 \
  grafana/otel-lgtm:latest
```

Then set the local OTLP endpoint for the app:

```bash
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4318/v1/traces
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://localhost:4318/v1/metrics
```

Start the app and make a request:

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
curl -sS -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Read the local runbook and tell me how to investigate a checkout API readiness failure."
  }'
```

Then open:

- Grafana UI: http://localhost:3000
- Explore -> Traces
- Search for the request trace and inspect the parent `harness.run` span plus child spans such as `harness.tool.read_knowledge_file` and the underlying model/tool telemetry

The spans include `gen_ai.*` attributes and harness-specific metadata so you can see the full end-to-end flow: HTTP request -> harness run -> tool call -> model interaction -> response.

## OTLP protocol choice

This project intentionally uses OTLP over HTTP, not gRPC.

That matters because modern Azure Monitor / Application Insights setups are far more comfortable with the OTLP HTTP path for trace and metric export, while local Grafana LGTM is also happy to receive OTLP HTTP on port 4318.

The pattern is:

- local developer UI: Grafana LGTM
- Azure sink: Azure Monitor / Application Insights
- common protocol: OpenTelemetry OTLP over HTTP

## Azure Monitor path

When you are ready to send telemetry to Azure, keep the same OTel instrumentation and change the exporter endpoint to the Azure-compatible OTLP HTTP endpoint or route via a collector that forwards to Azure Monitor.

This keeps the app architecture clean: the producer emits standard OTel GenAI telemetry, and the backend decides where it is visualized.

## Why the pins matter

This project intentionally uses exact dependency pins instead of open ranges so the environment stays stable for demos, included blog examples, and repeatable local troubleshooting.

The dependency set was chosen to avoid the startup issues caused by mismatched OpenTelemetry and `pydantic-ai` versions.

## Why this is a harness

This project is intentionally narrow:

- read-only local knowledge access
- a constrained tool surface
- structured output and evidence tracking
- traceable request flow

That is the difference between a harness and a broad autonomous agent system. The harness is easier to reason about, easier to debug, and easier to monitor end-to-end.
