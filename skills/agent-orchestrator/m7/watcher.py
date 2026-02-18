class SessionWatcher:
    def __init__(self, adapter):
        self.adapter = adapter
        self._sessions: set[str] = set()

    def watch(self, session_id: str) -> None:
        self._sessions.add(session_id)

    def unwatch(self, session_id: str) -> None:
        self._sessions.discard(session_id)

    def poll_events(self) -> list[dict]:
        events: list[dict] = []
        for session_id in sorted(self._sessions):
            messages = self.adapter.poll_messages(session_id)
            if messages:
                events.append(
                    {
                        "session_id": session_id,
                        "messages": messages,
                    }
                )
        return events
