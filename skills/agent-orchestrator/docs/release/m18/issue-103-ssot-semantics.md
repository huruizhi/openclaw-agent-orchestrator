# Issue #103 — SSOT Status Semantics

## Source Precedence (deterministic)

Status consumers must resolve run status using this strict order:

1. `temporal`
2. `last_result`
3. `job`

`status.py` now exposes `run_status_source_precedence` explicitly and sets `run_status_source` to the selected source.

## Divergence Severity

When temporal and last_result disagree, `status_divergence` includes:

- `severity`:
  - `high`: both sides terminal but conflicting
  - `medium`: one terminal, one non-terminal
  - `low`: both non-terminal
- `action_hint`: operator guidance for next action
- `source_precedence`: precedence list used for arbitration

## Compatibility

Legacy summary fields remain stable for existing dashboards; this enhancement only adds explicit observability metadata for migration operations.
