"""Session-aware multi-monitor capture engine."""

from __future__ import annotations

import datetime as dt
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol

import mss
from PIL import Image

from .privacy import ActiveWindowInfo, PrivacyGuard
from .sessions import RecordingSession, SessionRepository


class OCRProvider(Protocol):
    def extract_text(self, image: Path) -> str: ...


class NullOCR:
    def extract_text(self, image: Path) -> str:
        return ""


@dataclass
class SessionCaptureOptions:
    monitor: int = 1
    region: tuple[int, int, int, int] | None = None
    active_window_only: bool = False
    image_format: str = "png"
    quality: int = 90
    scale: float = 1.0
    auto_exclude_duplicates: bool = True
    daily_rollover: bool = False
    continue_across_midnight: bool = True

    def validate(self) -> None:
        if self.monitor < 0:
            raise ValueError("monitor index cannot be negative")
        if self.image_format.casefold() not in {"png", "jpeg", "jpg", "webp"}:
            raise ValueError("image format must be PNG, JPEG or WebP")
        if not 1 <= self.quality <= 100:
            raise ValueError("image quality must be between 1 and 100")
        if not 0.1 <= self.scale <= 1.0:
            raise ValueError("image scale must be between 0.1 and 1.0")
        if self.region is not None:
            _left, _top, width, height = self.region
            if width <= 0 or height <= 0:
                raise ValueError("capture region width and height must be positive")


class MSSCaptureBackend:
    def monitor_count(self) -> int:
        with mss.mss() as capture:
            return max(0, len(capture.monitors) - 1)

    def capture(
        self,
        options: SessionCaptureOptions,
        window: ActiveWindowInfo,
    ) -> Image.Image:
        options.validate()
        with mss.mss() as capture:
            if options.active_window_only:
                if window.rect is None:
                    raise RuntimeError("active window bounds are unavailable")
                left, top, width, height = window.rect
                area = {"left": left, "top": top, "width": width, "height": height}
            elif options.region is not None:
                left, top, width, height = options.region
                area = {"left": left, "top": top, "width": width, "height": height}
            else:
                if options.monitor >= len(capture.monitors):
                    raise ValueError(
                        f"monitor {options.monitor} is unavailable; "
                        f"detected {max(0, len(capture.monitors) - 1)} monitors"
                    )
                area = capture.monitors[options.monitor]
            shot = capture.grab(area)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
        if options.scale != 1.0:
            target = (
                max(1, round(image.width * options.scale)),
                max(1, round(image.height * options.scale)),
            )
            image = image.resize(target, Image.Resampling.LANCZOS)
        return image


class SessionCaptureEngine:
    """Callable capture adapter compatible with CaptureService."""

    def __init__(
        self,
        repository: SessionRepository,
        session: RecordingSession,
        options: SessionCaptureOptions | None = None,
        privacy: PrivacyGuard | None = None,
        backend: MSSCaptureBackend | None = None,
        ocr: OCRProvider | None = None,
        on_skip=None,
    ) -> None:
        self.repository = repository
        self.session = session
        self.options = options or SessionCaptureOptions()
        self.privacy = privacy or PrivacyGuard()
        self.backend = backend or MSSCaptureBackend()
        if ocr is not None:
            self.ocr = ocr
        elif self.privacy.rules.ocr_enabled:
            from .intelligence import TesseractOCR

            self.ocr = TesseractOCR()
        else:
            self.ocr = NullOCR()
        self.on_skip = on_skip
        self._session_date = dt.date.today()

    def _rollover_if_needed(self) -> None:
        today = dt.date.today()
        if (
            not self.options.daily_rollover
            or self.options.continue_across_midnight
            or today == self._session_date
        ):
            return
        previous = self.session
        self.repository.set_session_status(previous.id, "completed")
        self.session = self.repository.create_session(
            root=previous.root_path.parent,
            name=today.isoformat(),
            mode="daily",
            settings={"rolled_over_from": previous.id},
        )
        self._session_date = today

    def _save_image(self, image: Image.Image) -> Path:
        extension = self.options.image_format.casefold().replace("jpeg", "jpg")
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        final = self.session.frames_path / f"frame_{timestamp}_{uuid.uuid4().hex[:8]}.{extension}"
        temporary = final.with_name(f".{final.name}.{uuid.uuid4().hex}.tmp")
        save_format = "JPEG" if extension == "jpg" else extension.upper()
        save_options = {}
        if save_format in {"JPEG", "WEBP"}:
            save_options["quality"] = self.options.quality
        if save_format == "JPEG" and image.mode != "RGB":
            image = image.convert("RGB")
        try:
            image.save(temporary, format=save_format, **save_options)
            os.replace(temporary, final)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return final

    def __call__(
        self,
        interval: int,
        folder: str,
        stop_event: Event | None = None,
        pause_event: Event | None = None,
        on_capture=None,
    ) -> None:
        del folder
        if interval <= 0:
            raise ValueError("interval must be greater than zero")
        self.options.validate()

        while stop_event is None or not stop_event.is_set():
            if pause_event is not None:
                pause_event.wait()
                if stop_event is not None and stop_event.is_set():
                    break

            allowed, reason, window = self.privacy.should_capture()
            if not allowed:
                if self.on_skip is not None:
                    self.on_skip(reason)
            else:
                self._rollover_if_needed()
                image = self.backend.capture(self.options, window)
                path = self._save_image(image)
                ocr_text = (
                    self.ocr.extract_text(path)
                    if self.privacy.rules.ocr_enabled
                    else ""
                )
                frame = self.repository.add_frame(
                    self.session.id,
                    path,
                    window_title=(
                        window.title
                        if self.privacy.rules.collect_window_metadata
                        else ""
                    ),
                    app_name=(
                        window.process_name
                        if self.privacy.rules.collect_window_metadata
                        else ""
                    ),
                    ocr_text=ocr_text,
                )
                if frame.duplicate_of and self.options.auto_exclude_duplicates:
                    self.repository.set_frames_excluded([frame.id], True)
                if on_capture is not None:
                    on_capture(path)

            if stop_event is None:
                time.sleep(interval)
            elif stop_event.wait(interval):
                break
