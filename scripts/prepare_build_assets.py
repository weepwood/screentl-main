"""Generate deterministic Windows icon and version resources."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from screentl.version import __version__

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "build-assets"
ICON_PATH = OUTPUT / "ScreenshotTimeLapse.ico"
VERSION_PATH = OUTPUT / "version_info.txt"


def version_tuple() -> tuple[int, int, int, int]:
    parts = [int(part) for part in __version__.split(".")]
    return tuple((parts + [0, 0, 0, 0])[:4])


def create_icon() -> None:
    image = Image.new("RGBA", (256, 256), (37, 99, 235, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 50, 214, 190), radius=20, fill="white")
    draw.rounded_rectangle((62, 72, 194, 100), radius=8, fill=(37, 99, 235))
    draw.rounded_rectangle((62, 118, 165, 146), radius=8, fill=(37, 99, 235))
    draw.rectangle((104, 190, 152, 218), fill="white")
    draw.rounded_rectangle((76, 212, 180, 230), radius=8, fill="white")
    image.save(
        ICON_PATH,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


def create_version_info() -> None:
    major, minor, patch, build = version_tuple()
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build}),
    prodvers=({major}, {minor}, {patch}, {build}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'weepwood'),
         StringStruct('FileDescription', 'Screenshot Time-lapse'),
         StringStruct('FileVersion', '{__version__}'),
         StringStruct('InternalName', 'ScreenshotTimeLapse'),
         StringStruct('LegalCopyright', 'Copyright (c) 2026 weepwood'),
         StringStruct('OriginalFilename', 'ScreenshotTimeLapse.exe'),
         StringStruct('ProductName', 'Screenshot Time-lapse'),
         StringStruct('ProductVersion', '{__version__}')]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    VERSION_PATH.write_text(content, encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    create_icon()
    create_version_info()
    print(f"Generated {ICON_PATH}")
    print(f"Generated {VERSION_PATH}")


if __name__ == "__main__":
    main()
