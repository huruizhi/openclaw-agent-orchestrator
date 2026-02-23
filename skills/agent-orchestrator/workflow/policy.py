from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivityPolicy:
    timeout_seconds: int
    max_attempts: int
    initial_interval_seconds: int
    backoff_coefficient: float
    max_interval_seconds: int


POLICY_PRESETS: dict[str, ActivityPolicy] = {
    "fast": ActivityPolicy(timeout_seconds=30, max_attempts=2, initial_interval_seconds=1, backoff_coefficient=2.0, max_interval_seconds=5),
    "default": ActivityPolicy(timeout_seconds=120, max_attempts=3, initial_interval_seconds=2, backoff_coefficient=2.0, max_interval_seconds=20),
    "slow": ActivityPolicy(timeout_seconds=300, max_attempts=4, initial_interval_seconds=5, backoff_coefficient=2.0, max_interval_seconds=60),
}

TASK_POLICY_MATRIX: dict[str, str] = {
    "dispatch": "fast",
    "wait_signal": "default",
    "validate": "default",
    "terminal": "slow",
}


def get_activity_policy(task_step: str) -> ActivityPolicy:
    preset_name = TASK_POLICY_MATRIX.get(task_step, "default")
    return POLICY_PRESETS[preset_name]
