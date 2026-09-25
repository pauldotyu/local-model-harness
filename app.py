from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

from telemetry import configure_telemetry, instrument_fastapi

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434/v1",
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen3.8:27b-mlx",
)

KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", "./knowledge")).resolve()

MAX_FILE_BYTES = 200_000

tracer, meter = configure_telemetry()

request_counter = meter.create_counter(
    name="harness.requests",
    description="Number of harness API requests.",
    unit="{request}",
)

request_duration = meter.create_histogram(
    name="harness.request.duration",
    description="End-to-end harness request duration.",
    unit="s",
)

agent_run_counter = meter.create_counter(
    name="harness.agent.runs",
    description="Number of agent runs by outcome.",
    unit="{run}",
)

tool_counter = meter.create_counter(
    name="harness.tool.executions",
    description="Number of tool executions by tool and outcome.",
    unit="{execution}",
)

tool_duration = meter.create_histogram(
    name="harness.tool.duration",
    description="Tool execution duration.",
    unit="s",
)


class HarnessDeps(BaseModel):
    knowledge_dir: Path


class Evidence(BaseModel):
    source: str
    excerpt: str


class HarnessResponse(BaseModel):
    answer: str = Field(description="A concise answer grounded in tool evidence.")

    evidence: list[Evidence] = Field(default_factory=list)

    needs_clarification: bool = False


model = OllamaModel(
    OLLAMA_MODEL,
    provider=OllamaProvider(base_url=OLLAMA_BASE_URL),
)

agent = Agent(
    model=model,
    deps_type=HarnessDeps,
    output_type=HarnessResponse,
    system_prompt=(
        "You are a local, read-only engineering-assistant harness. "
        "Use tools when factual information is needed from the local knowledge directory. "
        "Never claim to have inspected files unless you called a tool. "
        "Do not invent evidence. "
        "If the request cannot be answered from supplied context or allowed tools, "
        "set needs_clarification to true and explain what is needed. "
        "You cannot run shell commands, access Kubernetes, access secrets, or make changes."
    ),
)


def current_trace_id() -> str:
    span_context = trace.get_current_span().get_span_context()

    if not span_context.is_valid:
        return ""

    return format(span_context.trace_id, "032x")


@agent.tool
def list_knowledge_files(
    ctx: RunContext[HarnessDeps],
) -> list[str]:
    """List approved Markdown and text files in the local knowledge directory."""
    started = time.perf_counter()

    with tracer.start_as_current_span("harness.tool.list_knowledge_files") as span:
        span.set_attribute(
            "gen_ai.tool.name",
            "list_knowledge_files",
        )

        span.set_attribute(
            "harness.knowledge_directory",
            str(ctx.deps.knowledge_dir),
        )

        try:
            root = ctx.deps.knowledge_dir

            if not root.exists():
                span.set_attribute("harness.files_found", 0)

                tool_counter.add(
                    1,
                    {
                        "tool.name": "list_knowledge_files",
                        "tool.outcome": "success",
                    },
                )

                return []

            files = [
                str(path.relative_to(root))
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".md", ".txt"}
            ]

            result = sorted(files)[:200]

            span.set_attribute(
                "harness.files_found",
                len(result),
            )

            tool_counter.add(
                1,
                {
                    "tool.name": "list_knowledge_files",
                    "tool.outcome": "success",
                },
            )

            return result

        except Exception as exc:
            span.record_exception(exc)

            span.set_status(
                Status(
                    StatusCode.ERROR,
                    str(exc),
                )
            )

            tool_counter.add(
                1,
                {
                    "tool.name": "list_knowledge_files",
                    "tool.outcome": "error",
                },
            )

            raise

        finally:
            tool_duration.record(
                time.perf_counter() - started,
                {"tool.name": "list_knowledge_files"},
            )


