"""Optional local OCR, search and work-session summaries."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .sessions import SessionRepository, TimelineFrame


@dataclass(frozen=True)
class SearchResult:
    frame: TimelineFrame
    matched_field: str
    excerpt: str


class TesseractOCR:
    """Use a user-installed Tesseract executable; no network calls are made."""

    def __init__(self, executable: str = "tesseract", language: str = "eng") -> None:
        resolved = shutil.which(executable) or executable
        self.executable = resolved
        self.language = language

    def extract_text(self, image: Path) -> str:
        process = subprocess.run(
            [self.executable, str(image), "stdout", "-l", self.language],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=(0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0),
        )
        if process.returncode != 0:
            message = process.stderr.strip() or "local OCR failed"
            raise RuntimeError(message)
        return process.stdout.strip()


class LocalIntelligenceService:
    def __init__(self, repository: SessionRepository) -> None:
        self.repository = repository

    def search(self, session_id: str, query: str, limit: int = 100) -> list[SearchResult]:
        needle = query.strip().casefold()
        if not needle:
            return []
        results: list[SearchResult] = []
        frames = self.repository.list_frames(session_id, limit=100000)
        for frame in frames:
            candidates = (
                ("ocr", frame.ocr_text),
                ("application", frame.app_name),
                ("window", frame.window_title),
                ("filename", frame.path.name),
            )
            for field, value in candidates:
                if needle in value.casefold():
                    position = value.casefold().find(needle)
                    start = max(0, position - 40)
                    end = min(len(value), position + len(query) + 80)
                    results.append(SearchResult(frame, field, value[start:end]))
                    break
            if len(results) >= max(1, limit):
                break
        return results

    def cluster_by_application(self, session_id: str) -> dict[str, list[TimelineFrame]]:
        clusters: dict[str, list[TimelineFrame]] = {}
        for frame in self.repository.list_frames(session_id, limit=100000):
            key = frame.app_name.strip() or "Unknown"
            clusters.setdefault(key, []).append(frame)
        return clusters

    def stagnation_periods(
        self,
        session_id: str,
        minimum_frames: int = 3,
    ) -> list[dict[str, object]]:
        frames = self.repository.list_frames(session_id, limit=100000)
        periods: list[dict[str, object]] = []
        run: list[TimelineFrame] = []
        previous_hash = ""
        for frame in frames:
            if frame.dhash == previous_hash and run:
                run.append(frame)
            else:
                if len(run) >= minimum_frames:
                    periods.append(self._period(run))
                run = [frame]
                previous_hash = frame.dhash
        if len(run) >= minimum_frames:
            periods.append(self._period(run))
        return periods

    @staticmethod
    def _period(frames: list[TimelineFrame]) -> dict[str, object]:
        return {
            "start": frames[0].captured_at,
            "end": frames[-1].captured_at,
            "frames": len(frames),
            "application": frames[0].app_name,
            "window": frames[0].window_title,
        }

    def build_summary(self, session_id: str) -> dict[str, object]:
        session = self.repository.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session: {session_id}")
        frames = self.repository.list_frames(session_id, limit=100000)
        applications = Counter(frame.app_name for frame in frames if frame.app_name)
        hours = Counter(frame.captured_at[:13] for frame in frames)
        base = self.repository.session_summary(session_id)
        return {
            **base,
            "name": session.name,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "top_applications": applications.most_common(10),
            "frames_by_hour": sorted(hours.items()),
            "stagnation_periods": self.stagnation_periods(session_id),
            "privacy": {
                "ocr_text_frames": sum(bool(frame.ocr_text) for frame in frames),
                "window_metadata_frames": sum(
                    bool(frame.app_name or frame.window_title) for frame in frames
                ),
                "processing": "local-only",
            },
        }

    def export_summary(self, session_id: str, destination: Path) -> Path:
        summary = self.build_summary(session_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.suffix.casefold() == ".json":
            destination.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return destination

        applications = "\n".join(
            f"- {name}: {count} 帧" for name, count in summary["top_applications"]
        ) or "- 未采集应用信息"
        stagnation = "\n".join(
            f"- {item['start']} ～ {item['end']}：{item['frames']} 帧"
            for item in summary["stagnation_periods"]
        ) or "- 未检测到明显停滞阶段"
        text = f"""# {summary['name']} 会话摘要

- 开始：{summary['started_at']}
- 结束：{summary['ended_at'] or '进行中'}
- 总帧数：{summary['frames']}
- 已排除：{summary['excluded']}
- 重复帧：{summary['duplicates']}
- 预计视频时长：{summary['estimated_video_seconds']:.1f} 秒

## 应用分布

{applications}

## 重复或停滞阶段

{stagnation}

## 隐私说明

本摘要仅基于本地 SQLite 索引生成，不上传截图或元数据。OCR 与窗口元数据默认关闭。
"""
        destination.write_text(text, encoding="utf-8")
        return destination
