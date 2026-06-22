"""Single source of truth for Skills Router Python package version."""

import json
import re
from pathlib import Path

__version__ = "0.0.10"


def _auto_update() -> None:
    try:
        pkg_json = Path(__file__).resolve().parent.parent.parent / "skills-router-npx" / "package.json"
        if pkg_json.exists():
            current_version = json.loads(pkg_json.read_text(encoding="utf-8"))["version"]
            global __version__
            if current_version != __version__:
                __version__ = current_version
                file_path = Path(__file__).resolve()
                text = file_path.read_text(encoding="utf-8")
                updated = re.sub(
                    r'^__version__ = "[^"]+"',
                    f'__version__ = "{current_version}"',
                    text,
                    flags=re.MULTILINE,
                )
                file_path.write_text(updated, encoding="utf-8")
    except Exception:
        pass


_auto_update()
