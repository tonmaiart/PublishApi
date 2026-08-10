"""Versioned publish-folder creation — the part of the old
UkoreMaya/core/Logic.py 'share'/'publish' path-swap convention worth
keeping (the vNNN scanning/creation logic), rewritten to take an explicit,
already-resolved root instead of parsing it back out of a scene file path.
See repo_paths.get_publish_root() for how that root is resolved."""

from __future__ import annotations

import os
import re

_VERSION_PATTERN = re.compile(r"^v(\d{3})$")


def make_sure_folder_exist(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path)


def get_new_version(base_dir: str) -> int:
    """The next available version number (e.g. 2 for 'v002') given a
    directory whose immediate subfolders may include existing 'vNNN'
    folders. Returns 1 if base_dir doesn't exist yet or has none."""
    if not os.path.isdir(base_dir):
        return 1

    max_version = 0
    for entry in os.listdir(base_dir):
        full_path = os.path.join(base_dir, entry)
        if os.path.isdir(full_path):
            match = _VERSION_PATTERN.match(entry)
            if match:
                max_version = max(max_version, int(match.group(1)))
    return max_version + 1


def get_version_directory(publish_root: str, subfolder: str, version: int | None = None):
    """Creates (if needed) and returns (version_dir, version_number) for:

        <publish_root>/<subfolder>/vNNN/

    `publish_root` is always `repo_paths.get_publish_root(tool_id)`'s
    result, never something else — as of 2026-07-19 that result already
    has the studio-chosen CustomPath's own relative path baked in (see
    that function), so there's no separate "custom path" segment to join
    here anymore (there used to be, back when the artist typed it into a
    Publisher plugin's own free-text field). `subfolder` is the
    ticket/department subfolder (e.g. "Proxy", "Hi"). `version=None` means
    "use the next available version"; pass an explicit int to
    target/overwrite a specific one instead."""
    base_dir = os.path.join(publish_root, subfolder)
    make_sure_folder_exist(base_dir)

    if version is None:
        version = get_new_version(base_dir)

    version_dir = os.path.join(base_dir, "v{:03d}".format(version))
    make_sure_folder_exist(version_dir)
    return version_dir, version
