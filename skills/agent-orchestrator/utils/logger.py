"""Unified logging system for OpenClaw.

Primary API:
  - setup_logging / get_logger / ExtraAdapter / RunLogger

Backward-compatible API (kept for existing scripts/tests):
  - setup_logger / SimpleLogger / StructuredLogger
  - get_simple_logger / get_structured_logger / log_context
"""

import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Union

try:
    from utils.paths import LOGS_DIR, PROJECT_ID, init_workspace
except ImportError:
    from paths import LOGS_DIR, PROJECT_ID, init_workspace


class KwargLogger(logging.Logger):
    """Logger that accepts arbitrary keyword fields in log calls."""

    @staticmethod
    def _split_kwargs(kwargs: Dict[str, Any]):
        known = {"exc_info", "stack_info", "stacklevel", "extra"}
        clean = {}
        dynamic = {}
        for key, value in kwargs.items():
            if key in known:
                clean[key] = value
            else:
                dynamic[key] = value
        return clean, dynamic

    def _merge_extra(self, kwargs: Dict[str, Any], dynamic: Dict[str, Any]):
        if not dynamic:
            return kwargs
        extra = kwargs.get("extra", {})
        if isinstance(extra, dict):
            merged = dict(extra.get("extra_fields", {}))
            merged.update(dynamic)
            kwargs["extra"] = {"extra_fields": merged}
        else:
            kwargs["extra"] = {"extra_fields": dynamic}
        return kwargs

    def debug(self, msg, *args, **kwargs):
        clean, dynamic = self._split_kwargs(kwargs)
        super().debug(msg, *args, **self._merge_extra(clean, dynamic))

    def info(self, msg, *args, **kwargs):
        clean, dynamic = self._split_kwargs(kwargs)
        super().info(msg, *args, **self._merge_extra(clean, dynamic))

    def warning(self, msg, *args, **kwargs):
        clean, dynamic = self._split_kwargs(kwargs)
        super().warning(msg, *args, **self._merge_extra(clean, dynamic))

    def error(self, msg, *args, **kwargs):
        clean, dynamic = self._split_kwargs(kwargs)
        super().error(msg, *args, **self._merge_extra(clean, dynamic))

    def critical(self, msg, *args, **kwargs):
        clean, dynamic = self._split_kwargs(kwargs)
        super().critical(msg, *args, **self._merge_extra(clean, dynamic))


logging.setLoggerClass(KwargLogger)


