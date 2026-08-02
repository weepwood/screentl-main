import sys

INSTANCE_MUTEX = r"Local\ScreenshotTimeLapse"


def main() -> int:
    if "--diagnose" in sys.argv:
        from screentl.diagnostics import run_diagnostics

        return run_diagnostics()

    from screentl.instance_lock import (
        SingleInstance,
        activate_existing_window,
    )
    from screentl.safe_journal_app import run_safe_journal_app
    from screentl.ui import APP_NAME

    instance = SingleInstance(INSTANCE_MUTEX)
    if not instance.acquire():
        activate_existing_window(APP_NAME)
        return 0
    try:
        run_safe_journal_app()
    finally:
        instance.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
