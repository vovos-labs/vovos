"""Resolve profiles (with inheritance) and organisation overlays, then select controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from . import paths
from .catalogue import CatalogueError, load_yaml, schema_errors
from .models import Control


@dataclass
class ResolvedProfile:
    id: str
    title: str
    chain: list[str] = field(default_factory=list)
    include_tags: set[str] = field(default_factory=set)
    include_ids: set[str] = field(default_factory=set)
    exclude: dict[str, str] = field(default_factory=dict)  # control id -> reason
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    extra_control_dirs: list[Path] = field(default_factory=list)
    overlay: Path | None = None


@dataclass
class Selection:
    selected: list[Control]
    excluded: list[tuple[Control, str]]
    warnings: list[str]


def _locate(name: str) -> Path:
    candidate = Path(name)
    if candidate.suffix in (".yaml", ".yml") and candidate.is_file():
        return candidate
    path = paths.profiles_dir() / f"{name}.yaml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in paths.profiles_dir().glob("*.yaml")))
        raise CatalogueError(f"Unknown profile '{name}'. Available: {available}")
    return path


def _load(path: Path, *, overlay: bool) -> dict[str, Any]:
    doc = load_yaml(path) or {}
    errs = schema_errors(doc, paths.catalogue_schema("profile.schema.json"), path)
    if not overlay and "id" not in doc:
        errs.append(f"{path}: profiles must declare an 'id'")
    if overlay and doc.get("extends"):
        errs.append(f"{path}: overlays are applied on top of --profile and cannot use 'extends'")
    if errs:
        raise CatalogueError("\n".join(errs))
    return doc


def _merge(target: ResolvedProfile, doc: dict[str, Any], base_dir: Path) -> None:
    include = doc.get("include") or {}
    target.include_tags.update(include.get("tags") or [])
    target.include_ids.update(include.get("ids") or [])
    target.exclude.update(doc.get("exclude") or {})
    for cid, override in (doc.get("overrides") or {}).items():
        merged = target.overrides.setdefault(cid, {"params": {}})
        for key, value in override.items():
            if key == "params":
                for method, params in value.items():
                    merged["params"].setdefault(method, {}).update(params)
            else:
                merged[key] = value
    target.extra_control_dirs.extend((base_dir / d).resolve() for d in doc.get("extra_controls") or [])


def _apply(name: str, target: ResolvedProfile, stack: list[str]) -> None:
    path = _locate(name)
    doc = _load(path, overlay=False)
    if doc["id"] in stack:
        raise CatalogueError(f"Profile inheritance cycle: {' -> '.join([*stack, doc['id']])}")
    for parent in doc.get("extends") or []:
        _apply(parent, target, [*stack, doc["id"]])
    _merge(target, doc, path.parent)
    target.chain.append(doc["id"])


def resolve(name: str, overlay: Path | None = None) -> ResolvedProfile:
    path = _locate(name)
    head = _load(path, overlay=False)
    profile = ResolvedProfile(id=head["id"], title=head.get("title", head["id"]))
    _apply(name, profile, [])
    if overlay is not None:
        overlay = Path(overlay).resolve()
        _merge(profile, _load(overlay, overlay=True), overlay.parent)
        profile.overlay = overlay
    return profile


def select(controls: dict[str, Control], profile: ResolvedProfile) -> Selection:
    selected: list[Control] = []
    excluded: list[tuple[Control, str]] = []
    for control in sorted(controls.values(), key=lambda c: c.id):
        in_scope = bool(profile.include_tags.intersection(control.tags)) or any(
            fnmatchcase(control.id, pattern) for pattern in profile.include_ids
        )
        if not in_scope:
            continue
        if control.id in profile.exclude:
            excluded.append((control, profile.exclude[control.id]))
        else:
            selected.append(control)

    warnings = [
        f"Profile references unknown control '{cid}' (in {kind})"
        for kind, ids in (("exclude", profile.exclude), ("overrides", profile.overrides))
        for cid in ids
        if cid not in controls
    ]
    return Selection(selected, excluded, warnings)
