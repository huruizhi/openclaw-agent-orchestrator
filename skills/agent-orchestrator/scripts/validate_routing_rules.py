#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from m5.assign import _load_agents, _validate_routing_rules


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    rules_path = root / "m5" / "routing_rules.json"

    data = json.loads(rules_path.read_text(encoding="utf-8"))
    agents_data = _load_agents()
    valid_agents = {a["name"] for a in agents_data.get("agents", [])}

    _validate_routing_rules(data, valid_agents)
    print("routing_rules.json valid ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
