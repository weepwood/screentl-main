import sys

if "--diagnose" in sys.argv:
    from screentl.diagnostics import run_diagnostics

    raise SystemExit(run_diagnostics())

from screentl.application import run_desktop_app
from screentl.instance_lock import (
    SingleInstance,
    activate_existing_window,
)
from screentl.ui import APP_NAME

INSTANCE_MUTEX = r"Local\ScreenshotTimeLapse"


if __name__ == "__main__":
    instance = SingleInstance(INSTANCE_MUTEX)
    if not instance.acquire():
        activate_existing_window(APP_NAME)
    else:
        try:
            run_desktop_app()
        finally:
            instance.release()
