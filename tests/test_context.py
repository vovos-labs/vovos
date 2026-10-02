from __future__ import annotations

from pathlib import Path

import pytest

from dpdp_kit.context import Context, PrerequisiteMissing


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("shot.png", "shot.png"),
        ("../../escape.txt", "escape.txt"),
        ("/etc/passwd", "passwd"),
        ("a b/c?d.json", "c_d.json"),
        ("..", "evidence"),
        (".hidden", "hidden"),
    ],
)
def test_evidence_names_cannot_escape_the_evidence_folder(tmp_path: Path, name: str, expected: str) -> None:
    path = Context(out_dir=tmp_path).write_evidence(name, "x")
    assert path.parent == tmp_path / "evidence"
    assert path.name == expected


def test_windows_style_traversal_stays_inside_on_every_os(tmp_path: Path) -> None:
    path = Context(out_dir=tmp_path).write_evidence("..\\..\\escape.txt", "x")
    assert path.parent == tmp_path / "evidence"
    assert "\\" not in path.name
    assert not path.name.startswith(".")


def test_write_evidence_handles_text_and_bytes(tmp_path: Path) -> None:
    ctx = Context(out_dir=tmp_path)
    assert ctx.write_evidence("t.txt", "हिंदी").read_text(encoding="utf-8") == "हिंदी"
    assert ctx.write_evidence("b.bin", b"\x00\x01").read_bytes() == b"\x00\x01"


def test_resource_is_computed_once(tmp_path: Path) -> None:
    calls: list[int] = []
    ctx = Context(out_dir=tmp_path)

    def factory(_: Context) -> str:
        calls.append(1)
        return "value"

    assert [ctx.resource("k", factory) for _ in range(3)] == ["value"] * 3
    assert len(calls) == 1


def test_resource_failure_is_cached_and_reraised(tmp_path: Path) -> None:
    calls: list[int] = []
    ctx = Context(out_dir=tmp_path)

    def factory(_: Context) -> str:
        calls.append(1)
        raise PrerequisiteMissing("nope")

    for _ in range(3):
        with pytest.raises(PrerequisiteMissing):
            ctx.resource("k", factory)
    assert len(calls) == 1


@pytest.mark.parametrize("value", [None, ""])
def test_require_names_the_flag(tmp_path: Path, value: str | None) -> None:
    with pytest.raises(PrerequisiteMissing, match="--url"):
        Context(out_dir=tmp_path, target={"url": value}).require("url")


def test_inputs_are_copied_not_aliased(tmp_path: Path) -> None:
    target = {"url": "https://x.example"}
    ctx = Context(out_dir=tmp_path, target=target)
    target["url"] = "changed"
    assert ctx.require("url") == "https://x.example"
