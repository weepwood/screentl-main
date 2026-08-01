"""Independent FFmpeg renderer for indexed recording sessions."""

from __future__ import annotations

import datetime as dt
import os
import random
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageOps

from .sessions import RecordingSession, SessionRepository, TimelineFrame
from .timeline import TimelineService, apply_privacy_masks

SUPPORTED_AUDIO = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}
CODECS = {
    "h264": "libx264",
    "h265": "libx265",
    "vp9": "libvpx-vp9",
    "nvenc": "h264_nvenc",
    "qsv": "h264_qsv",
    "amf": "h264_amf",
}


class RenderCancelled(RuntimeError):
    """Raised when an FFmpeg render is cancelled by the user."""


@dataclass(frozen=True)
class RenderOptions:
    output_format: str = "mp4"
    codec: str = "h264"
    bitrate: str = "4M"
    resolution: tuple[int, int] | None = None
    audio_mode: str = "none"
    audio_path: Path | None = None
    audio_folder: Path | None = None
    audio_volume: float = 0.2
    audio_fade_seconds: float = 1.0
    fps: int = 25
    mask_mode: str = "blur"
    include_excluded: bool = False
    split_by_hour: bool = False
    overwrite: bool = False

    def validate(self) -> None:
        if self.output_format not in {"mp4", "gif"}:
            raise ValueError("output format must be mp4 or gif")
        if self.codec not in CODECS:
            raise ValueError(f"unsupported codec: {self.codec}")
        if self.fps <= 0:
            raise ValueError("fps must be greater than zero")
        if self.audio_mode not in {"none", "fixed", "random", "loop", "sequence"}:
            raise ValueError(f"unsupported audio mode: {self.audio_mode}")
        if not 0 <= self.audio_volume <= 4:
            raise ValueError("audio volume must be between 0 and 4")
        if self.audio_fade_seconds < 0:
            raise ValueError("audio fade cannot be negative")
        if self.resolution is not None and min(self.resolution) <= 0:
            raise ValueError("resolution values must be positive")


