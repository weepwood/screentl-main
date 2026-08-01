"""Command-line management for local recording sessions."""

from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

from screentl.capture_engine import SessionCaptureEngine, SessionCaptureOptions
from screentl.events import EventBus
from screentl.intelligence import LocalIntelligenceService
from screentl.journal_repository import JournalRepository
from screentl.models import CaptureConfig, TaskState
from screentl.privacy import PrivacyGuard, PrivacyRules
from screentl.renderer import FFmpegSessionRenderer, RenderCancelled, RenderOptions
from screentl.services import CaptureService
from screentl.settings import SettingsRepository, default_data_root
from screentl.timeline import TimelineService


def repository() -> JournalRepository:
    return JournalRepository(SettingsRepository.default_path().parent / "sessions.db")


def print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def require_session(repo: JournalRepository, session_id: str | None):
    session = repo.get_session(session_id) if session_id else repo.latest_session()
    if session is None:
        raise SystemExit("没有可用会话，请先执行 journal.py create <名称>")
    return session


def command_create(args) -> int:
    session = repository().create_session(
        Path(args.root),
        args.name,
        mode=args.mode,
    )
    print_json({"id": session.id, "name": session.name, "path": session.root_path})
    return 0


def command_list(args) -> int:
    sessions = repository().list_sessions(args.limit)
    print_json(
        [
            {
                "id": session.id,
                "name": session.name,
                "status": session.status,
                "started_at": session.started_at,
                "path": session.root_path,
            }
            for session in sessions
        ]
    )
    return 0


