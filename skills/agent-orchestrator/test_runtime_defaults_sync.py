from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_runtime_defaults_sync_check_passes() -> None:
    root = Path(__file__).resolve().parent
    cmd = [sys.executable, "scripts/check_runtime_defaults.py"]
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
