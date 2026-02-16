# Path Management

## Configuration

Base path and project ID are configured in `.env`:

```env
BASE_PATH=./workspace
PROJECT_ID=default_project
```

## Directory Structure

```
BASE_PATH/
└── PROJECT_ID/              # Project-specific directory
    ├── .orchestrator/       # Metadata (managed by system)
    │   ├── tasks/           # Task metadata JSON files
    │   │   └── {task_id}.json
    │   ├── state/           # Run state files
    │   │   └── run_{run_id}.json
    │   ├── logs/            # Execution logs
    │   │   ├── {run_id}.log
    │   │   └── {run_id}_{task_id}.log
    │   └── runs/            # Run history
    ├── tasks/               # Task-specific directories
    │   └── {task_id}/       # Each task has its own dir
    │       ├── input/
    │       └── output/
    └── {artifacts}          # Output files (e.g., hn_posts.json)
```

## Key Principles

1. **Project Isolation**
   - Each `PROJECT_ID` has its own directory
   - Different projects don't interfere with each other

2. **Metadata vs Artifacts**
   - Metadata → `.orchestrator/` (system managed)
   - Artifacts → `PROJECT_DIR/` (user accessible)

3. **File Locations**

   | Type | Location | Example |
   |------|----------|---------|
   | Task metadata | `.orchestrator/tasks/` | `tsk_...json` |
   | Run state | `.orchestrator/state/` | `run_20250216.json` |
   | Logs | `.orchestrator/logs/` | `20250216.log` |
   | Artifacts | `PROJECT_DIR/` | `hn_posts.json` |
   | Task files | `PROJECT_DIR/tasks/{id}/` | `tasks/tsk_.../` |

## API Usage

```python
from utils import paths

# Initialize workspace
paths.init_workspace()

# Get paths
task_meta = paths.get_task_metadata_path("tsk_...")
# → BASE_PATH/PROJECT_ID/.orchestrator/tasks/tsk_....json

run_state = paths.get_run_state_path("20250216_120000")
# → BASE_PATH/PROJECT_ID/.orchestrator/state/run_20250216_120000.json

artifact = paths.get_artifact_path("hn_posts.json")
# → BASE_PATH/PROJECT_ID/hn_posts.json

task_dir = paths.get_task_dir("tsk_...")
# → BASE_PATH/PROJECT_ID/tasks/tsk_.../

# Workspace info
info = paths.get_workspace_info()
# → {
#     "base_path": "...",
#     "project_id": "hn_blog_project",
#     "project_dir": "...",
#     "orchestrator_dir": "...",
#     ...
# }

# Cleanup old runs
paths.cleanup_old_runs(keep_last_n=10)
```

## Examples

### Saving Task Metadata

```python
from utils import paths
import json

task_id = "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT"
metadata = {
    "id": task_id,
    "title": "Fetch HN posts",
    "status": "running",
    "started_at": "2025-02-16T12:00:00Z"
}

meta_path = paths.get_task_metadata_path(task_id)
with open(meta_path, 'w') as f:
    json.dump(metadata, f, indent=2)
```

### Saving Artifact

```python
from utils import paths
import json

posts = {"title": "Example", ...}
artifact_path = paths.get_artifact_path("hn_posts.json")

with open(artifact_path, 'w') as f:
    json.dump(posts, f, indent=2)
```

### Task-Specific Directory

```python
from utils import paths

task_dir = paths.get_task_dir("tsk_...")
input_file = task_dir / "input.json"
output_file = task_dir / "output.json"
```

## Environment Variables

Override defaults with environment variables:

```bash
export BASE_PATH=/tmp/openclaw
export PROJECT_ID=blog_project
```

Or in `.env`:

```env
BASE_PATH=/tmp/openclaw
PROJECT_ID=blog_project
```

## Project Examples

### Different projects, different directories

```bash
# HN Blog Project
BASE_PATH=./workspace
PROJECT_ID=hn_blog
# → ./workspace/hn_blog/.orchestrator/

# API Development Project
BASE_PATH=./workspace
PROJECT_ID=api_dev
# → ./workspace/api_dev/.orchestrator/

# Data Analysis Project
BASE_PATH=./workspace
PROJECT_ID=data_analysis
# → ./workspace/data_analysis/.orchestrator/
```
