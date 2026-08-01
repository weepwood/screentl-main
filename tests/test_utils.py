from pathlib import Path
from threading import Event

from screentl import utils


def test_screenshot_writes_numbered_file(tmp_path, monkeypatch):
    stop_event = Event()
    captured = []

    def fake_screenshot(filename):
        captured.append(filename)
        Path(filename).write_bytes(b'fake png')
        stop_event.set()

    monkeypatch.setattr(utils.pyautogui, 'screenshot', fake_screenshot)
    utils.screenshot(
        interval=1,
        folder=tmp_path,
        stop_event=stop_event,
        on_capture=lambda path: captured.append(path),
    )

    files = list(tmp_path.glob('screenshot_*.png'))
    assert len(files) == 1
    assert len(captured) == 2
    assert captured[0].endswith('.png')
    assert captured[1].name.startswith('screenshot_0_')
    assert (tmp_path / 'num.json').read_text(encoding='utf-8') == '{"num": 1}'


def test_invalid_interval_is_rejected(tmp_path):
    try:
        utils.screenshot(interval=0, folder=tmp_path)
    except ValueError as exc:
        assert 'greater than zero' in str(exc)
    else:
        raise AssertionError('expected ValueError')
