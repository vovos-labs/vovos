"""Run every quality gate in CI order. Usage: python scripts/check.py [--fast]

--fast skips browser tests and the dependency audit (for quick local loops).
Exits non-zero on the first failing gate.
"""

from __future__ import annotations

import subprocess
import sys
import time

FAST = "--fast" in sys.argv[1:]
PY = sys.executable

GATES: list[tuple[str, list[str]]] = [
    ("format", [PY, "-m", "ruff", "format", "--check", "."]),
    ("lint", [PY, "-m", "ruff", "check", "."]),
    ("types", [PY, "-m", "mypy"]),
    ("catalogue", [PY, "-m", "dpdp_kit", "validate"]),
    (
        "tests",
        [PY, "-m", "pytest", "-q", "--cov", *(["-m", "not browser", "--cov-fail-under=0"] if FAST else [])],
    ),
]
if not FAST:
    GATES.append(("dependencies", [PY, "-m", "pip_audit", "."]))


def main() -> int:
    for name, command in GATES:
        print(f"==> {name}: {' '.join(command[1:])}", flush=True)
        started = time.monotonic()
        code = subprocess.call(command)  # noqa: S603 - fixed, trusted argument lists
        print(f"    {name} {'passed' if code == 0 else 'FAILED'} in {time.monotonic() - started:.1f}s", flush=True)
        if code != 0:
            return code
    print("All gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
