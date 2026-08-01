from pathlib import Path
from threading import Event

from PIL import Image

from screentl.capture_engine import SessionCaptureEngine, SessionCaptureOptions
from screentl.privacy import ActiveWindowInfo, PrivacyGuard, PrivacyRules
from screentl.sessions import SessionRepository


class FakeBackend:
    def __init__(self, color="purple"):
        self.color = color
        self.calls = 0

    def capture(self, _options, _window):
        self.calls += 1
        return Image.new("RGB", (100, 60), self.color)


class FakeOCR:
    def extract_text(self, image: Path) -> str:
        assert image.is_file()
        return "local text"


def test_privacy_guard_manual_app_title_idle_and_battery(monkeypatch):
    import screentl.privacy as privacy

    window = ActiveWindowInfo("Secret document", "vault.exe", (0, 0, 100, 100))
    monkeypatch.setattr(privacy, "get_active_window_info", lambda: window)
    monkeypatch.setattr(privacy, "is_workstation_locked", lambda: False)
    monkeypatch.setattr(privacy, "is_on_battery", lambda: False)
    monkeypatch.setattr(privacy, "get_idle_seconds", lambda: 0)

    guard = PrivacyGuard(PrivacyRules(excluded_apps=["vault.exe"]))
    assert guard.should_capture()[:2] == (False, "excluded application")

    guard.rules.excluded_apps = []
    guard.rules.excluded_title_keywords = ["secret"]
    assert guard.should_capture()[:2] == (False, "excluded window title")

    guard.rules.excluded_title_keywords = []
    guard.toggle_manual_pause()
    assert guard.should_capture()[:2] == (False, "manual privacy pause")
    guard.toggle_manual_pause()

    guard.rules.idle_pause_seconds = 5
    monkeypatch.setattr(privacy, "get_idle_seconds", lambda: 10)
    assert guard.should_capture()[:2] == (False, "user idle")

    guard.rules.idle_pause_seconds = 0
    guard.rules.pause_on_battery = True
    monkeypatch.setattr(privacy, "is_on_battery", lambda: True)
    assert guard.should_capture()[:2] == (False, "running on battery")


def test_session_capture_engine_indexes_frame_and_ocr(tmp_path):
    repo = SessionRepository(tmp_path / "sessions.db")
    session = repo.create_session(tmp_path / "data", "Capture")
    backend = FakeBackend()
    rules = PrivacyRules(collect_window_metadata=True, ocr_enabled=True, pause_when_locked=False)
    guard = PrivacyGuard(rules)
    stop = Event()
    captured = []

    import screentl.privacy as privacy

    original = privacy.get_active_window_info
    privacy.get_active_window_info = lambda: ActiveWindowInfo(
        "Editor",
        "editor.exe",
        (0, 0, 100, 60),
    )
    try:
        engine = SessionCaptureEngine(
            repo,
            session,
            SessionCaptureOptions(image_format="webp", quality=80, scale=0.5),
            guard,
            backend=backend,
            ocr=FakeOCR(),
        )

        def on_capture(path):
            captured.append(path)
            stop.set()

        engine(1, str(session.frames_path), stop_event=stop, on_capture=on_capture)
    finally:
        privacy.get_active_window_info = original

    assert backend.calls == 1
    assert len(captured) == 1
    assert captured[0].suffix == ".webp"
    frames = repo.list_frames(session.id)
    assert frames[0].app_name == "editor.exe"
    assert frames[0].window_title == "Editor"
    assert frames[0].ocr_text == "local text"
    assert frames[0].width == 50
    assert frames[0].height == 30


def test_session_capture_engine_skips_when_privacy_blocks(tmp_path):
    repo = SessionRepository(tmp_path / "sessions.db")
    session = repo.create_session(tmp_path / "data", "Blocked")
    guard = PrivacyGuard(PrivacyRules(pause_when_locked=False))
    guard.manual_pause.set()
    stop = Event()
    reasons = []

    def skipped(reason):
        reasons.append(reason)
        stop.set()

    engine = SessionCaptureEngine(
        repo,
        session,
        privacy=guard,
        backend=FakeBackend(),
        on_skip=skipped,
    )
    engine(1, str(session.frames_path), stop_event=stop)

    assert reasons == ["manual privacy pause"]
    assert repo.list_frames(session.id) == []
