from screentl.instance_lock import (
    SingleInstance,
    activate_existing_window,
)
from screentl.ui import APP_NAME, main

INSTANCE_MUTEX = r'Local\ScreenshotTimeLapse'


if __name__ == '__main__':
    instance = SingleInstance(INSTANCE_MUTEX)
    if not instance.acquire():
        activate_existing_window(APP_NAME)
    else:
        try:
            main()
        finally:
            instance.release()
