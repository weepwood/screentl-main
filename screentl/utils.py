import datetime
import json
import os
import pyautogui
import sched
import time

TODAY = datetime.date.today().strftime('%Y-%m-%d')


def _get_num(folder: str):
    # mkdir with the provided name
    if not os.path.exists(folder):
        os.makedirs(folder)

    # initialize the first index, either continue from last screenshot or create the first.
    if os.path.exists(f'{folder}/num.json'):
        with open(f'{folder}/num.json', 'r') as f:
            data = json.load(f)
            num = data['num']
    else:
        num = 0

    return num


def _do_screenshot(folder: str):
    num = _get_num(folder)

    filename = f'{folder}/screenshot_{num}_{time.strftime("%Y%m%d_%H%M%S", time.localtime())}.png'
    pyautogui.screenshot(filename)
    start = time.time()
    print(f'Captured screenshot {num} at {time.ctime(start)}')
    num += 1
    with open(f'{folder}/num.json', 'w') as f:
        json.dump({'num': num}, f)


def screenshot(interval: int = 30,
               folder: str = TODAY):
    """
    Execute screen shot
    :param interval: how often the screen is captured.
    :param folder: folder where to store the file. By default the folder name is the date.
    :return: None
    """
    scheduler = sched.scheduler(time.time, time.sleep)

    while True:
        scheduler.enter(interval,
                        1,
                        _do_screenshot,
                        kwargs={
                            'folder': folder,
                        })
        scheduler.run()

# if you want to stop screen capturing, please stop this process
# or Ctrl+c on the terminal



