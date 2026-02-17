"""Path management for OpenClaw workspace.

All metadata is stored under BASE_PATH/<PROJECT_ID>/.orchestrator/.
If BASE_PATH is not writable, fallback to local ./workspace.
"""

import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

PROJECT_ROOT = Path(__file__).parent.parent


def _is_writable_dir(path: Path) -> bool:
    """Return True when directory is writable (or creatable and writable)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            pass
        return True
    except Exception:
        return False


def _resolve_base_path() -> Path:
    """Resolve BASE_PATH from env with safe writable fallback."""
    configured = Path(os.getenv("BASE_PATH", "./workspace")).expanduser()
    if not configured.is_absolute():
        configured = (PROJECT_ROOT / configured).resolve()

    if _is_writable_dir(configured):
        return configured

    fallback = (PROJECT_ROOT / "workspace").resolve()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


BASE_PATH = _resolve_base_path()
PROJECT_ID = os.getenv("PROJECT_ID", "default_project")

# Add project_id layer to hierarchy
PROJECT_DIR = BASE_PATH / PROJECT_ID
ORCHESTRATOR_DIR = PROJECT_DIR / ".orchestrator"

# Directory structure under .orchestrator/
TASKS_DIR = ORCHESTRATOR_DIR / "tasks"      # Task metadata
STATE_DIR = ORCHESTRATOR_DIR / "state"      # Execution state
LOGS_DIR = ORCHESTRATOR_DIR / "logs"        # Execution logs
RUNS_DIR = ORCHESTRATOR_DIR / "runs"        # Run history


def init_workspace():
    """Initialize workspace directory structure.

    Creates all necessary directories if they don't exist.
    """
    directories = [
        ORCHESTRATOR_DIR,
        TASKS_DIR,
        STATE_DIR,
        LOGS_DIR,
        RUNS_DIR,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def get_task_metadata_path(task_id: str) -> Path:
    """Get path for task metadata file.

    Args:
        task_id: Task identifier (e.g., "tsk_...")

    Returns:
        Path to task metadata JSON file
    """
    return TASKS_DIR / f"{task_id}.json"


def get_run_state_path(run_id: str) -> Path:
    """Get path for run state file.

    Args:
        run_id: Run identifier (timestamp or UUID)

    Returns:
        Path to run state JSON file
    """
    return STATE_DIR / f"run_{run_id}.json"


def get_log_path(run_id: str, task_id: str = None) -> Path:
    """Get path for log file.

    Args:
        run_id: Run identifier
        task_id: Optional task identifier (for task-specific logs)

    Returns:
        Path to log file
    """
    if task_id:
        return LOGS_DIR / f"{run_id}_{task_id}.log"
    return LOGS_DIR / f"{run_id}.log"


def get_artifact_path(filename: str) -> Path:
    """Get path for artifact file.

    Artifacts are stored in project directory (not .orchestrator/).

    Args:
        filename: Artifact filename (e.g., "hn_posts.json")

    Returns:
        Path to artifact file
    """
    return PROJECT_DIR / filename


def get_task_dir(task_id: str) -> Path:
    """Get path for task-specific directory.

    Each task can have its own directory for files.

    Args:
        task_id: Task identifier

    Returns:
        Path to task directory
    """
    task_dir = PROJECT_DIR / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def cleanup_old_runs(keep_last_n: int = 10):
    """Remove old run state files, keeping only the most recent.

    Args:
        keep_last_n: Number of recent runs to keep
    """
    if not STATE_DIR.exists():
        return

    run_files = sorted(STATE_DIR.glob("run_*.json"),
                      key=lambda p: p.stat().st_mtime,
                      reverse=True)

    # Remove old runs
    for old_file in run_files[keep_last_n:]:
        old_file.unlink()


def get_workspace_info() -> dict:
    """Get workspace information.

    Returns:
        Dictionary with workspace paths and status
    """
    return {
        "base_path": str(BASE_PATH),
        "project_id": PROJECT_ID,
        "project_dir": str(PROJECT_DIR),
        "orchestrator_dir": str(ORCHESTRATOR_DIR),
        "tasks_dir": str(TASKS_DIR),
        "state_dir": str(STATE_DIR),
        "logs_dir": str(LOGS_DIR),
        "runs_dir": str(RUNS_DIR),
        "base_path_exists": BASE_PATH.exists(),
        "project_dir_exists": PROJECT_DIR.exists(),
        "orchestrator_dir_exists": ORCHESTRATOR_DIR.exists(),
    }
