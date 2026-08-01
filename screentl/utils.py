import datetime
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Event

import pyautogui

from .storage import atomic_write_json, next_screenshot_number, parse_screenshot_name

TODAY = datetime.date.today().strftime('%Y-%m-%d')


def _get_num(folder: str | Path) -> int:
    """Create the output directory and return a collision-resistant next number."""
    return next_screenshot_number(folder)


def _do_screenshot(folder: str | Path, number: int | None = None) -> Path:
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    num = _get_num(folder_path) if number is None else max(0, number)

    while True:
        timestamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())
        filename = folder_path / f'screenshot_{num}_{timestamp}.png'
        if not filename.exists():
            break
        num += 1

    temporary = folder_path / f'.{filename.stem}.{uuid.uuid4().hex}.tmp.png'
    try:
        pyautogui.screenshot(str(temporary))
        if not temporary.is_file():
            raise OSError(f'screenshot backend did not create a file: {temporary}')
        os.replace(temporary, filename)
        atomic_write_json(folder_path / 'num.json', {'num': num + 1})
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    start = time.time()
    print(f'Captured screenshot {num} at {time.ctime(start)}')
    return filename


def screenshot(interval: int = 30,
               folder: str = TODAY,
               stop_event: Event | None = None,
               pause_event: Event | None = None,
               on_capture: Callable[[Path], None] | None = None):
    """
    Execute screen shot
    :param interval: how often the screen is captured.
    :param folder: folder where to store the file. By default the folder name is the date.
    :return: None
    """
    if interval <= 0:
        raise ValueError('interval must be greater than zero')

    next_number = _get_num(folder)
    while stop_event is None or not stop_event.is_set():
        if pause_event is not None:
            pause_event.wait()
            if stop_event is not None and stop_event.is_set():
                break
        image_path = _do_screenshot(folder, next_number)
        parsed = parse_screenshot_name(image_path)
        if parsed is None:
            raise RuntimeError(f'unexpected screenshot filename: {image_path.name}')
        next_number = parsed[0] + 1
        if on_capture is not None:
            on_capture(image_path)
        if stop_event is None:
            time.sleep(interval)
        elif stop_event.wait(interval):
            break

# if you want to stop screen capturing, please stop this process
# or Ctrl+c on the terminal
