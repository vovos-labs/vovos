"""Check registry and plugin discovery.

A check is a function ``(ctx, params) -> Result`` registered under a key of the
form ``<plugin>.<check>``. Controls reference checks by that key. Plugins are
found in three places:

1. built-in plugins under ``dpdp_kit.plugins``
2. installed packages exposing the ``dpdp_kit.plugins`` entry-point group
3. ``*.py`` files in directories passed with ``--plugins-dir``

Plugins are trusted code: loading one executes it (see SECURITY.md).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from .models import Result

log = logging.getLogger(__name__)

KINDS = ("automated", "attestation", "ai-assisted")

CheckFunc = Callable[[Any, dict[str, Any]], Result]


@dataclass(frozen=True)
class CheckSpec:
    key: str
    func: CheckFunc
    kind: str
    description: str
    module: str


class Registry:
    def __init__(self) -> None:
        self._checks: dict[str, CheckSpec] = {}

    def check(self, key: str, *, kind: str = "automated", description: str = "") -> Callable[[CheckFunc], CheckFunc]:
        """Decorator registering a check under ``key`` ('plugin.check'). Raises ValueError on bad or duplicate keys."""
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
        plugin, _, name = key.partition(".")
        if not plugin or not name or "." in name:
            raise ValueError(f"check key must look like 'plugin.check', got {key!r}")

        def decorator(func: CheckFunc) -> CheckFunc:
            existing = self._checks.get(key)
            if existing and existing.func is not func:
                raise ValueError(f"check '{key}' is already registered by {existing.module}")
            doc = (func.__doc__ or "").strip().splitlines()
            summary = description or (doc[0] if doc else "")
            self._checks[key] = CheckSpec(key, func, kind, summary, func.__module__)
            return func

        return decorator

    def get(self, key: str) -> CheckSpec | None:
        return self._checks.get(key)

    def all(self) -> list[CheckSpec]:
        return [self._checks[k] for k in sorted(self._checks)]


registry = Registry()
check = registry.check


def _load_file(py: Path) -> None:
    spec = importlib.util.spec_from_file_location(f"dpdp_kit_local_{py.stem}", py)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot create an import spec for {py}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def load_plugins(extra_dirs: Iterable[Path] = ()) -> list[str]:
    """Import every plugin source. Returns human-readable load errors instead of raising.

    Built-in plugins must import; a failure there is a packaging bug and propagates.
    """
    errors: list[str] = []
    importlib.import_module("dpdp_kit.plugins")
    for ep in entry_points(group="dpdp_kit.plugins"):
        try:
            ep.load()
        except Exception as exc:  # a broken third-party plugin must not stop the run
            log.debug("entry point %s failed", ep.name, exc_info=True)
            errors.append(f"plugin entry point '{ep.name}' failed to load: {exc}")
    for raw_dir in extra_dirs:
        directory = Path(raw_dir)
        if not directory.is_dir():
            errors.append(f"plugins directory {directory} not found")
            continue
        for py in sorted(directory.glob("*.py")):
            try:
                _load_file(py)
            except Exception as exc:
                log.debug("local plugin %s failed", py, exc_info=True)
                errors.append(f"local plugin {py} failed to load: {exc}")
    return errors
