"""Publish-destination resolution — single source of truth for Maya-side tools."""

from __future__ import annotations

from pathlib import Path


def find_ukorehub_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _open_store(root: Path):
    """MetadataStore straight off disk (Maya's Python has no PluginAPI
    instance to go through) — same construction UkoreBrowser.core.repo_context
    uses, so both read through the one real Project/Repo registry format
    (data/projects.json) instead of guessing at its on-disk layout."""
    from core.storage.metadata_store import MetadataStore

    return MetadataStore(root / "data" / "projects.json")


def get_active_repo():
    """(project, repo, repo_path) สำหรับ Active Repo ปัจจุบัน"""
    root = find_ukorehub_root()
    from core.exceptions import NotFoundError
    from core.storage.config_store import LocalConfigStore

    local_config = LocalConfigStore(root / "cache" / "local_config.json")
    project_id = local_config.active_project_id
    repo_id = local_config.active_repo_id
    workspace_root = local_config.workspace_root

    if not (workspace_root and project_id and repo_id):
        return None, None, None

    store = _open_store(root)
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
    root = find_ukorehub_root()
    from core.exceptions import NotFoundError
    from core.storage.config_store import LocalConfigStore

    local_config = LocalConfigStore(root / "cache" / "local_config.json")
    project_id = ref.get("project_id")
    repo_id = ref.get("repo_id")

    if not (local_config.workspace_root and project_id and repo_id):
        return None

    store = _open_store(root)
    try:
        project = store.get_project(project_id)
        repo = store.get_repo(project_id, repo_id)
    except NotFoundError:
        return None

    repo_path = Path(local_config.workspace_root) / repo.local_path
    return project, repo, repo_path


def get_custom_paths(project_id: str, repo_id: str) -> list[dict]:
    root = find_ukorehub_root()
    from core.exceptions import NotFoundError

    store = _open_store(root)
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