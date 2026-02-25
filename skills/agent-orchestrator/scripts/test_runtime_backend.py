from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from runtime_backend import enforce_backend_policy, resolve_runtime_backend


def test_resolve_runtime_backend_prefers_runtime_key(monkeypatch):
    monkeypatch.setenv("ORCH_RUN_BACKEND", "legacy")
    monkeypatch.setenv("ORCH_RUNTIME_BACKEND", "temporal")
    assert resolve_runtime_backend() == "temporal"


def test_enforce_backend_policy_blocks_legacy_in_cutover(monkeypatch):
    monkeypatch.setenv("ORCH_PRODUCTION_CUTOVER", "1")
    try:
        enforce_backend_policy("legacy")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "BACKEND_POLICY_BLOCKED" in str(e)


def test_enforce_backend_policy_allows_temporal_in_cutover(monkeypatch):
    monkeypatch.setenv("ORCH_PRODUCTION_CUTOVER", "1")
    assert enforce_backend_policy("temporal") == "temporal"
