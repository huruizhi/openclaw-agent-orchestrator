# ADR: Temporal Migration (M3)

## Status
Accepted (v1.3.1 / milestone #17)

## Context
We migrated control-plane and run-level state to temporal-like runtime semantics, but validation and legacy operator commands still had mixed paths.

## Decision
1. Keep Temporal-oriented runtime as source of truth for run/task convergence.
2. Keep legacy CLI entrypoints as **compatibility proxy** only (no direct state bypass in default mode).
3. Move validation behavior into isolated activity modules (`workflow/validation_activities.py`) consumed by executor.
4. Add tracing hooks for runner/worker signal handling to accelerate troubleshooting.

## Consequences
- Operators can continue using existing commands.
- State mutation path is more auditable (signal enqueue -> worker apply -> events).
- Validation is testable in isolation.

## Rollback
- Set `ORCH_RUN_BACKEND=legacy` to revert runtime backend behavior.
- Set `ORCH_LEGACY_QUEUE_COMPAT=1` to temporarily route submit via legacy queue JSON.
- If rollback is used, keep compatibility window short and log explicit rollback events.
