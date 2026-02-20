# Risk & Rollback Plan (v1.0)

## Key Risks
1. Status divergence between job view and run view.
2. Non-deterministic task-agent routing for file-path-critical outputs.
3. False completion signal when run has failed tasks.

## Mitigations
- Treat run summary (`done/failed`) as source of truth.
- For file-path-critical tasks, enforce main/code execution and path-based verification.
- Require explicit artifact existence checks before acceptance.

## Rollback Plan
1. Revert problematic commits with `git revert <commit>`.
2. Restore previous known-good behavior for status display and routing.
3. Re-run minimal regression:
   - submit -> awaiting_audit -> approve -> running -> completed
   - waiting_human -> resume_from_chat

## Verification Gate
- Required files exist in repo path.
- Commit hash recorded.
- Acceptance summary explicitly marks completed/failed/risk.