@agent.tool
def read_knowledge_file(
    ctx: RunContext[HarnessDeps],
    relative_path: str,
) -> str:
    """Read one approved Markdown or text file returned by list_knowledge_files."""
    started = time.perf_counter()

    with tracer.start_as_current_span("harness.tool.read_knowledge_file") as span:
        span.set_attribute(
            "gen_ai.tool.name",
            "read_knowledge_file",
        )

        span.set_attribute(
            "harness.file.path",
            relative_path,
        )

        try:
            root = ctx.deps.knowledge_dir
            candidate = (root / relative_path).resolve()

            if root not in candidate.parents and candidate != root:
                raise ValueError("Path is outside the approved knowledge directory.")

            if candidate.suffix.lower() not in {".md", ".txt"}:
                raise ValueError("Only .md and .txt files are allowed.")

            if not candidate.is_file():
                raise FileNotFoundError(f"File not found: {relative_path}")

            if candidate.stat().st_size > MAX_FILE_BYTES:
                raise ValueError(f"File exceeds {MAX_FILE_BYTES} byte limit.")

            content = candidate.read_text(
                encoding="utf-8",
                errors="replace",
            )

            span.set_attribute(
                "harness.file.size_bytes",
                len(content),
            )

            span.set_attribute(
                "harness.content_captured",
                False,
            )

            tool_counter.add(
                1,
                {
                    "tool.name": "read_knowledge_file",
                    "tool.outcome": "success",
                },
            )

            return content

        except Exception as exc:
            span.record_exception(exc)

            span.set_status(
                Status(
                    StatusCode.ERROR,
                    str(exc),
                )
            )

            tool_counter.add(
                1,
                {
                    "tool.name": "read_knowledge_file",
                    "tool.outcome": "error",
                },
            )

            raise

        finally:
            tool_duration.record(
                time.perf_counter() - started,
                {"tool.name": "read_knowledge_file"},
            )


class AskRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=10_000,
    )


class AskResponse(BaseModel):
    answer: str
    evidence: list[Evidence]
    needs_clarification: bool
    model: str
    trace_id: str


app = FastAPI(
    title="Local Qwen AI Harness",
    version="0.2.0",
)

instrument_fastapi(app)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "model": OLLAMA_MODEL,
        "ollama_base_url": OLLAMA_BASE_URL,
    }


@app.post("/ask", response_model=AskResponse)
async def ask(
    request: Request,
    payload: AskRequest,
) -> AskResponse:
    started = time.perf_counter()

    request_counter.add(
        1,
        {
            "http.route": "/ask",
            "model": OLLAMA_MODEL,
        },
    )

    with tracer.start_as_current_span("harness.run") as span:
        span.set_attribute(
            "gen_ai.operation.name",
            "invoke_agent",
        )

        span.set_attribute(
            "gen_ai.request.model",
            OLLAMA_MODEL,
        )

        span.set_attribute(
            "harness.request.input_length",
            len(payload.question),
        )

        span.set_attribute(
            "harness.mode",
            "read_only",
        )

        deps = HarnessDeps(
            knowledge_dir=KNOWLEDGE_DIR,
        )

        try:
            result = await agent.run(
                payload.question,
                deps=deps,
            )

            output = result.output

            outcome = "clarification" if output.needs_clarification else "success"

            agent_run_counter.add(
                1,
                {
                    "agent.outcome": outcome,
                    "model": OLLAMA_MODEL,
                },
            )

            span.set_attribute(
                "harness.outcome",
                outcome,
            )

            span.set_attribute(
                "harness.evidence_count",
                len(output.evidence),
            )

            span.set_attribute(
                "harness.response.output_length",
                len(output.answer),
            )

            return AskResponse(
                answer=output.answer,
                evidence=output.evidence,
                needs_clarification=output.needs_clarification,
                model=OLLAMA_MODEL,
                trace_id=current_trace_id(),
            )

        except Exception as exc:
            span.record_exception(exc)

            span.set_status(
                Status(
                    StatusCode.ERROR,
                    str(exc),
                )
            )

            agent_run_counter.add(
                1,
                {
                    "agent.outcome": "error",
                    "model": OLLAMA_MODEL,
                },
            )

            raise HTTPException(
                status_code=500,
                detail=("Harness execution failed: " f"{type(exc).__name__}: {exc}"),
            ) from exc

        finally:
            request_duration.record(
                time.perf_counter() - started,
                {
                    "http.route": "/ask",
                    "model": OLLAMA_MODEL,
                },
            )
