import argparse
from pathlib import Path

from screentl.cli import run_render
from screentl.models import RenderConfig
from screentl.settings import AppSettings


def main() -> int:
    defaults = AppSettings.defaults()
    parser = argparse.ArgumentParser(
        description="Turn screenshots into an MP4 video."
    )
    parser.add_argument(
        "--folder",
        default=defaults.folder,
        help="screenshot folder (default: user Pictures/ScreenshotTimeLapse/<date>)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=defaults.fps,
        help="video frames per second",
    )
    parser.add_argument(
        "--audio",
        default=defaults.audio,
        help="audio folder; use an empty value for silent video",
    )
    parser.add_argument(
        "--text",
        default=defaults.text,
        help="title text; use an empty string to disable",
    )
    parser.add_argument(
        "--output",
        default="video.mp4",
        help="output MP4 filename",
    )
    args = parser.parse_args()
    if not str(args.folder).strip():
        parser.error("--folder cannot be empty")

    audio = str(args.audio).strip()
    try:
        exit_code, _output = run_render(
            RenderConfig(
                folder=Path(args.folder).expanduser(),
                fps=args.fps,
                audio_folder=Path(audio).expanduser() if audio else None,
                title=args.text,
                output_name=args.output,
            )
        )
        return exit_code
    except ValueError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
