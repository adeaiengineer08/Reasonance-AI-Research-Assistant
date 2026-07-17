#!/usr/bin/env python3
"""Fix macOS-specific venv shebangs in AgentCore dependencies.zip before cloud deploy."""
from __future__ import annotations

import pathlib
import re
import sys
import tempfile
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
ZIP_PATH = REPO / ".bedrock_agentcore" / "monk_ticket_triage" / "dependencies.zip"
EXEC_RE = re.compile(r"^'''exec' '[^']*' \"\$0\" \"\$@\"$")


def fix_script(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if len(lines) < 2 or not lines[0].startswith("#!/bin/sh"):
        return text
    if not EXEC_RE.match(lines[1].rstrip("\n")):
        return text
    lines[1] = "'''exec' python3 \"$0\" \"$@\"\n"
    return "".join(lines)


def main() -> int:
    if not ZIP_PATH.exists():
        print(f"no dependencies zip at {ZIP_PATH}", file=sys.stderr)
        return 1

    changed = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        with zipfile.ZipFile(ZIP_PATH) as zf:
            zf.extractall(tmp)

        for path in (tmp / "bin").glob("*"):
            if not path.is_file():
                continue
            original = path.read_text(encoding="utf-8", errors="replace")
            fixed = fix_script(original)
            if fixed != original:
                path.write_text(fixed, encoding="utf-8")
                changed += 1

        if changed == 0:
            print("no shebang fixes needed")
            return 0

        backup = ZIP_PATH.with_suffix(".zip.bak")
        ZIP_PATH.replace(backup)
        with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file in tmp.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(tmp))
        backup.unlink(missing_ok=True)
        print(f"fixed {changed} bin script(s) in {ZIP_PATH}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
