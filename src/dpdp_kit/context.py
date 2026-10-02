"""Runtime context handed to every check."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class PrerequisiteMissing(Exception):
    """Raised by a check that cannot run, e.g. no URL supplied. The method is reported as NOT_TESTED."""


class Context:
    """What a check can see: the target, questionnaire answers, run options and an evidence folder.

    Expensive work shared by several checks (such as loading a web page once)
    goes through :meth:`resource`, which caches the result, or the error, per run.
    """

    def __init__(
        self,
        *,
        out_dir: Path,
        target: dict[str, Any] | None = None,
        answers: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.target = dict(target or {})
        self.answers = dict(answers or {})
        self.options = dict(options or {})
        self._cache: dict[str, tuple[bool, Any]] = {}

    def require(self, key: str) -> Any:
        """Return ``target[key]``, or raise PrerequisiteMissing telling the user which flag to pass."""
        value = self.target.get(key)
        if not value:
            raise PrerequisiteMissing(f"no '{key}' supplied for this assessment (pass --{key})")
        return value

    def resource(self, key: str, factory: Callable[[Context], Any]) -> Any:
        """Compute ``factory(self)`` once per run. A failure is cached and re-raised for later callers."""
        if key not in self._cache:
            try:
                self._cache[key] = (True, factory(self))
            except Exception as exc:  # cached so N checks don't retry an expensive failure N times
                self._cache[key] = (False, exc)
        ok, value = self._cache[key]
        if not ok:
            raise value
        return value

    @property
    def evidence_dir(self) -> Path:
        path = self.out_dir / "evidence"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_evidence(self, name: str, data: bytes | str) -> Path:
        """Write an evidence file under ``evidence/``. The name is sanitised so it cannot escape that folder."""
        safe = _UNSAFE_NAME.sub("_", Path(name).name).lstrip(".") or "evidence"
        path = self.evidence_dir / safe
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        else:
            path.write_bytes(data)
        return path