class JSONFormatter(logging.Formatter):
    """Format log records into JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if hasattr(record, "extra_fields"):
            entry.update(record.extra_fields)
        elif hasattr(record, "task_id"):
            # Compatibility for plain logger calls using logging's `extra`.
            entry.update(
                {
                    k: getattr(record, k)
                    for k in ("task_id", "title", "outputs", "duration_ms")
                    if hasattr(record, k)
                }
            )

        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, ensure_ascii=False)


def _coerce_log_file(log_file: Optional[Union[str, Path]]) -> Path:
    """Resolve log file path and ensure parent exists."""
    if log_file is None:
        init_workspace()
        path = LOGS_DIR / "orchestrator_log.json"
    else:
        path = Path(log_file)
        if not path.is_absolute():
            path = LOGS_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(
    log_file: Optional[Union[str, Path]] = None,
    level: int = logging.INFO,
    also_console: bool = False,
) -> None:
    """Setup root logger with JSON file output."""
    resolved = _coerce_log_file(log_file)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    file_handler = logging.FileHandler(resolved, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(JSONFormatter())
    root.addHandler(file_handler)

    if also_console:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(console)


def get_logger(name: str = __name__) -> logging.Logger:
    """Get logger by name."""
    return logging.getLogger(name)


class ExtraAdapter(logging.LoggerAdapter):
    """Logger adapter that accepts extra kwargs as structured fields."""

    def process(self, msg, kwargs):
        extra = dict(self.extra)

        if "extra" in kwargs:
            raw_extra = kwargs.pop("extra")
            if isinstance(raw_extra, dict):
                extra.update(raw_extra)

        known_keys = {"exc_info", "stack_info", "stacklevel"}
        for key in list(kwargs.keys()):
            if key not in known_keys:
                extra[key] = kwargs.pop(key)

        kwargs["extra"] = {"extra_fields": extra}
        return msg, kwargs


def setup_logger(
    name: str,
    log_file: Optional[Union[str, Path]] = None,
    level: int = logging.INFO,
    also_console: bool = False,
) -> logging.Logger:
    """Backward-compatible alias: configure root logger and return named logger."""
    setup_logging(log_file=log_file, level=level, also_console=also_console)
    return get_logger(name)


class SimpleLogger:
    """Very simple line-based file logger."""

    def __init__(self, log_file: Union[str, Path]):
        self.log_file = _coerce_log_file(log_file)

    def _write(self, level: str, message: str):
        line = f"{datetime.now().isoformat()} [{level}] {message}\n"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line)

    def debug(self, message: str):
        self._write("DEBUG", message)

    def info(self, message: str):
        self._write("INFO", message)

    def warning(self, message: str):
        self._write("WARNING", message)

    def error(self, message: str):
        self._write("ERROR", message)


def get_simple_logger(log_file: Union[str, Path] = "simple.log") -> SimpleLogger:
    """Create a SimpleLogger."""
    return SimpleLogger(log_file)


class StructuredLogger:
    """JSONL logger for machine-readable logs."""

    def __init__(self, log_file: Union[str, Path]):
        self.log_file = _coerce_log_file(log_file)

    def _write(self, level: str, message: str, **kwargs):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            **kwargs,
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def debug(self, message: str, **kwargs):
        self._write("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs):
        self._write("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._write("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._write("ERROR", message, **kwargs)


def get_structured_logger(
    log_file: Union[str, Path] = "structured.jsonl",
) -> StructuredLogger:
    """Create a StructuredLogger."""
    return StructuredLogger(log_file)


def log_function_call(logger: logging.Logger, func_name: str, **kwargs):
    """Log function call with parameters."""
    params = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())
    logger.debug(f"Calling {func_name}({params})")


def log_error(logger: logging.Logger, error: Exception, context: Optional[Dict] = None):
    """Log error plus optional context."""
    logger.error(f"{type(error).__name__}: {error}", exc_info=True)
    if context:
        logger.error(f"Context: {context}")


@contextmanager
def log_context(logger: logging.Logger, title: str) -> Iterator[None]:
    """Context manager that logs section start/end and exceptions."""
    logger.info(f"[START] {title}")
    try:
        yield
        logger.info(f"[END] {title}")
    except Exception:
        logger.exception(f"[FAIL] {title}")
        raise


class RunLogger:
    """Run-scoped logger with convenience methods and compatibility fields."""

    def __init__(self, run_id: str, **context):
        init_workspace()
        self.run_id = run_id
        self.context = context
        self.log_file = LOGS_DIR / f"{run_id}.log"
        self.structured_file = LOGS_DIR / f"{run_id}.jsonl"

        self.logger = ExtraAdapter(
            get_logger(f"run.{run_id}"),
            {"run_id": run_id, **context},
        )
        self._simple = SimpleLogger(self.log_file)
        self._structured = StructuredLogger(self.structured_file)

    def _emit(self, level: str, message: str, **kwargs):
        # Unified structured root logging
        if level == "DEBUG":
            self.logger.debug(message, extra=kwargs)
            self._simple.debug(message)
            self._structured.debug(message, **kwargs)
        elif level == "WARNING":
            self.logger.warning(message, extra=kwargs)
            self._simple.warning(message)
            self._structured.warning(message, **kwargs)
        elif level == "ERROR":
            self.logger.error(message, extra=kwargs)
            self._simple.error(message)
            self._structured.error(message, **kwargs)
        elif level == "CRITICAL":
            self.logger.critical(message, extra=kwargs)
            self._simple.error(message)
            self._structured.error(message, **kwargs)
        else:
            self.logger.info(message, extra=kwargs)
            self._simple.info(message)
            self._structured.info(message, **kwargs)

    def info(self, message: str, **kwargs):
        self._emit("INFO", message, **kwargs)

    def debug(self, message: str, **kwargs):
        self._emit("DEBUG", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._emit("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._emit("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._emit("CRITICAL", message, **kwargs)

    def log_task(self, task_id: str, event: str, **kwargs):
        self.info(f"Task {task_id}: {event}", task_id=task_id, event=event, **kwargs)

    def log_llm_call(self, prompt: str, response: str, tokens_used: int, **kwargs):
        self.info(
            "LLM call",
            event="llm_call",
            prompt_length=len(prompt),
            response_length=len(response),
            tokens_used=tokens_used,
            **kwargs,
        )


def get_run_logger(run_id: Optional[str] = None, **context) -> RunLogger:
    """Create run logger with default timestamp run_id."""
    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    if "project_id" not in context:
        context["project_id"] = PROJECT_ID
    return RunLogger(run_id, **context)
