import datetime
import json
import time
from pathlib import Path
from threading import Event

import pyautogui

TODAY = datetime.date.today().strftime('%Y-%m-%d')


def _get_num(folder: str | Path) -> int:
    """Create the output directory and return the next screenshot number."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    counter_file = folder / 'num.json'

    # initialize the first index, either continue from last screenshot or create the first.
    if not counter_file.exists():
        return 0

    try:
        with counter_file.open('r', encoding='utf-8') as f:
            return max(0, int(json.load(f)['num']))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        # A damaged counter should not prevent future captures.
        return 0


def _do_screenshot(folder: str | Path) -> Path:
    folder = Path(folder)
    num = _get_num(folder)

    timestamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())
    filename = folder / f'screenshot_{num}_{timestamp}.png'
    pyautogui.screenshot(str(filename))
    start = time.time()
    print(f'Captured screenshot {num} at {time.ctime(start)}')
    num += 1
    with (folder / 'num.json').open('w', encoding='utf-8') as f:
        json.dump({'num': num}, f)
    return filename


def screenshot(interval: int = 30,
               folder: str = TODAY,
               stop_event: Event | None = None):
    """
    Execute screen shot
    :param interval: how often the screen is captured.
    :param folder: folder where to store the file. By default the folder name is the date.
    :return: None
    """
    if interval <= 0:
        raise ValueError('interval must be greater than zero')

    while stop_event is None or not stop_event.is_set():
        _do_screenshot(folder)
        if stop_event is None:
            time.sleep(interval)
        elif stop_event.wait(interval):
            break

# if you want to stop screen capturing, please stop this process
# or Ctrl+c on the terminal

