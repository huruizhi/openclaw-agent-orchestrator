def parse_messages(messages: list[dict]) -> list[dict]:
    results: list[dict] = []

    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") != "assistant":
            continue

        content = message.get("content", "")
        if not isinstance(content, str):
            continue

        if "[TASK_DONE]" in content:
            results.append({"type": "done"})

        if "[TASK_FAILED]" in content:
            results.append({"type": "failed"})

        marker = "[TASK_WAITING]"
        idx = content.find(marker)
        if idx != -1:
            question = content[idx + len(marker):].strip()
            results.append({"type": "waiting", "question": question})

    return results
