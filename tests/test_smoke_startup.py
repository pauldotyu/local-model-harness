import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_app_imports() -> None:
    app_module = importlib.import_module("app")
    assert hasattr(app_module, "app")
    assert app_module.app is not None
