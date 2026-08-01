from pathlib import Path

from PIL import Image

import screentl.intelligence as intelligence
from screentl.intelligence import LocalIntelligenceService, TesseractOCR
from screentl.sessions import SessionRepository


def add_frame(repo, session, name, color, time, app="", title="", ocr=""):
    path = session.frames_path / name
    Image.new("RGB", (80, 45), color).save(path)
    return repo.add_frame(
        session.id,
        path,
        captured_at=time,
        app_name=app,
        window_title=title,
        ocr_text=ocr,
    )


def test_local_search_clusters_stagnation_and_summary(tmp_path):
    repo = SessionRepository(tmp_path / "sessions.db")
    session = repo.create_session(tmp_path / "data", "Intelligence")
    add_frame(
        repo,
        session,
        "one.png",
        "red",
        "2026-08-02T10:00:00+00:00",
        "Code",
        "Editor",
        "hello project",
    )
    add_frame(
        repo,
        session,
        "two.png",
        "red",
        "2026-08-02T10:01:00+00:00",
        "Code",
        "Editor",
    )
    add_frame(
        repo,
        session,
        "three.png",
        "red",
        "2026-08-02T10:02:00+00:00",
        "Code",
        "Editor",
    )

    service = LocalIntelligenceService(repo)
    results = service.search(session.id, "project")
    clusters = service.cluster_by_application(session.id)
    summary = service.build_summary(session.id)

    assert results[0].matched_field == "ocr"
    assert len(clusters["Code"]) == 3
    assert summary["top_applications"] == [("Code", 3)]
    assert summary["stagnation_periods"][0]["frames"] == 3

    markdown = service.export_summary(session.id, tmp_path / "summary.md")
    json_output = service.export_summary(session.id, tmp_path / "summary.json")
    assert "会话摘要" in markdown.read_text(encoding="utf-8")
    assert json_output.read_text(encoding="utf-8").startswith("{")


def test_tesseract_ocr_uses_local_process(tmp_path, monkeypatch):
    image = tmp_path / "frame.png"
    image.touch()
    calls = []

    class Result:
        returncode = 0
        stdout = "recognized text\n"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    monkeypatch.setattr(intelligence.subprocess, "run", fake_run)
    text = TesseractOCR(executable="tesseract", language="eng").extract_text(image)

    assert text == "recognized text"
    assert calls[0][0][1] == str(image)
    assert calls[0][0][-1] == "eng"
