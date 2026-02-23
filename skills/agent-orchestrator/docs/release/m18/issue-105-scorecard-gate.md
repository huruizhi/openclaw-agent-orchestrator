# Issue #105 — M1 Scorecard Gate (>= 8.0)

## Weighted Rubric

- Functionality correctness: **35%**
- Reliability evidence (restart/no-terminal/temporal contracts): **30%**
- Regression coverage quality: **25%**
- Operability & runbook clarity: **10%**

Target score: **>= 8.0 / 10.0**.

## Mandatory Closure Checklist

Milestone cannot be closed until all are true:

- [ ] All P0 issues for milestone are closed.
- [ ] Gate score >= 8.0 with linked evidence.
- [ ] Regression artifacts are attached (`regression_report`, `gate_report`, issue checks).
- [ ] Release notes include issue->evidence mapping.

## Gate Evaluator

Use `scripts/scorecard_gate.py` with a scorecard JSON to evaluate pass/fail.

Example:

```bash
python3 scripts/scorecard_gate.py path/to/m1_scorecard.json --threshold 8.0
```
