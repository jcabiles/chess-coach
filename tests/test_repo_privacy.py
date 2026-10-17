"""Guard against committing private bot portraits or local bot names.

Portraits belong in the gitignored data/avatars/ and local names in the gitignored
data/profiles.local.json. The name check runs only where that local file exists.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".avif"}


def _tracked_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [f for f in out.decode().split("\0") if f]


def test_tracked_images_live_only_in_docs():
    stray = [
        f
        for f in _tracked_files()
        if Path(f).suffix.lower() in IMAGE_SUFFIXES and not f.startswith("docs/")
    ]
    assert stray == [], f"images outside docs/ are tracked: {stray}"


def test_local_profile_names_and_photos_not_tracked():
    local = ROOT / "data" / "profiles.local.json"
    if not local.is_file():
        pytest.skip("no data/profiles.local.json on this machine")
    from app import personas

    committed = {p.name for p in personas._DEFAULT_PERSONAS}
    secrets = set()
    for fields in json.loads(local.read_text(encoding="utf-8")).values():
        if isinstance(fields, dict):
            secrets.update(
                v
                for k, v in fields.items()
                if k in ("name", "photo") and isinstance(v, str)
            )
    secrets -= committed
    if not secrets:
        pytest.skip("local profiles add no new names or photos")
    pattern = re.compile(
        r"(?<![\w-])(" + "|".join(map(re.escape, sorted(secrets))) + r")(?![\w-])"
    )
    hits = []
    for f in _tracked_files():
        path = ROOT / f
        if path.suffix.lower() in IMAGE_SUFFIXES or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits += [f"{f}: {m}" for m in sorted(set(pattern.findall(text)))]
    assert hits == [], f"local bot names/photos found in tracked files: {hits}"