def command_status(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    print_json(repo.session_summary(session.id))
    return 0


def command_end(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    repo.set_session_status(session.id, "completed")
    print(f"会话已结束：{session.name}")
    return 0


def command_capture(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    region = tuple(args.region) if args.region else None
    options = SessionCaptureOptions(
        monitor=args.monitor,
        region=region,
        active_window_only=args.active_window,
        image_format=args.format,
        quality=args.quality,
        scale=args.scale,
        auto_exclude_duplicates=not args.keep_duplicates,
    )
    rules = PrivacyRules(
        excluded_apps=args.exclude_app,
        excluded_title_keywords=args.exclude_title,
        idle_pause_seconds=args.idle_pause,
        pause_when_locked=not args.capture_locked,
        pause_on_battery=args.pause_on_battery,
        collect_window_metadata=args.window_metadata,
    )
    engine = SessionCaptureEngine(repo, session, options, PrivacyGuard(rules))
    events = EventBus()
    service = CaptureService(events, capture_func=engine)
    service.start(CaptureConfig(session.frames_path, args.interval))
    print(f"开始记录会话 {session.name}，按 Ctrl+C 停止。")
    try:
        while service.is_running:
            service.join(0.25)
            for event in events.drain(100):
                if event.message:
                    print(event.message)
                elif event.data:
                    print(event.data)
    except KeyboardInterrupt:
        service.stop()
    finally:
        service.join()
        repo.set_session_status(session.id, "paused")
    return 1 if service.state is TaskState.FAILED else 0


def render_options(args) -> RenderOptions:
    resolution = tuple(args.resolution) if args.resolution else None
    audio_path = Path(args.audio) if args.audio else None
    audio_folder = Path(args.audio_folder) if args.audio_folder else None
    return RenderOptions(
        output_format=args.format,
        codec=args.codec,
        bitrate=args.bitrate,
        resolution=resolution,
        audio_mode=args.audio_mode,
        audio_path=audio_path,
        audio_folder=audio_folder,
        audio_volume=args.volume,
        audio_fade_seconds=args.fade,
        fps=args.fps,
        include_excluded=args.include_excluded,
        split_by_hour=args.split_by_hour,
    )


def command_render(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    renderer = FFmpegSessionRenderer(repo)
    cancel_event = threading.Event()
    try:
        outputs = renderer.render(
            session.id,
            render_options(args),
            cancel_event=cancel_event,
            on_progress=lambda value: print(f"\r进度 {value:.0%}", end="", flush=True),
        )
    except KeyboardInterrupt:
        cancel_event.set()
        print("\n正在取消…")
        return 1
    except RenderCancelled:
        print("\n已取消")
        return 1
    print()
    print_json([str(path) for path in outputs])
    return 0


def command_timeline(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    page = TimelineService(repo).page(session.id, args.offset, args.limit)
    print_json(
        {
            "offset": page.offset,
            "limit": page.limit,
            "total": page.total,
            "groups": [
                {
                    "hour": group.hour,
                    "frames": [
                        {
                            "id": frame.id,
                            "sequence": frame.sequence,
                            "time": frame.captured_at,
                            "path": frame.path,
                            "excluded": frame.excluded,
                            "duplicate_of": frame.duplicate_of,
                            "duration": frame.duration,
                        }
                        for frame in group.frames
                    ],
                }
                for group in page.groups
            ],
        }
    )
    return 0


def command_exclude(args) -> int:
    changed = repository().set_frames_excluded(args.frames, not args.keep)
    print(f"已更新 {changed} 张截图")
    return 0


def command_delete(args) -> int:
    changed = repository().delete_frames(args.frames, delete_files=not args.keep_files)
    print(f"已删除 {changed} 张截图")
    return 0


def command_duration(args) -> int:
    repo = repository()
    for frame_id in args.frames:
        repo.set_frame_duration(frame_id, args.seconds)
    return 0


def command_mask(args) -> int:
    repo = repository()
    frame = repo.get_frame(args.frame)
    if frame is None:
        raise SystemExit(f"截图不存在：{args.frame}")
    repo.set_frame_masks(args.frame, [*frame.masks, tuple(args.rect)])
    return 0


def command_collapse(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    print(f"已排除 {repo.collapse_duplicates(session.id)} 张重复截图")
    return 0


def command_contact_sheet(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    output = TimelineService(repo).build_contact_sheet(
        session.id,
        Path(args.output),
        columns=args.columns,
    )
    print(output)
    return 0


def command_preview(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    print(TimelineService(repo).build_html_preview(session.id, Path(args.output)))
    return 0


def command_search(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    results = LocalIntelligenceService(repo).search(session.id, args.query, args.limit)
    print_json(
        [
            {
                "frame_id": result.frame.id,
                "time": result.frame.captured_at,
                "field": result.matched_field,
                "excerpt": result.excerpt,
            }
            for result in results
        ]
    )
    return 0


def command_summary(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    service = LocalIntelligenceService(repo)
    if args.output:
        print(service.export_summary(session.id, Path(args.output)))
    else:
        print_json(service.build_summary(session.id))
    return 0


def command_export(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    print(repo.export_session_manifest(session.id, Path(args.output)))
    return 0


def command_archive(args) -> int:
    repo = repository()
    session = require_session(repo, args.session)
    print(repo.archive_session(session.id, Path(args.destination)))
    return 0


def command_cleanup(args) -> int:
    removed = repository().cleanup(args.days, args.max_sessions)
    print_json([str(path) for path in removed])
    return 0


def add_session_argument(parser) -> None:
    parser.add_argument("--session", help="会话 ID，省略时使用最近会话")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Screenshot Time-lapse 会话管理")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="新建会话")
    create.add_argument("name")
    create.add_argument("--root", default=str(default_data_root() / "sessions"))
    create.add_argument("--mode", choices=["named", "daily", "fixed"], default="named")
    create.set_defaults(handler=command_create)

    listing = sub.add_parser("list", help="列出会话")
    listing.add_argument("--limit", type=int, default=100)
    listing.set_defaults(handler=command_list)

    for name, handler in [("status", command_status), ("end", command_end)]:
        command = sub.add_parser(name)
        add_session_argument(command)
        command.set_defaults(handler=handler)

    capture = sub.add_parser("capture", help="记录当前会话")
    add_session_argument(capture)
    capture.add_argument("--interval", type=int, default=30)
    capture.add_argument("--monitor", type=int, default=1)
    capture.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    capture.add_argument("--active-window", action="store_true")
    capture.add_argument("--format", choices=["png", "jpeg", "webp"], default="png")
    capture.add_argument("--quality", type=int, default=90)
    capture.add_argument("--scale", type=float, default=1.0)
    capture.add_argument("--keep-duplicates", action="store_true")
    capture.add_argument("--exclude-app", action="append", default=[])
    capture.add_argument("--exclude-title", action="append", default=[])
    capture.add_argument("--idle-pause", type=int, default=0)
    capture.add_argument("--capture-locked", action="store_true")
    capture.add_argument("--pause-on-battery", action="store_true")
    capture.add_argument("--window-metadata", action="store_true")
    capture.set_defaults(handler=command_capture)

    render = sub.add_parser("render", help="专业视频输出")
    add_session_argument(render)
    render.add_argument("--format", choices=["mp4", "gif"], default="mp4")
    render.add_argument(
        "--codec",
        choices=["h264", "h265", "vp9", "nvenc", "qsv", "amf"],
        default="h264",
    )
    render.add_argument("--bitrate", default="4M")
    render.add_argument("--resolution", type=int, nargs=2, metavar=("W", "H"))
    render.add_argument(
        "--audio-mode",
        choices=["none", "fixed", "random", "loop", "sequence"],
        default="none",
    )
    render.add_argument("--audio")
    render.add_argument("--audio-folder")
    render.add_argument("--volume", type=float, default=0.2)
    render.add_argument("--fade", type=float, default=1.0)
    render.add_argument("--fps", type=int, default=25)
    render.add_argument("--include-excluded", action="store_true")
    render.add_argument("--split-by-hour", action="store_true")
    render.set_defaults(handler=command_render)

    timeline = sub.add_parser("timeline")
    add_session_argument(timeline)
    timeline.add_argument("--offset", type=int, default=0)
    timeline.add_argument("--limit", type=int, default=200)
    timeline.set_defaults(handler=command_timeline)

    exclude = sub.add_parser("exclude")
    exclude.add_argument("frames", type=int, nargs="+")
    exclude.add_argument("--keep", action="store_true")
    exclude.set_defaults(handler=command_exclude)

    delete = sub.add_parser("delete")
    delete.add_argument("frames", type=int, nargs="+")
    delete.add_argument("--keep-files", action="store_true")
    delete.set_defaults(handler=command_delete)

    duration = sub.add_parser("duration")
    duration.add_argument("seconds", type=float)
    duration.add_argument("frames", type=int, nargs="+")
    duration.set_defaults(handler=command_duration)

    mask = sub.add_parser("mask")
    mask.add_argument("frame", type=int)
    mask.add_argument("rect", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    mask.set_defaults(handler=command_mask)

    for name, handler in [("collapse", command_collapse), ("search", command_search)]:
        command = sub.add_parser(name)
        add_session_argument(command)
        if name == "search":
            command.add_argument("query")
            command.add_argument("--limit", type=int, default=100)
        command.set_defaults(handler=handler)

    contact = sub.add_parser("contact-sheet")
    add_session_argument(contact)
    contact.add_argument("output")
    contact.add_argument("--columns", type=int, default=4)
    contact.set_defaults(handler=command_contact_sheet)

    preview = sub.add_parser("preview")
    add_session_argument(preview)
    preview.add_argument("output")
    preview.set_defaults(handler=command_preview)

    summary = sub.add_parser("summary")
    add_session_argument(summary)
    summary.add_argument("--output")
    summary.set_defaults(handler=command_summary)

    export = sub.add_parser("export")
    add_session_argument(export)
    export.add_argument("output")
    export.set_defaults(handler=command_export)

    archive = sub.add_parser("archive")
    add_session_argument(archive)
    archive.add_argument("destination")
    archive.set_defaults(handler=command_archive)

    cleanup = sub.add_parser("cleanup")
    cleanup.add_argument("--days", type=int)
    cleanup.add_argument("--max-sessions", type=int)
    cleanup.set_defaults(handler=command_cleanup)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    started = time.monotonic()
    try:
        return int(args.handler(args))
    finally:
        elapsed = time.monotonic() - started
        if elapsed > 1:
            print(f"耗时：{elapsed:.1f} 秒")


if __name__ == "__main__":
    raise SystemExit(main())
