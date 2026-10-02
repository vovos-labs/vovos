from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dpdp_kit import registry as registry_module
from dpdp_kit.models import Result, Status
from dpdp_kit.registry import Registry, load_plugins


def _noop(ctx: Any, params: dict[str, Any]) -> Result:
    """First docstring line becomes the description."""
    return Result(Status.PASS)


@pytest.mark.parametrize("key", ["nodot", ".check", "plugin.", "a.b.c", ""])
def test_rejects_malformed_keys(key: str) -> None:
    with pytest.raises(ValueError, match=r"plugin.check"):
        Registry().check(key)


def test_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="kind"):
        Registry().check("a.b", kind="magic")


def test_duplicate_key_from_different_function_rejected() -> None:
    reg = Registry()
    reg.check("a.b")(_noop)
    reg.check("a.b")(_noop)  # re-registering the same function (re-import) is harmless
    with pytest.raises(ValueError, match="already registered"):
        reg.check("a.b")(lambda c, p: Result(Status.PASS))


def test_description_defaults_to_docstring_and_all_is_sorted() -> None:
    reg = Registry()
    reg.check("z.last")(_noop)
    reg.check("a.first", description="explicit")(_noop)
    assert [s.key for s in reg.all()] == ["a.first", "z.last"]
    assert reg.get("z.last").description == "First docstring line becomes the description."  # type: ignore[union-attr]
    assert reg.get("a.first").description == "explicit"  # type: ignore[union-attr]
    assert reg.get("missing.key") is None


def test_broken_local_plugins_are_reported_not_raised(tmp_path: Path) -> None:
    (tmp_path / "syntax_error.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "raises.py").write_text("raise RuntimeError('plugin exploded')\n", encoding="utf-8")
    errors = load_plugins([tmp_path, tmp_path / "does-not-exist"])
    assert any("syntax_error.py" in e for e in errors)
    assert any("plugin exploded" in e for e in errors)
    assert any("does-not-exist" in e and "not found" in e for e in errors)


def test_local_plugin_registers_its_checks(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text(
        "from dpdp_kit.registry import check\n"
        "from dpdp_kit.models import Result, Status\n"
        "@check('localtest.ok')\n"
        "def ok(ctx, params):\n"
        "    return Result(Status.PASS)\n",
        encoding="utf-8",
    )
    assert load_plugins([tmp_path]) == []
    assert registry_module.registry.get("localtest.ok") is not None


class _FakeEntryPoint:
    name = "broken-ep"

    def load(self) -> None:
        raise ImportError("missing dependency")


def test_broken_entry_point_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry_module, "entry_points", lambda group: [_FakeEntryPoint()])
    assert load_plugins() == ["plugin entry point 'broken-ep' failed to load: missing dependency"]
