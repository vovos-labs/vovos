"""Locate the control catalogue, profiles and schemas, whether installed or run from a checkout."""

from __future__ import annotations

from pathlib import Path

_PKG = Path(__file__).resolve().parent


def data_root() -> Path:
    bundled = _PKG / "_data"
    if (bundled / "catalogue").is_dir():
        return bundled
    repo = _PKG.parents[1]
    if (repo / "catalogue").is_dir():
        return repo
    raise FileNotFoundError("Could not locate the control catalogue; pass --catalogue explicitly.")


def catalogue_dir() -> Path:
    return data_root() / "catalogue"


def profiles_dir() -> Path:
    return data_root() / "profiles"


def catalogue_schema(name: str) -> Path:
    return catalogue_dir() / "schema" / name


def package_schema(name: str) -> Path:
    return _PKG / "schemas" / name


def templates_dir() -> Path:
    return _PKG / "templates"
