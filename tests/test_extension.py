"""IDE extension packaging / install helpers."""

from __future__ import annotations

from pathlib import Path

from pulse.__main__ import EMBED_ROOT, _EXTENSION_ID, _extension_vsix, extension_install


def test_embedded_vsix_ships():
    vsix = EMBED_ROOT / "extension" / "pulse-board.vsix"
    assert vsix.is_file(), vsix
    assert vsix.stat().st_size > 1000
    assert _extension_vsix() == vsix


def test_extension_install_invokes_ide_cli(monkeypatch, tmp_path: Path):
    fake = tmp_path / "cursor"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)

    calls: list[list[str]] = []

    def fake_call(argv, *args, **kwargs):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(
        "pulse.__main__._ide_cli_bins",
        lambda: [("cursor", str(fake))],
    )
    monkeypatch.setattr("pulse.__main__.subprocess.call", fake_call)

    extension_install(ide="cursor")
    assert len(calls) == 1
    assert calls[0][0] == str(fake)
    assert "--install-extension" in calls[0]
    assert calls[0][-2] == "--force" or calls[0][-1] == "--force"
    assert any(str(p).endswith("pulse-board.vsix") for p in calls[0])
    assert _EXTENSION_ID == "pulse.pulse-board"
