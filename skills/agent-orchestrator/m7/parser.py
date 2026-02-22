import json
from collections.abc import Iterable

TASK_DONE = "TASK_DONE"
TASK_FAILED = "TASK_FAILED"
TASK_WAITING = "TASK_WAITING"


def _iter_lines(content) -> Iterable[str]:
    if isinstance(content, list):
        for m in content:
            if isinstance(m, dict):
                if m.get("role") and m.get("role") != "assistant":
                    continue
                txt = m.get("content", "")
            else:
                txt = str(m)
            yield str(txt)
    else:
        yield str(content)


def _parse_line(line: str) -> dict | None:
    s = line.strip()
    if not s.startswith("["):
        return None

    for marker, etype in ((TASK_DONE, "done"), (TASK_FAILED, "failed"), (TASK_WAITING, "waiting")):
        prefix = f"[{marker}]"
        if not s.startswith(prefix):
            continue

        rest = s[len(prefix) :].strip()
        if not rest:
            return {"type": etype} if etype != "waiting" else {"type": "waiting", "question": ""}

        if not rest.startswith("{"):
            return {"type": "malformed", "marker": marker, "error": "non-json payload"}

        try:
            payload = json.loads(rest)
        except Exception as e:
            return {"type": "malformed", "marker": marker, "error": f"malformed payload: {e}"}

        if etype == "waiting":
            if not isinstance(payload, dict) or not isinstance(payload.get("question"), str):
                return {"type": "malformed", "marker": marker, "error": "waiting payload must be object with question:string"}
            return {"type": "waiting", "question": payload.get("question", "")}

        if not isinstance(payload, dict):
            return {"type": "malformed", "marker": marker, "error": "payload must be JSON object"}
        return {"type": etype, "payload": payload}

    return None


def parse_messages(content):
    results: list[dict] = []
    for text in _iter_lines(content):
        if not text:
            continue
        for line in str(text).splitlines():
            parsed = _parse_line(line)
            if parsed:
                results.append(parsed)
    return results
