"""Fail CI when application code writes directly to stdout.

Command-line tools intentionally print user-facing output, so the policy
scope is the runtime application packages only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PACKAGES = ("api", "core", "db", "modules", "workers")
PRINT_CALL = re.compile(r"\bprint\s*\(")


def find_violations(root: Path = ROOT) -> list[str]:
    violations: list[str] = []
    for package in RUNTIME_PACKAGES:
        package_root = root / package
        for path in sorted(package_root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if PRINT_CALL.search(line):
                    violations.append(f"{path.relative_to(root)}:{line_number}: {line.strip()}")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Direct print() calls are not allowed in runtime application code:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1
    print("logging policy: no runtime print() calls found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
