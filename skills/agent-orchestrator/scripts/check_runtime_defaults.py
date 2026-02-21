#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

from runtime_defaults import runtime_default_matrix

ROOT = Path(__file__).resolve().parent.parent
CONFIG_MD = ROOT / "CONFIG.md"
RELEASE_NOTES = ROOT / "docs" / "releases" / "v1.1.1.md"


def _parse_config_table(content: str) -> dict[str, str]:
    out: dict[str, str] = {}
    pattern = re.compile(r"^\|\s*`(?P<key>[^`]+)`\s*\|\s*`(?P<val>[^`]+)`\s*\|")
    for line in content.splitlines():
        m = pattern.match(line.strip())
        if not m:
            continue
        out[m.group("key")] = m.group("val")
    return out


def main() -> int:
    if not CONFIG_MD.exists():
        print(f"[FAIL] missing {CONFIG_MD}")
        return 1

    table = _parse_config_table(CONFIG_MD.read_text(encoding="utf-8"))
    expected = runtime_default_matrix()

    errors: list[str] = []
    for key, val in expected.items():
        got = table.get(key)
        if got is None:
            errors.append(f"missing CONFIG.md row for {key}")
            continue
        if str(got).strip() != str(val):
            errors.append(f"CONFIG.md mismatch for {key}: doc={got}, runtime={val}")

    if not RELEASE_NOTES.exists():
        errors.append(f"missing release default matrix file: {RELEASE_NOTES}")

    if errors:
        print("[FAIL] runtime-doc default drift detected:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("[OK] runtime defaults match CONFIG.md and release matrix exists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
