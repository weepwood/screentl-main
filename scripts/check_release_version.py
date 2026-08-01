"""Ensure a release tag matches the application version."""

from __future__ import annotations

import os

from screentl.version import __version__


def main() -> int:
    tag = os.environ.get("GITHUB_REF_NAME", "").strip()
    expected = f"v{__version__}"
    if tag != expected:
        print(f"Release tag mismatch: expected {expected}, received {tag or '<empty>'}")
        return 1
    print(f"Release tag matches application version: {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
