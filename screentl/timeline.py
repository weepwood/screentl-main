"""Timeline browsing, thumbnails, privacy masks and contact-sheet export."""

from __future__ import annotations

import datetime as dt
import html
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .sessions import SessionRepository, TimelineFrame


@dataclass(frozen=True)
class TimelineGroup:
    hour: str
    frames: tuple[TimelineFrame, ...]


@dataclass(frozen=True)
class TimelinePage:
    offset: int
    limit: int
    total: int
    groups: tuple[TimelineGroup, ...]

    @property
    def has_next(self) -> bool:
        return self.offset + self.limit < self.total


def frame_hour(frame: TimelineFrame) -> str:
    try:
        value = dt.datetime.fromisoformat(frame.captured_at)
        return value.strftime("%Y-%m-%d %H:00")
    except ValueError:
        return frame.captured_at[:13]


def apply_privacy_masks(
    image: Image.Image,
    masks: tuple[tuple[int, int, int, int], ...],
    mode: str = "blur",
) -> Image.Image:
    result = image.convert("RGB")
    for x, y, width, height in masks:
        left = max(0, x)
        top = max(0, y)
        right = min(result.width, left + width)
        bottom = min(result.height, top + height)
        if right <= left or bottom <= top:
            continue
        box = (left, top, right, bottom)
        if mode == "black":
            ImageDraw.Draw(result).rectangle(box, fill="black")
        elif mode == "pixelate":
            region = result.crop(box)
            tiny = region.resize(
                (max(1, region.width // 20), max(1, region.height // 20)),
                Image.Resampling.BILINEAR,
            )
            result.paste(
                tiny.resize(region.size, Image.Resampling.NEAREST),
                box,
            )
        else:
            region = result.crop(box).filter(ImageFilter.GaussianBlur(radius=18))
            result.paste(region, box)
    return result


class TimelineService:
    def __init__(self, repository: SessionRepository) -> None:
        self.repository = repository

    def page(
        self,
        session_id: str,
        offset: int = 0,
        limit: int = 200,
        include_excluded: bool = True,
    ) -> TimelinePage:
        summary = self.repository.session_summary(session_id)
        total = int(summary["frames"])
        frames = self.repository.list_frames(
            session_id,
            offset=offset,
            limit=limit,
            include_excluded=include_excluded,
        )
        grouped: list[TimelineGroup] = []
        current_hour = ""
        bucket: list[TimelineFrame] = []
        for frame in frames:
            hour = frame_hour(frame)
            if bucket and hour != current_hour:
                grouped.append(TimelineGroup(current_hour, tuple(bucket)))
                bucket = []
            current_hour = hour
            bucket.append(frame)
        if bucket:
            grouped.append(TimelineGroup(current_hour, tuple(bucket)))
        return TimelinePage(offset, limit, total, tuple(grouped))

    def estimate_seconds(self, session_id: str, include_excluded: bool = False) -> float:
        frames = self.repository.list_frames(
            session_id,
            limit=100000,
            include_excluded=include_excluded,
        )
        if not include_excluded:
            frames = [frame for frame in frames if not frame.excluded]
        return sum(frame.duration for frame in frames)

    def create_thumbnail(
        self,
        frame: TimelineFrame,
        destination: Path,
        size: tuple[int, int] = (320, 180),
        mask_mode: str = "blur",
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(frame.path) as source:
            image = apply_privacy_masks(source, frame.masks, mask_mode)
            image.thumbnail(size, Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", size, "#111827")
            offset = ((size[0] - image.width) // 2, (size[1] - image.height) // 2)
            canvas.paste(image, offset)
            canvas.save(destination, "JPEG", quality=85, optimize=True)
        return destination

    def ensure_thumbnail(self, session_id: str, frame: TimelineFrame) -> Path:
        session = self.repository.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session: {session_id}")
        destination = session.thumbnails_path / f"{frame.id}_{frame.sha256[:12]}.jpg"
        if not destination.exists():
            self.create_thumbnail(frame, destination)
        return destination

    def build_contact_sheet(
        self,
        session_id: str,
        destination: Path,
        columns: int = 4,
        cell_size: tuple[int, int] = (320, 210),
        include_excluded: bool = False,
    ) -> Path:
        if columns <= 0:
            raise ValueError("columns must be greater than zero")
        frames = self.repository.list_frames(
            session_id,
            limit=100000,
            include_excluded=include_excluded,
        )
        if not include_excluded:
            frames = [frame for frame in frames if not frame.excluded]
        if not frames:
            raise ValueError("session has no frames to export")

        rows = math.ceil(len(frames) / columns)
        sheet = Image.new(
            "RGB",
            (cell_size[0] * columns, cell_size[1] * rows),
            "#f3f4f6",
        )
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.load_default()
        for index, frame in enumerate(frames):
            x = (index % columns) * cell_size[0]
            y = (index // columns) * cell_size[1]
            with Image.open(frame.path) as source:
                image = apply_privacy_masks(source, frame.masks)
                image = ImageOps.contain(
                    image,
                    (cell_size[0] - 12, cell_size[1] - 34),
                    Image.Resampling.LANCZOS,
                )
            offset = (
                x + (cell_size[0] - image.width) // 2,
                y + 6,
            )
            sheet.paste(image, offset)
            label = f"#{frame.sequence}  {frame.captured_at[11:19]}"
            if frame.excluded:
                label += "  [excluded]"
            draw.text((x + 8, y + cell_size[1] - 22), label, fill="#111827", font=font)
        destination.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(destination, "JPEG", quality=88, optimize=True)
        return destination

    def build_html_preview(self, session_id: str, destination: Path) -> Path:
        session = self.repository.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session: {session_id}")
        frames = self.repository.list_frames(session_id, limit=100000)
        cards = []
        for frame in frames:
            thumbnail = self.ensure_thumbnail(session_id, frame)
            relative = thumbnail.relative_to(destination.parent).as_posix()
            status = "excluded" if frame.excluded else "kept"
            cards.append(
                "<article class='frame'>"
                f"<img loading='lazy' src='{html.escape(relative)}' alt='frame {frame.sequence}'>"
                f"<p>#{frame.sequence} · {html.escape(frame.captured_at)} · {status}</p>"
                f"<p>{html.escape(frame.app_name or frame.window_title)}</p>"
                "</article>"
            )
        summary = self.repository.session_summary(session_id)
        document = f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(session.name)} - Timeline</title>
<style>
body{{font-family:system-ui;margin:24px;background:#f8fafc;color:#0f172a}}
header{{position:sticky;top:0;background:#f8fafcee;padding:12px 0;backdrop-filter:blur(8px)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}
.frame{{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:8px}}
.frame img{{width:100%;aspect-ratio:16/9;object-fit:contain;background:#111827;border-radius:8px}}
p{{margin:6px 2px;font-size:13px}}
</style>
<header><h1>{html.escape(session.name)}</h1>
<p>{summary['frames']} 帧 · {summary['duplicates']} 重复 · {summary['excluded']} 已排除 · 预计 {summary['estimated_video_seconds']:.1f} 秒</p></header>
<section class="grid">{''.join(cards)}</section>
</html>"""
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(document, encoding="utf-8")
        return destination
