"""Video rendering with cancellation and atomic output replacement."""

from __future__ import annotations

import datetime
import os
import random
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Event

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageSequenceClip,
    TextClip,
)
from proglog import ProgressBarLogger

from .storage import list_screenshots

TODAY = datetime.date.today().strftime("%Y-%m-%d")


class VideoCancelled(RuntimeError):
    """Raised when a cooperative video render is cancelled."""


class _RenderLogger(ProgressBarLogger):
    def __init__(
        self,
        cancel_event: Event | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
        super().__init__()
        self.cancel_event = cancel_event
        self.on_progress = on_progress

    def _check_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise VideoCancelled("video rendering cancelled")

    def callback(self, **changes):
        self._check_cancelled()
        return super().callback(**changes)

    def bars_callback(self, bar, attr, value, old_value=None):
        self._check_cancelled()
        result = super().bars_callback(bar, attr, value, old_value)
        if self.on_progress is not None and bar == "t" and attr == "index":
            total = self.bars.get(bar, {}).get("total")
            if total:
                self.on_progress(min(1.0, max(0.0, value / total)))
        return result


def _write_video_atomically(
    final,
    duration: float,
    output: Path,
    cancel_event: Event | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Render to a temporary MP4 and replace the final file on success."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(
        f".{output.stem}.{uuid.uuid4().hex}.part{output.suffix}"
    )
    logger = _RenderLogger(cancel_event, on_progress)

    if cancel_event is not None and cancel_event.is_set():
        raise VideoCancelled("video rendering cancelled")

    try:
        final.set_duration(duration).write_videofile(
            str(temporary),
            bitrate=None,
            logger=logger,
        )
        if cancel_event is not None and cancel_event.is_set():
            raise VideoCancelled("video rendering cancelled")
        os.replace(temporary, output)
        if on_progress is not None:
            on_progress(1.0)
        return output
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def make_video(
    folder: str = TODAY,
    fps: int = 25,
    audio_loc: str = "audio",
    text: str = TODAY,
    output_name: str = "video.mp4",
    cancel_event: Event | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Build an MP4 without replacing the final output until success."""
    if fps <= 0:
        raise ValueError("fps must be greater than zero")
    if not output_name.lower().endswith(".mp4"):
        raise ValueError("output filename must use the .mp4 extension")

    folder_path = Path(folder)
    if not folder_path.is_dir():
        raise FileNotFoundError(
            f"screenshot folder does not exist: {folder_path}"
        )

    screenshots = list_screenshots(folder_path)
    if not screenshots:
        raise FileNotFoundError(
            f"no screenshot_*.png files found in: {folder_path}"
        )

    images_list = [str(image) for image in screenshots]
    duration = len(images_list) / fps
    video_clip = ImageSequenceClip(images_list, fps=fps)
    output = folder_path / output_name
    audio_clip = None
    final = video_clip

    if text:
        try:
            title_clip = TextClip(str(text), color="white", fontsize=60)
            title_overlay = title_clip.set_pos("center").set_duration(
                min(3, duration)
            )
            final = CompositeVideoClip([video_clip, title_overlay])
        except Exception as exc:
            print(f"Warning: title overlay disabled: {exc}")

    audio_path = Path(audio_loc)
    if audio_path.is_dir():
        candidates = []
        for path in audio_path.iterdir():
            if path.suffix.lower() not in {
                ".mp3",
                ".m4a",
                ".wav",
                ".aac",
                ".ogg",
            }:
                continue
            try:
                clip = AudioFileClip(str(path))
                candidates.append((path, clip.duration))
                clip.close()
            except Exception as exc:
                print(f"Warning: unable to inspect audio {path}: {exc}")

        suitable = [path for path, length in candidates if length >= duration]
        if suitable:
            selected_audio = random.choice(suitable)
            audio_clip = AudioFileClip(str(selected_audio)).subclip(0, duration)
            final = final.set_audio(audio_clip)
        elif candidates:
            print(
                "Warning: no audio track is long enough; "
                "video will be silent."
            )
        else:
            print(
                f"Warning: no supported audio files found in {audio_path}; "
                "video will be silent."
            )
    else:
        print(
            f"Warning: audio folder not found: {audio_path}; "
            "video will be silent."
        )

    try:
        return _write_video_atomically(
            final=final,
            duration=duration,
            output=output,
            cancel_event=cancel_event,
            on_progress=on_progress,
        )
    finally:
        if audio_clip is not None:
            audio_clip.close()
        final.close()
        if final is not video_clip:
            video_clip.close()
