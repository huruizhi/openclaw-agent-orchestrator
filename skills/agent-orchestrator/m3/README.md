# M3: Execution Graph Builder

## Purpose

Builds a valid execution graph from tasks, ensuring:
- All dependencies are valid (refer to existing tasks)
- No circular dependencies exist
- Initial ready set is computed (tasks that can execute immediately)

## API

```python
from m3 import build_execution_graph

# Input: Output from M2
tasks_dict = {
    "tasks": [
        {
            "id": "tsk_...",
            "title": "Task name",
            "status": "pending",
            "deps": ["tsk_parent..."],
            "inputs": [],
            "outputs": [],
            "done_when": ["done"],
            "assigned_to": None
        }
    ]
}

# Output: Execution graph
result = build_execution_graph(tasks_dict)

# Returns:
{
    "graph": {
        "task_id": ["dependent_task_1", "dependent_task_2", ...]
        # Edges: parent -> children (reverse of deps)
    },
    "in_degree": {
        "task_id": number_of_unmet_dependencies
    },
    "ready": ["task_id_1", "task_id_2", ...]
    # Tasks with in_degree == 0
}
```

## Algorithm

### 1. Build Graph (Reverse Edges)

For `B depends on A`, we create edge `A -> B`:
- When A completes, it "unlocks" B
- Scheduler can efficiently find what to update

### 2. Detect Unknown Dependencies

Check all `deps` references exist in task IDs.

### 3. Detect Circular Dependencies (Kahn's Algorithm)

```
queue = all nodes with in_degree == 0
visited = 0

while queue:
    node = queue.pop()
    visited++

    for child in graph[node]:
        in_degree[child]--
        if in_degree[child] == 0:
            queue.append(child)

if visited != total_nodes:
    raise CircularDependencyError
```

### 4. Compute Ready Set

`ready = [task_id for task_id, deg in in_degree.items() if deg == 0]`

## Example

```python
# Input tasks
tasks = {
    "tasks": [
        {"id": "A", "deps": [], ...},
        {"id": "B", "deps": ["A"], ...},
        {"id": "C", "deps": ["A"], ...},
        {"id": "D", "deps": ["B", "C"], ...}
    ]
}

# Output graph
{
    "graph": {
        "A": ["B", "C"],    # A unlocks B and C
        "B": ["D"],         # B unlocks D
        "C": ["D"],         # C unlocks D
        "D": []             # D is terminal
    },
    "in_degree": {
        "A": 0,             # Ready to execute
        "B": 1,             # Waiting for A
        "C": 1,             # Waiting for A
        "D": 2              # Waiting for B and C
    },
    "ready": ["A"]          # Can start immediately
}
```

## Execution Flow

```
Initial State:
  ready = [A]
  Execute A

After A completes:
  ready = [B, C]
  Execute B

After B completes:
  ready = [C]
  Execute C

After C completes:
  ready = [D]
  Execute D

All tasks complete ✓
```

## Error Handling

### Unknown Dependency
```python
ValueError: Task 'B' depends on unknown task 'UNKNOWN'
```

### Circular Dependency
```python
ValueError: Circular dependency detected
```

## Testing

```bash
# Unit tests
python3 m3/test_graph.py

# Integration tests (M2 + M3)
python3 m3/test_integration.py
```

## Complexity

- **Time:** O(V + E) where V = tasks, E = dependencies
- **Space:** O(V + E)

## Notes

- Graph uses **reverse edges** (parent -> children)
- This is optimal for scheduler: "When task A completes, update these children"
- No optimization, no concurrency, no weights (that's M6's job)
