"""Publish-destination resolution — single source of truth for Maya-side tools."""

from __future__ import annotations

import json
from pathlib import Path


def find_ukorehub_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _load_project_data(root: Path, project_id: str) -> dict | None:
    """Helper อ่าน Project Blob ย่อยตาม Schema v2"""
    blob_path = root / "data" / "projects" / f"{project_id}.json"
    if not blob_path.exists():
        return None
    try:
        with open(blob_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as err:
        print(f"[PublishApi] Failed to load project blob {project_id}: {err}")
        return None


def get_active_repo():
    """(project, repo, repo_path) สำหรับ Active Repo ปัจจุบัน"""
    root = find_ukorehub_root()
    from core.storage.config_store import LocalConfigStore

    local_config = LocalConfigStore(root / "cache" / "local_config.json")
    project_id = local_config.active_project_id
    repo_id = local_config.active_repo_id
    workspace_root = local_config.workspace_root

    if not (workspace_root and project_id and repo_id):
        return None, None, None

    proj_dict = _load_project_data(root, project_id)
    if not proj_dict:
        return None, None, None

    from core.models import Project
    project = Project.from_dict(proj_dict)
    repo = next((r for r in project.repos if r.id == repo_id), None)

    if repo is None:
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
    from core.storage.config_store import LocalConfigStore

    local_config = LocalConfigStore(root / "cache" / "local_config.json")
    project_id = ref.get("project_id")
    repo_id = ref.get("repo_id")

    if not (local_config.workspace_root and project_id and repo_id):
        return None

    proj_dict = _load_project_data(root, project_id)
    if not proj_dict:
        return None

    from core.models import Project
    project = Project.from_dict(proj_dict)
    repo = next((r for r in project.repos if r.id == repo_id), None)

    if repo is None:
        return None

    repo_path = Path(local_config.workspace_root) / repo.local_path
    return project, repo, repo_path


def get_custom_paths(project_id: str, repo_id: str) -> list[dict]:
    root = find_ukorehub_root()
    proj_dict = _load_project_data(root, project_id)
    if not proj_dict:
        return []

    from core.models import Project
    project = Project.from_dict(proj_dict)
    repo = next((r for r in project.repos if r.id == repo_id), None)

    if repo is None:
        return []

    return repo.plugin_data.get("project_editor", {}).get("custom_paths", [])


def get_custom_path(project_id: str, repo_id: str, custom_path_id: str | None) -> dict | None:
    if not custom_path_id:
        return None
    for custom_path in get_custom_paths(project_id, repo_id):
        if custom_path.get("id") == custom_path_id:
            return custom_path
    return None