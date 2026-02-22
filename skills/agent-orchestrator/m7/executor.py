import os
import re
import time
import json
import shutil
import hashlib
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
from typing import Any

from .parser import parse_messages
from utils.task_context_signature import sign_task_context, verify_task_context_signature


class Executor:
    TERMINAL_PROTOCOL_VERSION = "v2"
    TERMINAL_EVENTS = {"task_completed", "task_failed", "task_waiting"}

    def __init__(self, scheduler, adapter, watcher, artifacts_dir: str | None = None, state_store=None):
        self.scheduler = scheduler
        self.adapter = adapter
        self.watcher = watcher
        self.state_store = state_store
        self.task_to_session: dict[str, str] = {}
        self.session_to_task: dict[str, str] = {}
        self.waiting_tasks: dict[str, str] = {}
        self.notifier = None
        self.run_id = ""
        self.max_parallel_tasks = max(1, int(os.getenv("ORCH_MAX_PARALLEL_TASKS", "2")))
        self.task_started_at: dict[str, float] = {}
        self.task_durations_ms: list[int] = []
        self.task_retry_count: defaultdict[str, int] = defaultdict(int)
        self.started_count = 0
        self.completed_count = 0
        self.failed_count = 0
        self.agent_stats: defaultdict[str, dict] = defaultdict(lambda: {"started": 0, "completed": 0, "failed": 0})
        self.artifacts_dir = Path(artifacts_dir or os.getenv("ORCH_ARTIFACTS_DIR", "./workspace/artifacts"))
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self.compat_protocol = os.getenv("ORCH_TERMINAL_COMPAT", "1").strip() != "0"
        self.validate_non_empty = os.getenv("ORCH_OUTPUT_VALIDATE_NON_EMPTY", "0") == "1"
        self.validate_freshness = os.getenv("ORCH_OUTPUT_VALIDATE_FRESHNESS", "0") == "1"
        self.validate_json_schema = os.getenv("ORCH_OUTPUT_VALIDATE_JSON", "0") == "1"
        self.output_max_age_min = max(1, int(os.getenv("ORCH_OUTPUT_MAX_AGE_MINUTES", "120")))
        self.max_retries_transient = int(os.getenv("ORCH_FAILURE_RETRY_TRANSIENT", "2"))
        self.max_retries_logic = int(os.getenv("ORCH_FAILURE_RETRY_LOGIC", "0"))
        self._dedupe_failures: dict[str, str] = {}
        self.task_context_hmac_required = os.getenv("TASK_CONTEXT_HMAC_KEY_REQUIRED", "false").strip().lower() in {"1", "true", "yes", "on", "prod", "production"}
        self.context_hmac_key = os.getenv("TASK_CONTEXT_HMAC_KEY", "")
        if self.task_context_hmac_required and not self.context_hmac_key.strip():
            raise RuntimeError("TASK_CONTEXT_HMAC_KEY is required for runtime context verification")
        self._terminal_resolved: set[str] = set()
        self._artifact_recovery_events: list[dict] = []

    def _task_context_path(self, task_id: str) -> Path:
        return self.artifacts_dir / task_id / "task_context.json"

    def _build_task_context(self, task_id: str, task: dict) -> dict:
        outputs = [str(o) for o in (task.get("outputs", []) or [])]
        context = {
            "run_id": self.run_id,
            "project_id": os.getenv("PROJECT_ID", "default_project"),
            "task_id": task_id,
            "protocol_version": self.TERMINAL_PROTOCOL_VERSION,
            "artifacts_root": str(self.artifacts_dir),
            "task_artifacts_dir": str(self.artifacts_dir / task_id),
            "required_outputs": outputs,
            "allowed_output_filenames": outputs,
            "inputs": list(task.get("inputs", []) or []),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        context_payload = json.dumps(context, sort_keys=True, ensure_ascii=False).encode("utf-8")
        context["context_sha256"] = hashlib.sha256(context_payload).hexdigest()
        if self.context_hmac_key:
            context["context_sig"] = sign_task_context(context, self.context_hmac_key)
        return context

    def _write_task_context(self, task_id: str, task: dict) -> dict:
        if not task_id:
            return {}
        path = self._task_context_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        context = self._build_task_context(task_id, task)
        path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
        return context

    def _load_task_context(self, task_id: str) -> dict:
        path = self._task_context_path(task_id)
        if not path.exists():
            raise RuntimeError(f"missing task_context: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("invalid task_context format")
        return data

    def _validate_task_context(self, task_id: str) -> tuple[bool, str | None]:
        try:
            data = self._load_task_context(task_id)
            context_sig = str(data.pop("context_sig", ""))
            context_hash = str(data.pop("context_sha256", ""))
            if not context_hash:
                return False, "CONTEXT_HASH_MISSING"
            payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
            if hashlib.sha256(payload).hexdigest() != context_hash:
                return False, "CONTEXT_HASH_MISMATCH"
            if self.context_hmac_key:
                if not context_sig:
                    return False, "CONTEXT_SIGNATURE_MISSING"
                signed_payload = dict(data)
                signed_payload["context_sha256"] = context_hash
                if not verify_task_context_signature(signed_payload, context_sig, self.context_hmac_key):
                    return False, "CONTEXT_SIGNATURE_INVALID"
            return True, None
        except Exception:
            return False, "CONTEXT_SIGNATURE_INVALID"

    def _failure_dedupe_key(self, task_id: str, error: object) -> str:
        return hashlib.sha256(
            f"{self.run_id}:{task_id}:{error}".encode("utf-8")
        ).hexdigest()

    def _set_task_state(self, task_id: str, status: str, error: str | None = None) -> None:
        if self.state_store is None:
            return
        self.state_store.update(task_id, status, error=error)

    def _classify_error(self, err: BaseException, op_name: str) -> dict[str, Any]:
        reason = f"{type(err).__name__}: {err}"
        lower = reason.lower()
        if "timeout" in lower or "timed out" in lower:
            failure_class = "transient"
            retryable = True
            recovery = "Retry with a short backoff."
        elif "permission" in lower or "auth" in lower:
            failure_class = "logic"
            retryable = False
            recovery = "Fix credentials/ACL and rerun."
        elif "network" in lower or "connection" in lower:
            failure_class = "resource"
            retryable = True
            recovery = "Requeue task after infra check."
        elif "human" in lower:
            failure_class = "human_reject"
            retryable = False
            recovery = "Manual intervention required in review."
        else:
            failure_class = "logic"
            retryable = False
            recovery = "Inspect operator instruction and task payload."

        return {
            "failure_class": failure_class,
            "retryable": retryable,
            "error_code": f"EXECUTOR_SAFE_WRAPPER_{op_name.upper()}_ERROR",
            "root_cause": reason,
            "impact": f"{op_name} failed; runtime flow may be partially advanced",
            "recovery_plan": recovery,
        }

    def _standard_error(self, error_code: str, root_cause: str, impact: str, recovery_plan: str, failure_class: str | None = None, retryable: bool = False) -> dict:
        return {
            "error_code": error_code,
            "root_cause": root_cause,
            "impact": impact,
            "recovery_plan": recovery_plan,
            "failure_class": failure_class or "logic",
            "retryable": retryable,
        }

    def _safe_call(self, op_name: str, fn, *args, **kwargs):
        try:
            return True, fn(*args, **kwargs), None
        except Exception as e:
            cls = self._classify_error(e, op_name)
            err = self._standard_error(
                error_code=cls["error_code"],
                root_cause=cls["root_cause"],
                impact=cls["impact"],
                recovery_plan=cls["recovery_plan"],
                failure_class=cls["failure_class"],
                retryable=cls["retryable"],
            )
            return False, None, err

    def _release_task_session(self, task_id: str, session: str | None, *, keep_waiting_meta: bool = False) -> None:
        if session:
            self.adapter.mark_session_idle(session)
            self.watcher.unwatch(session)
            self.session_to_task.pop(session, None)
        self.task_to_session.pop(task_id, None)
        if not keep_waiting_meta:
            self.waiting_tasks.pop(task_id, None)

    def _failure_retry_policy(self, failure_class: str) -> dict[str, Any]:
        if failure_class == "transient":
            return {"retryable": True, "max_retries": self.max_retries_transient}
        if failure_class == "resource":
            return {"retryable": True, "max_retries": 1}
        if failure_class == "logic":
            return {"retryable": self.max_retries_logic > 0, "max_retries": self.max_retries_logic}
        return {"retryable": False, "max_retries": 0}

    def _build_terminal_payload(self, task: dict, event: str, extras: dict | None = None) -> dict:
        failure = (task.get("error") or {}).copy() if isinstance(task.get("error"), dict) else {}
        payload = {
            "run_id": self.run_id,
            "task_id": str(task.get("id") or task.get("task_id") or ""),
            "title": str(task.get("title", "")),
            "status_protocol": self.TERMINAL_PROTOCOL_VERSION,
            "event": event,
            "terminal_state": {
                "task_completed": "completed",
                "task_failed": "failed",
                "task_waiting": "waiting_human",
            }.get(event, "unknown"),
            "compat_mode": self.compat_protocol,
            "failure": failure,
        }
        policy = self._failure_retry_policy(str(failure.get("failure_class", "logic")))
        payload.update({"retry_policy": policy})
        if extras:
            payload.update(extras)
        return payload

    def _notify(self, tasks_by_id: dict, task_id: str, event: str, **extra) -> None:
        notifier = self.notifier
        if notifier is None:
            return
        task = tasks_by_id.get(task_id, {})
        agent = str(task.get("assigned_to") or "unassigned")
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "task_id": task_id,
            "title": str(task.get("title", "")),
            "agent": agent,
            **extra,
        }
        if event in self.TERMINAL_EVENTS:
            payload = self._build_terminal_payload(task, event, payload)

        notifier.notify(agent, event, payload)
        if event in {"task_failed", "task_waiting"} and agent != "main":
            fail_key = self._failure_dedupe_key(task_id, payload.get("error"))
            if self._dedupe_failures.get(task_id) != fail_key:
                self._dedupe_failures[task_id] = fail_key
                notifier.notify("main", event, {**payload, "source_agent": agent, "dedupe_key": fail_key})

    def _build_task_prompt(self, task: dict) -> str:
        title = str(task.get("title", "")).strip()
        description = str(task.get("description", "")).strip()
        inputs = task.get("inputs", []) or []
        outputs = task.get("outputs", []) or []
        done_when = task.get("done_when", []) or []
        task_id = str(task.get("id", "")).strip() or str(task.get("task_id", "")).strip()

        task_artifacts_dir = self.artifacts_dir / task_id if task_id else self.artifacts_dir

        lines = [
            "You are executing a task from a workflow engine.",
            "",
            f"Task: {title}",
        ]
        if description:
            lines.extend(["", f"Description: {description}"])
        if inputs:
            lines.extend(["", "Inputs:"])
            for item in inputs:
                lines.append(f"- {item}")
        if outputs:
            lines.extend(["", "Required Outputs:"])
            for item in outputs:
                lines.append(f"- {item}")
        if done_when:
            lines.extend(["", "Done Criteria:"])
            for item in done_when:
                lines.append(f"- {item}")

        lines.extend(
            [
                "",
                f"Shared artifacts directory for this workflow: {self.artifacts_dir}",
                f"Task-scoped artifacts directory (MUST use for this task): {task_artifacts_dir}",
                "Rules:",
                "- Prefer existing skills/capabilities first; avoid manual ad-hoc flows when a skill path exists.",
                "- Write every declared output file into the TASK-SCOPED artifacts directory above.",
                "- Never write required outputs to workflow root artifacts dir when a task-scoped dir is provided.",
                "- If an input refers to an artifact filename, first read from task-scoped dir, then workflow shared dir if needed.",
                "- Use exact output filenames from Required Outputs whenever possible.",
                "- Request user input only when strictly necessary and unavailable via configured tools/skills.",
                "",
                "When finished output exactly:",
                "[TASK_DONE]",
                "",
                "If impossible output exactly:",
                "[TASK_FAILED]",
                "",
                "If you need user input output exactly:",
                "[TASK_WAITING] <question>",
            ]
        )
        return "\n".join(lines)

    def _expected_output_paths(self, task: dict) -> list[Path]:
        outputs = task.get("outputs", []) or []
        task_id = str(task.get("id", "")).strip() or str(task.get("task_id", "")).strip()
        paths: list[Path] = []
        for raw in outputs:
            name = str(raw or "").strip()
            if not name:
                continue
            # Keep artifact exchange deterministic across agents and isolate by task.
            fname = Path(name).name
            if task_id:
                paths.append(self.artifacts_dir / task_id / fname)
            else:
                paths.append(self.artifacts_dir / fname)
        return paths

    def _is_fresh_output(self, path: Path) -> bool:
        if not self.validate_freshness:
            return True
        if not path.exists():
            return False
        age_minutes = (time.time() - path.stat().st_mtime) / 60
        return age_minutes <= self.output_max_age_min

    def _normalize_recovery_paths(self, task: dict) -> list[dict]:
        return [
            r for r in (task.get("artifact_recoveries") or []) if isinstance(r, dict)
        ]

    def _find_recovery_mapping(self, task: dict, filename: str) -> dict | None:
        target = Path(filename).name
        for raw in self._normalize_recovery_paths(task):
            source_task_id = str(raw.get("source_task_id") or "").strip()
            source_path = str(raw.get("source_path") or "").strip()
            target_name = str(raw.get("target_filename") or "").strip() or Path(source_path).name
            if not source_task_id or not source_path:
                continue
            if target_name == target:
                return {
                    "source_task_id": source_task_id,
                    "source_path": source_path,
                    "reason": str(raw.get("reason") or ""),
                }
        return None

    @staticmethod
    def _normalize_artifact_name(name: str) -> str:
        base = Path(str(name or "")).name.lower().strip()
        stem = Path(base).stem
        return re.sub(r"[^a-z0-9]+", "_", stem).strip("_")

    def _resolve_output_path(self, expected_path: Path) -> Path:
        if expected_path.exists():
            return expected_path
        task_dir = expected_path.parent
        if not task_dir.exists() or not task_dir.is_dir():
            return expected_path

        expected_norm = self._normalize_artifact_name(expected_path.name)
        if not expected_norm:
            return expected_path

        for cand in task_dir.iterdir():
            if not cand.is_file():
                continue
            if self._normalize_artifact_name(cand.name) == expected_norm:
                return cand
        return expected_path

    def _validate_terminal_payload(self, task_id: str, event: str, payload: object) -> tuple[bool, str | None]:
        if isinstance(payload, str):
            s = payload.strip()
            if not s and self.compat_protocol:
                payload = {}
            else:
                try:
                    payload = json.loads(payload)
                except Exception:
                    return False, "terminal payload must be JSON object"

        if payload is None and self.compat_protocol:
            payload = {}

        if not isinstance(payload, dict):
            return False, "terminal payload must be object with fields event/type/run_id/task_id"

        # v2 compat: normalize legacy/partial terminal payload before strict validation.
        if self.compat_protocol:
            alias = {
                "task_completed": "done",
                "task_failed": "failed",
                "task_waiting": "waiting",
            }
            ev_raw = str(payload.get("event") or "").strip()
            ty_raw = str(payload.get("type") or "").strip()
            ev = alias.get(ev_raw, ev_raw)
            ty = alias.get(ty_raw, ty_raw)

            if not ev and ty:
                ev = ty
            if not ty and ev:
                ty = ev
            if not ev:
                ev = event
            if not ty:
                ty = event

            payload["event"] = ev
            payload["type"] = ty
            payload.setdefault("run_id", self.run_id)
            payload.setdefault("task_id", task_id)

        required = {"event", "type", "run_id", "task_id"}
        missing = [field for field in sorted(required) if field not in payload]
        if missing:
            return False, f"missing terminal fields: {','.join(missing)}"

        terminal_event = str(payload.get("event"))
        terminal_type = str(payload.get("type"))
        payload_run_id = str(payload.get("run_id") or "")
        payload_task_id = str(payload.get("task_id") or "")

        if terminal_event != event:
            return False, f"event mismatch: expected {event}, got {terminal_event}"
        if terminal_type != event:
            return False, f"type mismatch: expected {event}, got {terminal_type}"
        if payload_task_id != task_id:
            return False, f"task_id mismatch: expected {task_id}, got {payload_task_id}"
        if payload_run_id != self.run_id:
            return False, f"run_id mismatch: expected {self.run_id}, got {payload_run_id}"
        return True, None

    def _validate_task_outputs(self, task: dict) -> tuple[bool, list[str]]:
        expected = self._expected_output_paths(task)
        task_id = str(task.get("id") or task.get("task_id") or "").strip()
        if not expected:
            return True, []

        issues: list[str] = []
        for p in expected:
            resolved = self._resolve_output_path(p)
            if not resolved.exists():
                recovery = self._find_recovery_mapping(task, p.name)
                if not recovery:
                    issues.append(f"missing:{p}")
                    continue

                source_task_id = recovery["source_task_id"]
                source_path = recovery["source_path"]
                reason = recovery.get("reason", "")

                source_task_dir = (self.artifacts_dir / source_task_id).resolve()
                if not source_task_dir.exists():
                    issues.append(f"invalid_recovery_source_task:{source_task_id}")
                    continue

                source_file = (source_task_dir / source_path).resolve()
                if not source_file.exists() or source_file.is_dir():
                    issues.append(f"invalid_recovery_source_path:{source_file}")
                    continue
                source_root = str(source_task_dir) + "/"
                if not str(source_file).startswith(source_root):
                    issues.append(f"unsafe_recovery_source_path:{source_file}")
                    continue

                try:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(source_file), str(p))
                    resolved = p
                except Exception as exc:
                    issues.append(f"recovery_failed:{p}:{exc}")
                    continue

                self._artifact_recovery_events.append(
                    {
                        "task_id": task_id,
                        "output": p.name,
                        "source_task_id": source_task_id,
                        "source_path": source_path,
                        "reason": reason,
                    }
                )
                self._notify(
                    {task_id: task},
                    task_id,
                    "artifact_recovery",
                    output=p.name,
                    source_task_id=source_task_id,
                    source_path=source_path,
                    reason=reason,
                    status="recovered",
                )

            if self.validate_non_empty and resolved.stat().st_size == 0:
                issues.append(f"empty:{resolved}")
                continue
            if self.validate_freshness and not self._is_fresh_output(resolved):
                issues.append(f"stale:{resolved}")
                continue
            if self.validate_json_schema and resolved.suffix.lower() == ".json":
                try:
                    json.loads(resolved.read_text())
                except Exception as e:
                    issues.append(f"invalid_json:{resolved}:{e}")

        return len(issues) == 0, issues

    def _record_task_end(self, task_id: str, success: bool, tasks_by_id: dict) -> None:
        started = self.task_started_at.pop(task_id, None)
        if started is not None:
            self.task_durations_ms.append(int((time.monotonic() - started) * 1000))
        agent = str((tasks_by_id.get(task_id) or {}).get("assigned_to") or "unassigned")
        if success:
            self.completed_count += 1
            self.agent_stats[agent]["completed"] += 1
        else:
            self.failed_count += 1
            self.agent_stats[agent]["failed"] += 1

    def _convergence_report(self, tasks_by_id: dict) -> dict:
        durations = sorted(self.task_durations_ms)
        avg = (sum(durations) / len(durations)) if durations else 0
        p95 = durations[int(len(durations) * 0.95) - 1] if durations else 0
        blocked = sorted(
            tid
            for tid in tasks_by_id
            if tid not in getattr(self.scheduler, "done", set())
            and tid not in getattr(self.scheduler, "failed", set())
        )
        return {
            "total": len(tasks_by_id),
            "started": self.started_count,
            "completed": self.completed_count,
            "failed": self.failed_count,
            "by_agent": dict(self.agent_stats),
            "avg_duration_ms": int(avg),
            "p95_duration_ms": int(p95),
            "retry_count": sum(self.task_retry_count.values()),
            "blocked": blocked,
            "blocked_by": {tid: list((tasks_by_id.get(tid) or {}).get("deps", []) or []) for tid in blocked},
            "max_parallel_tasks": self.max_parallel_tasks,
            "protocol": self.TERMINAL_PROTOCOL_VERSION,
            "compat_protocol": self.compat_protocol,
        }

    def run(self, tasks_by_id: dict) -> dict:
        idle_timeout_seconds = int(os.getenv("ORCH_EXECUTOR_IDLE_TIMEOUT_SECONDS", "60"))
        last_progress_at = time.monotonic()

        while not self.scheduler.is_finished():
            progressed = False
            ok_runnable, runnable, runnable_err = self._safe_call("get_runnable_tasks", self.scheduler.get_runnable_tasks)
            if not ok_runnable:
                return {
                    "status": "failed",
                    "waiting": self.waiting_tasks,
                    "error": runnable_err,
                    "convergence_report": self._convergence_report(tasks_by_id),
                }
            available_slots = max(0, self.max_parallel_tasks - len(self.task_to_session))
            if available_slots == 0 and runnable:
                self._notify({}, "", "parallel_throttled", message="parallel slots exhausted")
            for agent, task_id in runnable[:available_slots]:
                session = self.adapter.ensure_session(agent)

                if self.adapter.is_session_idle(session):
                    self.adapter.mark_session_busy(session)
                    ok_start, _, start_err = self._safe_call("start_task", self.scheduler.start_task, task_id)
                    if not ok_start:
                        self.adapter.mark_session_idle(session)
                        return {
                            "status": "failed",
                            "waiting": self.waiting_tasks,
                            "error": start_err,
                            "convergence_report": self._convergence_report(tasks_by_id),
                        }
                    self.task_retry_count[task_id] += 1
                    self.started_count += 1
                    self.agent_stats[str(agent or "unassigned")]["started"] += 1
                    self.task_started_at[task_id] = time.monotonic()
                    self._set_task_state(task_id, "running")
                    self._notify(tasks_by_id, task_id, "task_dispatched")
                    self._notify(tasks_by_id, task_id, "parallel_started", max_parallel_tasks=self.max_parallel_tasks)
                    self.watcher.watch(session)
                    self.task_to_session[task_id] = session
                    self.session_to_task[session] = task_id
                    last_progress_at = time.monotonic()

                    context = self._write_task_context(task_id, tasks_by_id[task_id])
                    prompt = self._build_task_prompt(tasks_by_id[task_id])
                    prompt += "\nTask context: " + str(self._task_context_path(task_id)) + "\n"
                    prompt += "Task context hash: " + str(context.get("context_sha256", "")) + "\n"
                    try:
                        self.adapter.send_message(session, prompt)
                    except Exception as e:
                        ok_finish, _, finish_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, False)
                        if not ok_finish:
                            self._release_task_session(task_id, session)
                            return {
                                "status": "failed",
                                "waiting": self.waiting_tasks,
                                "error": finish_err,
                                "convergence_report": self._convergence_report(tasks_by_id),
                            }
                        self._record_task_end(task_id, False, tasks_by_id)
                        self._set_task_state(task_id, "failed", error=f"dispatch failed: {e}")
                        self._notify(
                            tasks_by_id,
                            task_id,
                            "task_failed",
                            error=f"dispatch failed: {e}",
                        )
                        self._release_task_session(task_id, session)
                        progressed = True

            # Watch active sessions and resolve outputs.
            active_sessions = list(self.task_to_session.values())
            for session in active_sessions:
                messages = self.watcher.drain(session)
                if not messages:
                    continue
                task_id = self.session_to_task.get(session)
                if not task_id:
                    continue
                parsed_events = parse_messages("\n".join(messages))
                if not parsed_events:
                    continue

                for ev in parsed_events:
                    if task_id in self._terminal_resolved:
                        continue
                    progressed = True
                    etype = ev.get("type")
                    payload_text = ev.get("payload")
                    if isinstance(payload_text, (dict, list)):
                        try:
                            payload_text = json.dumps(payload_text)
                        except Exception:
                            payload_text = str(payload_text)
                    parse_err = ev.get("error")
                    if etype == "malformed":
                        ok_finish, _, finish_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, False)
                        err = self._standard_error(
                            error_code="MALFORMED_PAYLOAD",
                            root_cause=str(payload_text or parse_err),
                            impact="protocol malformed, task stopped",
                            recovery_plan="Ask agent to emit valid [TASK_DONE]/[TASK_FAILED]/[TASK_WAITING]",
                            failure_class="logic",
                            retryable=False,
                        )
                        if not ok_finish:
                            return {
                                "status": "failed",
                                "waiting": self.waiting_tasks,
                                "error": finish_err,
                                "convergence_report": self._convergence_report(tasks_by_id),
                            }
                        self._terminal_resolved.add(task_id)
                        self._record_task_end(task_id, False, tasks_by_id)
                        self._set_task_state(task_id, "failed", error="Malformed terminal payload")
                        self._notify(tasks_by_id, task_id, "task_failed", error=err)
                        self._release_task_session(task_id, session)
                        continue

                    terminal_ok, terminal_err = self._validate_terminal_payload(task_id, etype, payload_text)
                    if not terminal_ok:
                        ok_finish, _, finish_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, False)
                        err = self._standard_error(
                            error_code="MALFORMED_PAYLOAD",
                            root_cause=terminal_err,
                            impact="terminal payload schema mismatch",
                            recovery_plan="Re-emit terminal signal with required fields event/type/run_id/task_id and task-consistent ids",
                            failure_class="logic",
                            retryable=False,
                        )
                        if not ok_finish:
                            return {
                                "status": "failed",
                                "waiting": self.waiting_tasks,
                                "error": finish_err,
                                "convergence_report": self._convergence_report(tasks_by_id),
                            }
                        self._terminal_resolved.add(task_id)
                        self._record_task_end(task_id, False, tasks_by_id)
                        self._set_task_state(task_id, "failed", error=terminal_err)
                        self._notify(tasks_by_id, task_id, "task_failed", error=err)
                        self._release_task_session(task_id, session)
                        continue

                    if etype == "done":
                        ctx_ok, ctx_err = self._validate_task_context(task_id)
                        if not ctx_ok:
                            ok_fail, _, fail_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, False)
                            if not ok_fail:
                                return {
                                    "status": "failed",
                                    "waiting": self.waiting_tasks,
                                    "error": fail_err,
                                    "convergence_report": self._convergence_report(tasks_by_id),
                                }
                            self._terminal_resolved.add(task_id)
                            self._record_task_end(task_id, False, tasks_by_id)
                            self._set_task_state(task_id, "failed", error=ctx_err or "CONTEXT_SIGNATURE_INVALID")
                            self._notify(tasks_by_id, task_id, "task_failed", error=ctx_err or "CONTEXT_SIGNATURE_INVALID")
                            self._release_task_session(task_id, session)
                            continue

                        valid, details = self._validate_task_outputs(tasks_by_id[task_id])
                        if not valid:
                            ok_fail, _, fail_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, False)
                            if not ok_fail:
                                return {
                                    "status": "failed",
                                    "waiting": self.waiting_tasks,
                                    "error": fail_err,
                                    "convergence_report": self._convergence_report(tasks_by_id),
                                }
                            self._terminal_resolved.add(task_id)
                            self._record_task_end(task_id, False, tasks_by_id)
                            self._set_task_state(task_id, "failed", error=f"output validation failed: {', '.join(details)}")
                            self._notify(tasks_by_id, task_id, "task_failed", error=f"output validation failed: {', '.join(details)}")
                            self._release_task_session(task_id, session)
                            continue

                        ok_finish, _, finish_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, True)
                        if not ok_finish:
                            return {
                                "status": "failed",
                                "waiting": self.waiting_tasks,
                                "error": finish_err,
                                "convergence_report": self._convergence_report(tasks_by_id),
                            }
                        self._terminal_resolved.add(task_id)
                        self._record_task_end(task_id, True, tasks_by_id)
                        self._set_task_state(task_id, "completed")
                        self._notify(tasks_by_id, task_id, "task_completed")
                        self._release_task_session(task_id, session)

                    elif etype == "failed":
                        ok_finish, _, finish_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, False)
                        if not ok_finish:
                            return {
                                "status": "failed",
                                "waiting": self.waiting_tasks,
                                "error": finish_err,
                                "convergence_report": self._convergence_report(tasks_by_id),
                            }
                        failure = self._standard_error(
                            error_code="TASK_SIGNAL_FAILED",
                            root_cause=payload_text or "agent reported failure",
                            impact="agent task failed",
                            recovery_plan="Fix root cause and rerun task",
                            failure_class="logic",
                            retryable=False,
                        )
                        self._terminal_resolved.add(task_id)
                        self._record_task_end(task_id, False, tasks_by_id)
                        self._set_task_state(task_id, "failed", error=failure["root_cause"])
                        self._notify(tasks_by_id, task_id, "task_failed", error=failure)
                        self._release_task_session(task_id, session)

                    elif etype == "waiting":
                        # Localized waiting: do not block unrelated tasks in the same run.
                        question = ev.get("question") or payload_text or ""
                        self.waiting_tasks[task_id] = question
                        if hasattr(self.scheduler, "pause_task"):
                            self.scheduler.pause_task(task_id)
                        self._set_task_state(task_id, "waiting_human", error=None)
                        self._notify(tasks_by_id, task_id, "task_waiting", question=question)
                        # Keep session clean so other tasks can reuse resources.
                        self._release_task_session(task_id, session, keep_waiting_meta=True)

            if not progressed:
                if time.monotonic() - last_progress_at > idle_timeout_seconds:
                    return {
                        "status": "waiting" if self.waiting_tasks else "stalled",
                        "waiting": self.waiting_tasks,
                        "error": {
                            "error_code": "RUNNER_IDLE_TIMEOUT",
                            "root_cause": f"no task progress for {idle_timeout_seconds}s",
                        },
                        "convergence_report": self._convergence_report(tasks_by_id),
                    }

        return {
            "status": "finished",
            "waiting": self.waiting_tasks,
            "convergence_report": self._convergence_report(tasks_by_id),
        }
