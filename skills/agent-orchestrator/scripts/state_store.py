#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
MAX_ATTEMPTS = 2
LEASE_SECONDS = 60
STALE_TIMEOUT_SECONDS = 120


def load_env() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str | None) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def resolve_project_id(override: str | None = None) -> str:
    if override and str(override).strip():
        return str(override).strip()
    return os.getenv("PROJECT_ID", "default_project").strip() or "default_project"


def base_path() -> Path:
    base = os.getenv("BASE_PATH", "./workspace").strip() or "./workspace"
    p = Path(base)
    if not p.is_absolute():
        p = (ROOT_DIR / p).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_root(project_id: str | None = None) -> Path:
    p = base_path() / resolve_project_id(project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path(project_id: str | None = None) -> Path:
    p = project_root(project_id) / ".orchestrator" / "state" / "orchestrator.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def snapshot_path(project_id: str | None, job_id: str) -> Path:
    p = project_root(project_id) / ".orchestrator" / "state" / "jobs" / f"{job_id}.snapshot.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class StateStore:
    def __init__(self, project_id: str | None = None):
        self.project_id = resolve_project_id(project_id)
        self.path = db_path(self.project_id)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    audit_decision TEXT NOT NULL DEFAULT 'pending',
                    audit_revision TEXT NOT NULL DEFAULT '',
                    run_id TEXT,
                    last_result TEXT,
                    error TEXT,
                    human_inputs TEXT,
                    worker_id TEXT,
                    runner_pid INTEGER,
                    lease_until TEXT,
                    heartbeat_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 2,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_notified_status TEXT,
                    last_main_heartbeat_ts INTEGER,
                    last_heartbeat_log_ts INTEGER
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    pid INTEGER,
                    worker_id TEXT,
                    lease_until TEXT,
                    heartbeat_at TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    meta TEXT,
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    agent TEXT,
                    error TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    run_id TEXT,
                    ts TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload TEXT,
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id, id);
                """
            )

    def submit_job(self, goal: str) -> dict[str, Any]:
        now = utc_now()
        job_id = uuid.uuid4().hex[:16]
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO jobs(job_id, project_id, goal, status, created_at, updated_at, max_attempts, human_inputs)
                VALUES (?, ?, ?, 'queued', ?, ?, ?, '[]')
                """,
                (job_id, self.project_id, goal, now, now, MAX_ATTEMPTS),
            )
            self._event_conn(c, job_id, None, "job_submitted", {"goal": goal})
        return self.get_job_snapshot(job_id)

    def _event_conn(self, c: sqlite3.Connection, job_id: str, run_id: str | None, event: str, payload: dict[str, Any] | None = None) -> None:
        c.execute(
            "INSERT INTO events(job_id, run_id, ts, event, payload) VALUES (?, ?, ?, ?, ?)",
            (job_id, run_id, utc_now(), event, json.dumps(payload or {}, ensure_ascii=False)),
        )

    def add_event(self, job_id: str, event: str, run_id: str | None = None, payload: dict[str, Any] | None = None) -> None:
        with self._conn() as c:
            self._event_conn(c, job_id, run_id, event, payload)

    def get_job_row(self, job_id: str) -> sqlite3.Row | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            return row

    def update_job(self, job_id: str, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = utc_now()
        keys = list(fields.keys())
        with self._conn() as c:
            c.execute(
                f"UPDATE jobs SET {', '.join([k+'=?' for k in keys])} WHERE job_id=?",
                tuple(fields[k] for k in keys) + (job_id,),
            )

    def claim_jobs(self, worker_id: str, limit: int = 2, lease_seconds: int = LEASE_SECONDS) -> list[str]:
        claimed: list[str] = []
        now = datetime.now(timezone.utc)
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT job_id FROM jobs
                WHERE status IN ('queued','planning','approved')
                  AND (lease_until IS NULL OR lease_until <= ?)
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (utc_now(), max(1, int(limit))),
            ).fetchall()
            for r in rows:
                jid = str(r["job_id"])
                cur = c.execute(
                    """
                    UPDATE jobs
                    SET worker_id=?, lease_until=?, heartbeat_at=?, updated_at=?
                    WHERE job_id=? AND (lease_until IS NULL OR lease_until <= ?)
                    """,
                    (worker_id, lease_until, utc_now(), utc_now(), jid, utc_now()),
                )
                if cur.rowcount:
                    claimed.append(jid)
                    self._event_conn(c, jid, None, "job_claimed", {"worker_id": worker_id, "lease_until": lease_until})
        return claimed

    def heartbeat(self, job_id: str, worker_id: str, runner_pid: int | None = None, lease_seconds: int = LEASE_SECONDS) -> None:
        lease_until = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
        now = utc_now()
        with self._conn() as c:
            c.execute(
                """
                UPDATE jobs
                SET worker_id=?, runner_pid=?, heartbeat_at=?, lease_until=?, updated_at=?
                WHERE job_id=?
                """,
                (worker_id, runner_pid, now, lease_until, now, job_id),
            )

            # Throttled heartbeat event for observability (every >=30s)
            row = c.execute("SELECT last_heartbeat_log_ts FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            now_ts = int(datetime.now(timezone.utc).timestamp())
            last_ts = int((row["last_heartbeat_log_ts"] if row and row["last_heartbeat_log_ts"] is not None else 0) or 0)
            if (not last_ts) or (now_ts - last_ts >= 30):
                c.execute("UPDATE jobs SET last_heartbeat_log_ts=? WHERE job_id=?", (now_ts, job_id))
                self._event_conn(
                    c,
                    job_id,
                    None,
                    "heartbeat",
                    {"worker_id": worker_id, "runner_pid": runner_pid, "lease_until": lease_until},
                )

    def recover_stale_jobs(self, stale_timeout: int = STALE_TIMEOUT_SECONDS) -> list[str]:
        out: list[str] = []
        now = datetime.now(timezone.utc)
        with self._conn() as c:
            rows = c.execute("SELECT * FROM jobs WHERE status IN ('running','planning')").fetchall()
            for row in rows:
                hb = _parse_utc(row["heartbeat_at"])
                lease = _parse_utc(row["lease_until"])
                stale = False
                if hb is None:
                    stale = True
                elif (now - hb).total_seconds() > stale_timeout:
                    stale = True
                if lease and lease > now and not stale:
                    continue
                if not stale and lease is None:
                    continue
                new_status = "approved" if row["status"] == "running" else "queued"
                c.execute(
                    "UPDATE jobs SET status=?, worker_id=NULL, runner_pid=NULL, lease_until=NULL, updated_at=? WHERE job_id=?",
                    (new_status, utc_now(), row["job_id"]),
                )
                out.append(str(row["job_id"]))
                self._event_conn(
                    c,
                    str(row["job_id"]),
                    str(row["run_id"] or "") or None,
                    "stale_recovered",
                    {"from": row["status"], "to": new_status},
                )
        return out

    def list_events(self, job_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT ts,event,payload,run_id FROM events WHERE job_id=? ORDER BY id DESC LIMIT ?",
                (job_id, max(1, int(limit))),
            ).fetchall()
        out = []
        for r in reversed(rows):
            payload = {}
            try:
                payload = json.loads(r["payload"] or "{}")
            except Exception:
                pass
            out.append({"ts": r["ts"], "event": r["event"], "run_id": r["run_id"], "payload": payload})
        return out

    def _row_to_job(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["audit"] = {
            "decision": d.pop("audit_decision", "pending"),
            "revision": d.pop("audit_revision", ""),
            "run_id": d.get("run_id"),
        }
        for k in ("human_inputs", "last_result"):
            raw = d.get(k)
            if isinstance(raw, str) and raw:
                try:
                    d[k] = json.loads(raw)
                except Exception:
                    d[k] = [] if k == "human_inputs" else {}
            elif raw is None:
                d[k] = [] if k == "human_inputs" else {}
        return d

    def get_job_snapshot(self, job_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return None
        job = self._row_to_job(row)
        job["events"] = self.list_events(job_id, limit=30)
        self.export_snapshot(job)
        return job

    def export_snapshot(self, job: dict[str, Any]) -> None:
        p = snapshot_path(job.get("project_id") or self.project_id, str(job["job_id"]))
        p.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_run(self, run_id: str, job_id: str, status: str, pid: int | None, worker_id: str | None, lease_until: str | None = None, heartbeat_at: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO runs(run_id, job_id, status, pid, worker_id, lease_until, heartbeat_at, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    pid=excluded.pid,
                    worker_id=excluded.worker_id,
                    lease_until=excluded.lease_until,
                    heartbeat_at=excluded.heartbeat_at
                """,
                (run_id, job_id, status, pid, worker_id, lease_until, heartbeat_at, utc_now()),
            )

    def finish_run(self, run_id: str, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE runs SET status=?, finished_at=? WHERE run_id=?", (status, utc_now(), run_id))
