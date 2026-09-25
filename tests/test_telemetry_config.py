import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import OLLAMA_MODEL
from telemetry import default_otlp_metric_endpoint, default_otlp_trace_endpoint


def test_default_otlp_http_endpoints_are_http():
    assert default_otlp_trace_endpoint() == "http://localhost:4318/v1/traces"
    assert default_otlp_metric_endpoint() == "http://localhost:4318/v1/metrics"


def test_default_ollama_model_matches_installed_local_model():
    assert OLLAMA_MODEL == "qwen3.8:27b-mlx"
    assert os.getenv("OLLAMA_MODEL", "qwen3.8:27b-mlx") == "qwen3.8:27b-mlx"
