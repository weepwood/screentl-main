from pathlib import Path

from screentl import diagnostics


def test_diagnostics_reports_packaged_dependencies(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"fake")
    monkeypatch.setattr(
        diagnostics.imageio_ffmpeg,
        "get_ffmpeg_exe",
        lambda: str(ffmpeg),
    )

    result = diagnostics.collect_diagnostics()

    assert result["application"] == "ScreenshotTimeLapse"
    assert result["ffmpeg_exists"] is True
    assert Path(str(result["ffmpeg"])) == ffmpeg
