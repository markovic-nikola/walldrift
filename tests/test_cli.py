"""The JSON protocol the applet relies on, end to end through main()."""

import io
import json
from pathlib import Path
from typing import Any

import pytest

from walldrift import cli, protocol, setter, sources

from .conftest import FakeHttp, FakeSource, candidate


@pytest.fixture
def backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """A backend with temporary XDG dirs, a fake source and a recorded wallpaper setter."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(protocol, "_sent", False)
    monkeypatch.setattr(
        setter, "conflicts", lambda: [setter.Conflict("slideshow is on", "backgrounds")]
    )
    monkeypatch.setattr(setter, "largest_monitor", lambda: (1920, 1080))
    wallpapers: list[Path] = []
    monkeypatch.setattr(setter, "set_wallpaper", wallpapers.append)
    monkeypatch.setattr(cli, "HttpClient", FakeHttp)
    source = FakeSource([[candidate(n) for n in range(10)]])
    monkeypatch.setattr(sources, "build", lambda config, http: [source])
    return wallpapers


def run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    settings: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Runs one command the way the applet does: settings on stdin, one JSON line back."""
    monkeypatch.setattr(protocol, "_sent", False)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"queue-size": 2, **(settings or {})})))
    code = cli.main([command])
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1, lines
    return code, json.loads(lines[0])


def test_info_before_anything_is_shown(
    backend: list[Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, answer = run(monkeypatch, capsys, "info")
    assert code == 0
    assert answer == {
        "image": None,
        "queued": 0,
        "conflicts": [{"message": "slideshow is on", "settings_module": "backgrounds"}],
    }


def test_next_sets_wallpaper_answers_then_refills(
    backend: list[Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, answer = run(monkeypatch, capsys, "next")
    assert code == 0
    assert [p.name for p in backend] == [Path(answer["image"]["path"]).name]
    assert answer["image"]["page_url"].startswith("https://example.com/")
    assert answer["image"]["shown_at"] is not None
    assert answer["queued"] == 0  # measured before the refill that follows the answer

    _, info = run(monkeypatch, capsys, "info")
    assert info["image"]["id"] == answer["image"]["id"]
    assert info["queued"] == 2  # queue-size from stdin


def test_fav_copies_and_marks(
    backend: list[Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    run(monkeypatch, capsys, "next")
    _, answer = run(monkeypatch, capsys, "fav", {"favorites-dir": str(tmp_path / "favs")})
    assert answer["image"]["favorite"] is True
    assert (tmp_path / "favs" / Path(answer["image"]["path"]).name).exists()


def test_ban_moves_on_and_deletes_the_file(
    backend: list[Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, first = run(monkeypatch, capsys, "next")
    _, second = run(monkeypatch, capsys, "ban")
    assert second["image"]["id"] != first["image"]["id"]
    assert not Path(first["image"]["path"]).exists()


def test_errors_are_one_json_line(
    backend: list[Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, answer = run(monkeypatch, capsys, "fav")
    assert code == 1
    assert answer == {"error": "No wallpaper has been shown yet."}


def test_protocol_sends_only_the_first_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(protocol, "_sent", False)
    protocol.emit({"a": 1})
    assert protocol.fail("later") == 1
    assert capsys.readouterr().out == '{"a": 1}\n'
