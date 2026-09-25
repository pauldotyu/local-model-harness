from __future__ import annotations

import logging
import os
import sys

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import (
    SERVICE_INSTANCE_ID,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def default_otlp_trace_endpoint() -> str:
    return os.getenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "http://localhost:4318/v1/traces",
    )


def default_otlp_metric_endpoint() -> str:
    return os.getenv(
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "http://localhost:4318/v1/metrics",
    )


def configure_telemetry() -> tuple[trace.Tracer, metrics.Meter]:
    service_name = os.getenv("OTEL_SERVICE_NAME", "local-qwen-harness")
    service_version = os.getenv("APP_VERSION", "0.1.0")
    instance_id = os.getenv("HOSTNAME", "local-dev")

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            SERVICE_INSTANCE_ID: instance_id,
            "deployment.environment.name": os.getenv(
                "DEPLOYMENT_ENVIRONMENT",
                "development",
            ),
            "ai.harness.provider": "ollama",
            "ai.harness.model": os.getenv("OLLAMA_MODEL", "qwen3.8:27b-mlx"),
        }
    )

    trace_provider = TracerProvider(resource=resource)

    trace_exporter = OTLPSpanExporter(
        endpoint=default_otlp_trace_endpoint(),
    )

    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))

    trace.set_tracer_provider(trace_provider)

    metric_exporter = OTLPMetricExporter(
        endpoint=default_otlp_metric_endpoint(),
    )

    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=10_000,
    )

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )

    metrics.set_meter_provider(meter_provider)

    LoggingInstrumentor().instrument(
        set_logging_format=True,
        log_level=logging.INFO,
    )

    HTTPXClientInstrumentor().instrument()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        stream=sys.stdout,
    )

    return (
        trace.get_tracer("local-qwen-harness"),
        metrics.get_meter("local-qwen-harness"),
    )


def instrument_fastapi(app) -> None:
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="healthz,metrics",
    )
