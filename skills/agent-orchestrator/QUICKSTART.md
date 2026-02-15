# Quick Start

## 1. Install Dependencies

```bash
pip3 install --user -r requirements.txt
```

## 2. Configure LLM

```bash
cp .env.example .env
# Edit .env and add your API key
```

## 3. Test Installation

```bash
python3 test_imports.py
```

## 4. Run Example

```bash
python3 -c "
from m2 import decompose
import json

result = decompose('获取Hacker News最热帖子 分析内容 写成博客 发送邮箱')
print(json.dumps(result, indent=2, ensure_ascii=False))
"
```

## 5. Run Tests

```bash
# Unit tests
python3 m2/test_decompose.py

# Repair loop tests
python3 m2/test_repair.py
```

## API Usage

```python
from m2 import decompose

# Decompose a goal into tasks
result = decompose("Build a REST API")

# Access tasks
for task in result["tasks"]:
    print(f"{task['title']} - {task['status']}")
```

## Expected Output

```json
{
  "tasks": [
    {
      "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT",
      "title": "Define API requirements",
      "status": "pending",
      "deps": [],
      "inputs": ["user_requirements"],
      "outputs": ["api_spec.json"],
      "done_when": ["Specification documented"],
      "assigned_to": null
    }
  ]
}
```

## Troubleshooting

**Missing API Key:**
```
RuntimeError: LLM_API_KEY not set
```
→ Edit `.env` and add your API key

**Import Error:**
```
ModuleNotFoundError: No module named 'jsonschema'
```
→ Run `pip3 install --user -r requirements.txt`

**Validation Failed:**
```
ValidationError: Task[0] invalid
```
→ Check LLM output format, model may need different prompt