class FFmpegSessionRenderer:
    def __init__(
        self,
        repository: SessionRepository,
        executable: str | None = None,
    ) -> None:
        self.repository = repository
        self.executable = executable or imageio_ffmpeg.get_ffmpeg_exe()

    def render(
        self,
        session_id: str,
        options: RenderOptions | None = None,
        cancel_event: threading.Event | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> list[Path]:
        options = options or RenderOptions()
        options.validate()
        session = self.repository.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session: {session_id}")
        frames = self.repository.list_frames(
            session_id,
            limit=100000,
            include_excluded=options.include_excluded,
        )
        if not options.include_excluded:
            frames = [frame for frame in frames if not frame.excluded]
        if not frames:
            raise ValueError("session has no frames to render")

        groups = self._group_frames(frames, options.split_by_hour)
        outputs: list[Path] = []
        for index, (label, group) in enumerate(groups):
            offset = index / len(groups)
            scale = 1 / len(groups)

            def group_progress(value: float, *, offset: float = offset, scale: float = scale) -> None:
                if on_progress is not None:
                    on_progress(offset + value * scale)

            outputs.append(
                self._render_group(
                    session,
                    label,
                    group,
                    options,
                    cancel_event,
                    group_progress,
                )
            )
        if on_progress is not None:
            on_progress(1.0)
        return outputs

    @staticmethod
    def _group_frames(
        frames: list[TimelineFrame],
        split_by_hour: bool,
    ) -> list[tuple[str, list[TimelineFrame]]]:
        if not split_by_hour:
            return [("", frames)]
        buckets: dict[str, list[TimelineFrame]] = {}
        for frame in frames:
            hour = frame.captured_at[:13].replace(":", "-").replace("T", "_")
            buckets.setdefault(hour, []).append(frame)
        return [(key, buckets[key]) for key in sorted(buckets)]

    def _render_group(
        self,
        session: RecordingSession,
        label: str,
        frames: list[TimelineFrame],
        options: RenderOptions,
        cancel_event: threading.Event | None,
        on_progress: Callable[[float], None],
    ) -> Path:
        job_id = self.repository.create_render_job(
            session.id,
            options.output_format,
            {
                "codec": options.codec,
                "resolution": options.resolution,
                "audio_mode": options.audio_mode,
                "split_label": label,
            },
        )
        try:
            output = self._execute_group(
                session,
                label,
                frames,
                options,
                job_id,
                cancel_event,
                on_progress,
            )
        except RenderCancelled:
            self.repository.update_render_job(job_id, "cancelled")
            raise
        except Exception as exc:
            self.repository.update_render_job(job_id, "failed", error=str(exc))
            raise
        self.repository.update_render_job(
            job_id,
            "completed",
            progress=1.0,
            output_path=output,
        )
        return output

    def _execute_group(
        self,
        session: RecordingSession,
        label: str,
        frames: list[TimelineFrame],
        options: RenderOptions,
        job_id: str,
        cancel_event: threading.Event | None,
        on_progress: Callable[[float], None],
    ) -> Path:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        label_part = f"_{label}" if label else ""
        destination = session.output_path / (
            f"{session.name}_{stamp}{label_part}.{options.output_format}"
        )
        if destination.exists() and not options.overwrite:
            destination = destination.with_stem(f"{destination.stem}_{uuid.uuid4().hex[:6]}")
        temporary = destination.with_name(
            f".{destination.stem}.{uuid.uuid4().hex}.part{destination.suffix}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="screentl-render-") as directory:
            workspace = Path(directory)
            prepared = self._prepare_frames(frames, workspace, options)
            concat_file = self._write_concat_file(prepared, frames, workspace)
            duration = sum(max(0.04, frame.duration) for frame in frames)
            command = self._build_command(
                concat_file,
                temporary,
                duration,
                options,
                workspace,
            )
            try:
                self._run_process(
                    command,
                    duration,
                    job_id,
                    cancel_event,
                    on_progress,
                )
                if cancel_event is not None and cancel_event.is_set():
                    raise RenderCancelled("render cancelled")
                os.replace(temporary, destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
        return destination

    def _prepare_frames(
        self,
        frames: list[TimelineFrame],
        workspace: Path,
        options: RenderOptions,
    ) -> list[Path]:
        prepared: list[Path] = []
        for index, frame in enumerate(frames):
            with Image.open(frame.path) as source:
                image = apply_privacy_masks(source, frame.masks, options.mask_mode)
                if options.resolution is not None:
                    image = ImageOps.fit(
                        image,
                        options.resolution,
                        method=Image.Resampling.LANCZOS,
                        centering=(0.5, 0.5),
                    )
                elif image.width % 2 or image.height % 2:
                    image = ImageOps.pad(
                        image,
                        (image.width + image.width % 2, image.height + image.height % 2),
                        color="black",
                    )
                path = workspace / f"frame_{index:08d}.png"
                image.save(path, "PNG", optimize=True)
                prepared.append(path)
        return prepared

    @staticmethod
    def _ffmpeg_quote(path: Path) -> str:
        escaped = str(path.resolve()).replace("'", "'\\''")
        return f"'{escaped}'"

    def _write_concat_file(
        self,
        prepared: list[Path],
        frames: list[TimelineFrame],
        workspace: Path,
    ) -> Path:
        lines: list[str] = []
        for path, frame in zip(prepared, frames, strict=True):
            lines.append(f"file {self._ffmpeg_quote(path)}")
            lines.append(f"duration {max(0.04, frame.duration):.6f}")
        lines.append(f"file {self._ffmpeg_quote(prepared[-1])}")
        destination = workspace / "frames.ffconcat"
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return destination

    def _select_audio(self, options: RenderOptions) -> list[Path]:
        if options.output_format == "gif" or options.audio_mode == "none":
            return []
        if options.audio_path is not None:
            if not options.audio_path.is_file():
                raise FileNotFoundError(options.audio_path)
            return [options.audio_path]
        folder = options.audio_folder
        if folder is None or not folder.is_dir():
            raise FileNotFoundError("audio folder is unavailable")
        candidates = sorted(
            path for path in folder.iterdir() if path.suffix.casefold() in SUPPORTED_AUDIO
        )
        if not candidates:
            raise FileNotFoundError("audio folder contains no supported files")
        if options.audio_mode == "random":
            return [random.choice(candidates)]
        if options.audio_mode in {"fixed", "loop"}:
            return [candidates[0]]
        return candidates

    def _write_audio_concat(self, paths: list[Path], workspace: Path) -> Path:
        destination = workspace / "audio.ffconcat"
        destination.write_text(
            "\n".join(f"file {self._ffmpeg_quote(path)}" for path in paths) + "\n",
            encoding="utf-8",
        )
        return destination

    def _build_command(
        self,
        concat_file: Path,
        output: Path,
        duration: float,
        options: RenderOptions,
        workspace: Path,
    ) -> list[str]:
        command = [
            self.executable,
            "-hide_banner",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
        ]
        audio = self._select_audio(options)
        if audio:
            if options.audio_mode == "loop":
                command.extend(["-stream_loop", "-1", "-i", str(audio[0])])
            elif options.audio_mode == "sequence":
                audio_concat = self._write_audio_concat(audio, workspace)
                command.extend(["-f", "concat", "-safe", "0", "-i", str(audio_concat)])
            else:
                command.extend(["-i", str(audio[0])])

        if options.output_format == "gif":
            filter_graph = (
                f"[0:v]fps={min(options.fps, 30)},split[s0][s1];"
                "[s0]palettegen=max_colors=256[p];"
                "[s1][p]paletteuse=dither=sierra2_4a[out]"
            )
            command.extend(["-filter_complex", filter_graph, "-map", "[out]", "-loop", "0"])
        else:
            command.extend(
                [
                    "-c:v",
                    CODECS[options.codec],
                    "-b:v",
                    options.bitrate,
                    "-r",
                    str(options.fps),
                ]
            )
            if options.codec in {"h264", "h265"}:
                command.extend(["-preset", "medium"])
            command.extend(["-pix_fmt", "yuv420p", "-movflags", "+faststart"])
            if audio:
                fade_out_start = max(0.0, duration - options.audio_fade_seconds)
                filters = [f"volume={options.audio_volume}"]
                if options.audio_fade_seconds > 0:
                    filters.extend(
                        [
                            f"afade=t=in:st=0:d={options.audio_fade_seconds}",
                            f"afade=t=out:st={fade_out_start}:d={options.audio_fade_seconds}",
                        ]
                    )
                command.extend(
                    [
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a:0",
                        "-filter:a",
                        ",".join(filters),
                        "-c:a",
                        "aac",
                        "-shortest",
                    ]
                )
        command.extend(["-progress", "pipe:1", "-nostats", str(output)])
        return command

    def _run_process(
        self,
        command: list[str],
        duration: float,
        job_id: str,
        cancel_event: threading.Event | None,
        on_progress: Callable[[float], None],
    ) -> None:
        creationflags = 0x08000000 if os.name == "nt" else 0
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        stderr_lines: list[str] = []

        def read_errors() -> None:
            if process.stderr is not None:
                stderr_lines.extend(process.stderr.readlines())

        stderr_thread = threading.Thread(target=read_errors, daemon=True)
        stderr_thread.start()
        try:
            if process.stdout is None:
                raise RuntimeError("FFmpeg progress stream is unavailable")
            for raw_line in process.stdout:
                if cancel_event is not None and cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise RenderCancelled("render cancelled")
                key, separator, value = raw_line.strip().partition("=")
                if separator and key in {"out_time_ms", "out_time_us"}:
                    progress = min(0.99, int(value) / max(1, duration * 1_000_000))
                    self.repository.update_render_job(job_id, "running", progress=progress)
                    on_progress(progress)
            return_code = process.wait()
            stderr_thread.join(2)
            if return_code != 0:
                message = "".join(stderr_lines[-30:]).strip()
                raise RuntimeError(message or f"FFmpeg exited with code {return_code}")
        finally:
            if process.poll() is None:
                process.kill()

    def render_contact_sheet(
        self,
        session_id: str,
        destination: Path | None = None,
    ) -> Path:
        session = self.repository.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session: {session_id}")
        target = destination or session.output_path / (
            f"{session.name}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_contact-sheet.jpg"
        )
        return TimelineService(self.repository).build_contact_sheet(session_id, target)

    def recover_interrupted_jobs(self) -> int:
        return self.repository.recover_render_jobs()
