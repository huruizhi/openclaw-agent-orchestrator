import json
import re
from collections.abc import Iterable

TASK_DONE = "TASK_DONE"
TASK_FAILED = "TASK_FAILED"
TASK_WAITING = "TASK_WAITING"


def _extract_payload(raw: str, marker: str):
    # strip only from first marker occurrence
    after = raw[raw.find(f"[{marker}]") + len(f"[{marker}]") :].strip()
    if not after:
        return None, None
    if not after.startswith("{"):
        return after or None, None
    try:
        return json.loads(after), None
    except Exception as e:
        return None, f"malformed payload: {e}"


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


def parse_messages(content):
    """Return parsed terminal directives from assistant text.

    Compatible with legacy behavior and structured JSON payload (post-compat-mode).
    """
    results: list[dict] = []
    for text in _iter_lines(content):
        if not text:
            continue
        for line in str(text).splitlines():
            line = line.strip()
            if not line:
                continue
            if "[TASK_DONE]" not in line and "[TASK_FAILED]" not in line and "[TASK_WAITING]" not in line:
                continue

            if "[TASK_DONE]" in line:
                payload, err = _extract_payload(line, TASK_DONE)
                if err:
                    results.append({"type": "malformed", "marker": "TASK_DONE", "error": err})
                else:
                    if isinstance(payload, str):
                        # Legacy: ignore non-JSON suffix text in tests (empty marker)
                        payload = None if payload == "" else payload
                    if payload is None:
                        results.append({"type": "done"})
                    else:
                        results.append({"type": "done", "payload": payload})
            elif "[TASK_FAILED]" in line:
                payload, err = _extract_payload(line, TASK_FAILED)
                if err:
                    results.append({"type": "malformed", "marker": "TASK_FAILED", "error": err})
                else:
                    if isinstance(payload, str):
                        payload = None if payload == "" else payload
                    if payload is None:
                        results.append({"type": "failed"})
                    else:
                        results.append({"type": "failed", "payload": payload})
            elif "[TASK_WAITING]" in line:
                payload, err = _extract_payload(line, TASK_WAITING)
                if err:
                    results.append({"type": "malformed", "marker": "TASK_WAITING", "error": err})
                else:
                    results.append({"type": "waiting", "question": payload if isinstance(payload, str) else None})

    return results