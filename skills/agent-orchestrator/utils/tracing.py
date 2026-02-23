from __future__ import annotations

import contextlib
import os
import time
from typing import Any, Iterator


@contextlib.contextmanager
def traced_span(name: str, **attrs: Any) -> Iterator[None]:
    """Best-effort tracing span.

    - If OpenTelemetry is installed and ORCH_TRACE_ENABLED=1, emit OTel span.
    - If LangSmith is configured, expose run/task attrs as metadata via env hints.
    - Otherwise fallback to no-op timing block.
    """

    enabled = os.getenv("ORCH_TRACE_ENABLED", "1").strip() != "0"
    if not enabled:
        yield
        return

    tracer = None
    span = None
    token = None
    start = time.time()
    try:
        try:
            from opentelemetry import trace  # type: ignore

            tracer = trace.get_tracer("agent-orchestrator")
            span = tracer.start_span(name)
            token = trace.use_span(span, end_on_exit=False)
            token.__enter__()
            for k, v in attrs.items():
                try:
                    span.set_attribute(str(k), str(v))
                except Exception:
                    pass
        except Exception:
            tracer = None

        # lightweight LangSmith correlation hints
        if os.getenv("LANGSMITH_TRACING", "").strip().lower() in {"1", "true", "yes", "on"}:
            if attrs.get("run_id"):
                os.environ.setdefault("LANGSMITH_RUN_ID", str(attrs.get("run_id")))
            if attrs.get("task_id"):
                os.environ.setdefault("LANGSMITH_TASK_ID", str(attrs.get("task_id")))

        yield
        if span is not None:
            span.set_attribute("status", "ok")
    except Exception as e:
        if span is not None:
            try:
                span.set_attribute("status", "error")
                span.set_attribute("error", str(e))
            except Exception:
                pass
        raise
    finally:
        if span is not None:
            try:
                span.set_attribute("duration_ms", int((time.time() - start) * 1000))
            except Exception:
                pass
        if token is not None:
            try:
                token.__exit__(None, None, None)
            except Exception:
                pass
        if span is not None:
            try:
                span.end()
            except Exception:
                pass
