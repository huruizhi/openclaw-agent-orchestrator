# Quick Start

## 1) Install + Configure

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set at least:
- `OPENCLAW_API_BASE_URL`
- `LLM_URL`
- `LLM_API_KEY`

See `INSTALL.md` and `CONFIG.md` for details.

## 2) Preflight

```bash
bash scripts/run_preflight.sh
```

## 3) Queue Workflow (Recommended)

```bash
# submit
python3 scripts/submit.py "<goal>"

# plan
python3 scripts/worker.py --once

# inspect
python3 scripts/status.py <job_id>

# approve (or revise)
python3 scripts/control.py approve <job_id>

# execute
python3 scripts/worker.py --once

# final status
python3 scripts/status.py <job_id>
```

If paused for input:

```bash
python3 scripts/control.py resume <job_id> "<answer>"
python3 scripts/worker.py --once
```

## 4) Direct Runner (Optional)

```bash
python3 scripts/runner.py run "<goal>"
python3 scripts/runner.py status <run_id>
```

## 5) If Something Looks Stuck

- Check `python3 scripts/status.py <job_id>`
- Check `BASE_PATH/_orchestrator_queue/jobs/<job_id>.events.jsonl`
- Read `OPERATIONS.md` for recovery rules
