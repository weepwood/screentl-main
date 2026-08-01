import argparse
from pathlib import Path

from screentl.cli import run_capture
from screentl.models import CaptureConfig
from screentl.settings import AppSettings


def main() -> int:
    defaults = AppSettings.defaults()
    parser = argparse.ArgumentParser(description="Capture periodic screenshots.")
    parser.add_argument(
        "--folder",
        default=defaults.folder,
        help="output folder (default: user Pictures/ScreenshotTimeLapse/<date>)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=defaults.interval,
        help="seconds between captures",
    )
    args = parser.parse_args()
    if not str(args.folder).strip():
        parser.error("--folder cannot be empty")
    try:
        return run_capture(
            CaptureConfig(folder=Path(args.folder).expanduser(), interval=args.interval)
        )
    except ValueError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
