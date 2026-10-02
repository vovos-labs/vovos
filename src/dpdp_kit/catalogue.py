"""Load and validate control definitions."""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from . import paths
from .models import Control


class CatalogueError(Exception):
    """Raised when controls, profiles or input files are invalid. The message lists every problem found."""


@cache
def _validator(schema_path: Path) -> Draft202012Validator:
    return Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))


def load_yaml(path: Path) -> Any:
    """Parse a YAML file safely. Raises CatalogueError naming the file on read or syntax errors."""
    try:
        with Path(path).open(encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise CatalogueError(f"{path}: invalid YAML: {exc}") from exc
    except OSError as exc:
        raise CatalogueError(f"{path}: cannot read file: {exc.strerror}") from exc


def schema_errors(doc: Any, schema_path: Path, source: Path | str) -> list[str]:
    """Return human-readable schema violations of ``doc``, prefixed with ``source``; empty if valid."""
    errors = sorted(_validator(schema_path).iter_errors(doc), key=lambda e: list(e.absolute_path))
    return [f"{source}: {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]


def _load_control_file(path: Path, schema: Path, known: dict[str, Control]) -> tuple[Control | None, list[str]]:
    doc = load_yaml(path)
    errors = schema_errors(doc, schema, path)
    if errors:
        return None, errors
    if path.stem != doc["id"]:
        errors.append(f"{path}: file name must match control id '{doc['id']}'")
    if doc["id"] in known:
        errors.append(f"{path}: duplicate control id {doc['id']} (also in {known[doc['id']].source})")
        return None, errors
    return Control.from_dict(doc, path), errors


def load_controls(dirs: Iterable[Path]) -> dict[str, Control]:
    """Load every ``*.yaml`` control under ``dirs``. Raises CatalogueError listing all problems at once."""
    controls: dict[str, Control] = {}
    errors: list[str] = []
    schema = paths.catalogue_schema("control.schema.json")
    for raw_dir in dirs:
        directory = Path(raw_dir)
        if not directory.is_dir():
            errors.append(f"{directory}: control directory not found")
            continue
        for path in sorted(directory.rglob("*.yaml")):
            try:
                control, problems = _load_control_file(path, schema, controls)
            except CatalogueError as exc:
                errors.append(str(exc))
                continue
            errors.extend(problems)
            if control is not None:
                controls[control.id] = control
    if errors:
        raise CatalogueError("\n".join(errors))
    return controls


def default_control_dirs() -> list[Path]:
    return [paths.catalogue_dir() / "controls"]


def catalogue_metadata() -> dict[str, Any]:
    """Return catalogue.yaml as a dict. Raises CatalogueError if it is not a mapping."""
    meta = load_yaml(paths.catalogue_dir() / "catalogue.yaml")
    if not isinstance(meta, dict):
        raise CatalogueError("catalogue.yaml must be a mapping")
    return meta
