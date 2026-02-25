#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

CODE_HINT_DIRS = ("m2/", "m3/", "m4/", "m5/", "m6/", "m7/", "scripts/", "workflow/", "utils/")
DOC_ONLY_PREFIXES = ("docs/",)
DOC_ONLY_SUFFIXES = (".md",)


def run_json(cmd: list[str]):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    return json.loads(p.stdout)


def is_code_file(path: str) -> bool:
    p = path.strip()
    parts = Path(p).parts

    if p.startswith(DOC_ONLY_PREFIXES) or p.endswith(DOC_ONLY_SUFFIXES):
        return False

    code_dirs = {d.rstrip("/") for d in CODE_HINT_DIRS}
    in_code_dir = any(seg in code_dirs for seg in parts)
    if not in_code_dir:
        return False

    # Prefer source-like files; markdown/docs are already filtered above.
    return p.endswith((".py", ".ts", ".js", ".go", ".rs", ".java", ".kt", ".yaml", ".yml", ".json", ".sh")) or in_code_dir


def main() -> int:
    ap = argparse.ArgumentParser(description="PR merge gate: block docs-only merges")
    ap.add_argument("--repo", required=True, help="owner/repo")
    ap.add_argument("--pr", required=True, type=int, help="PR number")
    args = ap.parse_args()

    data = run_json([
        "gh", "pr", "view", str(args.pr), "--repo", args.repo,
        "--json", "number,title,files,additions,deletions,url"
    ])

    files = [f.get("path", "") for f in data.get("files", [])]
    code_files = [f for f in files if is_code_file(f)]

    result = {
        "pr": data.get("number"),
        "url": data.get("url"),
        "title": data.get("title"),
        "files": files,
        "code_files": code_files,
        "additions": data.get("additions", 0),
        "deletions": data.get("deletions", 0),
        "pass": bool(code_files),
        "reason": "OK" if code_files else "BLOCK: docs-only or no effective code changes",
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
