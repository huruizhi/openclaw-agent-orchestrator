# ADR: State Source of Truth (P1)

## Decision
For job/run/task status reading, source precedence is fixed:
1. temporal runtime state
2. last_result snapshot (same run_id only)
3. job row fallback

This precedence is surfaced in `scripts/status.py` as `run_status_source_precedence`.

## Why
Avoid status split/flip caused by stale snapshots or delayed persistence.

## Operational Rule
When divergence exists, trust temporal and reconcile stale snapshots via events/audit timeline.
