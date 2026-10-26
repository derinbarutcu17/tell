"""Application-local paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_directory() -> Path:
    override = os.environ.get("STORY_SCOUT_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "story-scout"
    elif os.environ.get("XDG_DATA_HOME"):
        path = Path(os.environ["XDG_DATA_HOME"]).expanduser() / "story-scout"
    else:
        path = Path.home() / ".local" / "share" / "story-scout"
    was_missing = not path.exists()
    path.mkdir(parents=True, exist_ok=True)
    if was_missing:
        path.chmod(0o700)
    return path


def database_path() -> Path:
    return data_directory() / "story-scout.sqlite"
