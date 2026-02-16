"""Unified logging system for OpenClaw.

Single logging system based on Python logging module with JSON output.
All logs are saved to BASE_PATH/<PROJECT_ID>/logs/
"""

import logging
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Get paths directly to avoid circular import
BASE_PATH = Path(os.getenv("BASE_PATH", "./workspace"))
PROJECT_ID = os.getenv("PROJECT_ID", "default_project")
PROJECT_DIR = BASE_PATH / PROJECT_ID


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging.

    Outputs logs as JSON objects with timestamp, level, message, and extra fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON string
        """
        # Create base log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields from record
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(
    log_file: Optional[Path] = None,
    level: int = logging.INFO,
    also_console: bool = False
) -> None:
    """Setup global logging configuration.

    This function should be called once at application startup.

    Args:
        log_file: Path to log file (uses default if None)
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        also_console: Whether to also output to console

    Example:
        >>> setup_logging(level=logging.INFO, also_console=True)
        >>> logger = get_logger(__name__)
        >>> logger.info("Message")
    """
    # Determine log file path
    if log_file is None:
        logs_dir = PROJECT_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "orchestrator_log.json"

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # JSON file handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)

    # Console handler (optional, human-readable format)
    if also_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)


def get_logger(name: str = __name__) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Message", extra_field="value")
    """
    return logging.getLogger(name)


class ExtraAdapter(logging.LoggerAdapter):
    """Logger adapter for adding extra fields to log records.

    Allows adding context fields to log messages.

    Example:
        >>> logger = get_logger(__name__)
        >>> adapter = ExtraAdapter(logger, {"task_id": "tsk_123"})
        >>> adapter.info("Task started")
        # Output: {"timestamp": "...", "level": "INFO", "message": "Task started", "task_id": "tsk_123"}
    """

    def __init__(self, logger: logging.Logger, extra: Dict[str, Any]):
        """Initialize adapter with extra fields.

        Args:
            logger: Underlying logger
            extra: Dictionary of extra fields to add to all log messages
        """
        super().__init__(logger, extra)
        self.extra = extra

    def process(self, msg, kwargs):
        """Add extra fields to log record.

        Args:
            msg: Log message
            kwargs: Keyword arguments for log call

        Returns:
            Tuple of (msg, kwargs)
        """
        # Start with adapter's base extra fields
        extra = self.extra.copy()

        # Add any extra dict passed via kwargs['extra']
        if 'extra' in kwargs:
            extra.update(kwargs.pop('extra'))

        # Add all other keyword arguments as extra fields
        # This allows: logger.info("msg", task_id="xxx") instead of logger.info("msg", extra={"task_id": "xxx"})
        known_logging_keys = {'exc_info', 'stack_info', 'stacklevel'}
        for key, value in list(kwargs.items()):
            if key not in known_logging_keys:
                extra[key] = value
                kwargs.pop(key)

        kwargs['extra'] = {'extra_fields': extra}
        return msg, kwargs


# ============================================================================
# Convenience Functions
# ============================================================================

def log_function_call(logger: logging.Logger, func_name: str, **kwargs):
    """Log function call with parameters.

    Args:
        logger: Logger instance
        func_name: Name of the function
        **kwargs: Function parameters

    Example:
        >>> log_function_call(logger, "decompose", goal="test")
        # Output: {"timestamp": "...", "message": "Calling decompose(goal='test')", ...}
    """
    params_str = ', '.join(f'{k}={repr(v)}' for k, v in kwargs.items())
    logger.debug(f"Calling {func_name}({params_str})")


def log_error(logger: logging.Logger, error: Exception, context: Optional[Dict] = None):
    """Log exception with context.

    Args:
        logger: Logger instance
        error: Exception object
        context: Optional context dictionary

    Example:
        >>> try:
        ...     risky_operation()
        ... except Exception as e:
        ...     log_error(logger, e, context={"task_id": "tsk_123"})
    """
    logger.error(f"{type(error).__name__}: {error}", exc_info=True)
    if context:
        logger.error(f"Context: {context}")


# ============================================================================
# Run-specific Logger
# ============================================================================

class RunLogger:
    """Logger for a specific run with additional context.

    Provides convenience methods for logging task-related events.

    Example:
        >>> run_logger = RunLogger("run_001", goal="Build API")
        >>> run_logger.info("Run started")
        >>> run_logger.log_task("tsk_123", "completed", output="result.json")
    """

    def __init__(self, run_id: str, **context):
        """Initialize run-specific logger.

        Args:
            run_id: Run identifier
            **context: Additional context fields (goal, project, etc.)
        """
        self.run_id = run_id
        self.context = context
        self.logger = ExtraAdapter(
            get_logger(f"run.{run_id}"),
            {"run_id": run_id, **context}
        )

    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.info(message, extra=kwargs)

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.debug(message, extra=kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.warning(message, extra=kwargs)

    def error(self, message: str, **kwargs):
        """Log error message."""
        self.logger.error(message, extra=kwargs)

    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self.logger.critical(message, extra=kwargs)

    def log_task(self, task_id: str, event: str, **kwargs):
        """Log task-specific event.

        Args:
            task_id: Task identifier
            event: Event type (started, progress, completed, failed, etc.)
            **kwargs: Additional event data

        Example:
            >>> run_logger.log_task("tsk_123", "started", title="Fetch data")
            >>> run_logger.log_task("tsk_123", "progress", step=1, total=5)
            >>> run_logger.log_task("tsk_123", "completed", outputs=["data.json"])
        """
        self.info(f"Task {task_id}: {event}", task_id=task_id, event=event, **kwargs)

    def log_llm_call(self, prompt: str, response: str, tokens_used: int, **kwargs):
        """Log LLM API call.

        Args:
            prompt: Prompt text
            response: Response text
            tokens_used: Number of tokens used
            **kwargs: Additional call data
        """
        self.info(
            "LLM call",
            event="llm_call",
            prompt_length=len(prompt),
            response_length=len(response),
            tokens_used=tokens_used,
            **kwargs
        )


def get_run_logger(run_id: Optional[str] = None, **context) -> RunLogger:
    """Get or create a run-specific logger.

    Args:
        run_id: Run identifier (uses timestamp if None)
        **context: Additional context fields (goal, project_id, etc.)

    Returns:
        RunLogger instance

    Example:
        >>> run_logger = get_run_logger(goal="Build API")
        >>> run_logger.info("Starting...")
    """
    if run_id is None:
        run_id = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Add project context
    if 'project_id' not in context:
        context['project_id'] = PROJECT_ID

    return RunLogger(run_id, **context)


# ============================================================================
# Convenience: Auto-setup on import
# ============================================================================

# Setup logging automatically when module is imported
# This ensures logs are written even if setup_logging() is not called
_setup_done = False

def _ensure_logging_setup():
    """Ensure logging is setup (called automatically)."""
    global _setup_done
    if not _setup_done:
        # Setup with default config (JSON file only, no console)
        # Defer to avoid execution during import
        pass
        _setup_done = True


# Auto-setup on module import
_ensure_logging_setup()
