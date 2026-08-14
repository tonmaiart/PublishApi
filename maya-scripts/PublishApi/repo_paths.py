"""Publish-destination resolution — single source of truth for Maya-side tools."""

from __future__ import annotations

import os
from pathlib import Path


def find_cache_dir() -> Path:
    """Where cache/ (local_config.json, github_token.json,
    plugin_local_config/) actually lives — per-machine, not necessarily an
    ancestor of this plugin's own location (cache/plugins/ is deliberately
    allowed to live outside the app root — see app/launcher.py's
    UKOREHUB_CACHE_DIR export). Maya inherits UKOREHUB_CACHE_DIR from the
    launching UkoreHub process's env; the Documents fallback matches
    app/launcher.py's own USER_DATA_DIR default, only used for a mayapy
    session started without that env var (e.g. launched outside UkoreHub's
    own Maya-launch flow)."""
    env_cache = os.environ.get("UKOREHUB_CACHE_DIR")
    if env_cache:
        return Path(env_cache)
    return Path.home() / "Documents" / "UkoreHub" / "cache"


def find_data_dir() -> Path:
    """Where data/ (the R2 cloud-synced JSON registry: projects.json,
    projects/<id>.json, plugins/core/*.json) actually lives — moved outside
    the app root on 2026-08-14 (see app/launcher.py's UKOREHUB_DATA_DIR
    export), same treatment find_cache_dir() above already had. Maya
    inherits UKOREHUB_DATA_DIR the same way; same Documents fallback
    convention."""
    env_data = os.environ.get("UKOREHUB_DATA_DIR")
    if env_data:
        return Path(env_data)
    return Path.home() / "Documents" / "UkoreHub" / "data"


def _open_store():
    """MetadataStore straight off disk (Maya's Python has no PluginAPI
    instance to go through) — same construction UkoreBrowser.core.repo_context
    uses, so both read through the one real Project/Repo registry format
    (data/projects.json) instead of guessing at its on-disk layout."""
    from core.storage.metadata_store import MetadataStore

    return MetadataStore(find_data_dir() / "projects.json")


def get_active_repo():
    """(project, repo, repo_path) สำหรับ Active Repo ปัจจุบัน"""
    from core.exceptions import NotFoundError
    from core.storage.config_store import LocalConfigStore

    local_config = LocalConfigStore(find_cache_dir() / "local_config.json")
    project_id = local_config.active_project_id
    repo_id = local_config.active_repo_id
    workspace_root = local_config.workspace_root

    if not (workspace_root and project_id and repo_id):
        return None, None, None

    store = _open_store()
    try:
        project = store.get_project(project_id)
        repo = store.get_repo(project_id, repo_id)
    except NotFoundError:
        return None, None, None

    repo_path = Path(workspace_root) / repo.local_path
    return project, repo, repo_path


def get_pipeline_refs() -> list[dict]:
    _, repo, _ = get_active_repo()
    if repo is None:
        return []
    return repo.plugin_data.get("project_editor", {}).get("pipeline_inputs", [])


def resolve_ref(ref: dict):
    from core.exceptions import NotFoundError
    from core.storage.config_store import LocalConfigStore

    local_config = LocalConfigStore(find_cache_dir() / "local_config.json")
    project_id = ref.get("project_id")
    repo_id = ref.get("repo_id")

    if not (local_config.workspace_root and project_id and repo_id):
        return None

    store = _open_store()
    try:
        project = store.get_project(project_id)
        repo = store.get_repo(project_id, repo_id)
    except NotFoundError:
        return None

    repo_path = Path(local_config.workspace_root) / repo.local_path
    return project, repo, repo_path


def get_custom_paths(project_id: str, repo_id: str) -> list[dict]:
    from core.exceptions import NotFoundError

    store = _open_store()
    try:
        repo = store.get_repo(project_id, repo_id)
    except NotFoundError:
        return []

    return repo.plugin_data.get("project_editor", {}).get("custom_paths", [])


def get_custom_path(project_id: str, repo_id: str, custom_path_id: str | None) -> dict | None:
    if not custom_path_id:
        return None
    for custom_path in get_custom_paths(project_id, repo_id):
        if custom_path.get("id") == custom_path_id:
            return custom_path
    return None
