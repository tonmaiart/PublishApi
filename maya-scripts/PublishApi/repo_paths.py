"""Publish-destination resolution — always UkoreHub's own active-repo
pipeline metadata (Project Editor's declared pipeline connections), never a
filesystem-path convention like the old '.../share/...' -> '.../publish/...'
string swap ModelPublisher/RigPublisher/AnimationPublisher used to each
carry their own copy of. This is the single source of truth all three of
those plugins resolve a publish root through.

As of 2026-07-19, Project Editor only has ONE kind of pipeline connection
("Connect Pipeline Input Path...", stored under a repo's own
"pipeline_inputs" entry) — there's no separate "pipeline outputs" concept
to distinguish anymore (see plugins/core/project_editor/README.md for
why). Functions/parameters here still talk about "output" from a
Publisher plugin's own point of view (the destination it publishes into),
since that's still what tickets.py's get_publish_root_for_ticket()
resolves through these helpers — it's just reading the same unified
"pipeline_inputs" list Project Editor now stores everything in, not a
distinct "pipeline_outputs" one."""

from __future__ import annotations

from pathlib import Path


def find_ukorehub_root() -> Path:
    """Locate the UkoreHub install root from this file's own position on
    disk. This file lives at
    plugins/repo_internal/PublishApi/maya-scripts/PublishApi/repo_paths.py — five
    parents up is the UkoreHub repo root. Works without any IPC because
    this tool's own files are physically inside the UkoreHub install."""
    return Path(__file__).resolve().parents[5]


def get_active_repo():
    """(project, repo, repo_path) for whichever repo is currently active in
    UkoreHub, or (None, None, None) if there isn't one (no workspace
    configured, no active repo selected, or the repo/project record no
    longer exists). Constructs its own stores straight off disk — Maya's
    Python has no PluginAPI instance to call plugin_config_store()/
    api.metadata through."""
    root = find_ukorehub_root()
    from core.storage.config_store import LocalConfigStore
    from core.storage.metadata_store import MetadataStore

    local_config = LocalConfigStore(root / "cache" / "local_config.json")
    project_id = local_config.active_project_id
    repo_id = local_config.active_repo_id
    if not (local_config.workspace_root and project_id and repo_id):
        return None, None, None

    from core.exceptions import NotFoundError

    store = MetadataStore(root / "data" / "projects.json")
    try:
        project = store.get_project(project_id)
        repo = store.get_repo(project_id, repo_id)
    except NotFoundError:
        return None, None, None

    repo_path = Path(local_config.workspace_root) / repo.local_path
    return project, repo, repo_path


def get_pipeline_refs() -> list[dict]:
    """Every {"project_id", "repo_id", "custom_path_id"} pipeline
    connection the active repo has made via "Connect Pipeline Input
    Path..." in Project Editor, read off the active Repo's own
    plugin_data["project_editor"] (core/models.py's Repo, populated by
    get_active_repo() above). Returns [] if there's no
    active repo."""
    _, repo, _ = get_active_repo()
    if repo is None:
        return []
    return repo.plugin_data.get("project_editor", {}).get("pipeline_inputs", [])


def resolve_ref(ref: dict):
    """Resolves a {"project_id", "repo_id", ...} pipeline ref (as returned
    by get_pipeline_refs) to (project, repo, repo_path), or None if the
    project/repo record no longer exists. `repo_path` is not guaranteed to
    exist on disk (the repo may not be cloned locally yet) — callers
    should check `repo_path.is_dir()` themselves if that matters."""
    root = find_ukorehub_root()
    from core.exceptions import NotFoundError
    from core.storage.config_store import LocalConfigStore
    from core.storage.metadata_store import MetadataStore

    local_config = LocalConfigStore(root / "cache" / "local_config.json")
    store = MetadataStore(root / "data" / "projects.json")
    try:
        project = store.get_project(ref["project_id"])
        repo = store.get_repo(ref["project_id"], ref["repo_id"])
    except NotFoundError:
        return None
    repo_path = Path(local_config.workspace_root) / repo.local_path
    return project, repo, repo_path


def get_custom_paths(project_id: str, repo_id: str) -> list[dict]:
    """Every CustomPath dict ({"id", "label", "path"}) the given repo has
    declared for itself (see plugins/core/project_editor's
    custom_paths_settings_page.py) — read off that repo's own
    plugin_data["project_editor"] (core/models.py's Repo), same field
    get_pipeline_refs() uses."""
    root = find_ukorehub_root()
    from core.exceptions import NotFoundError
    from core.storage.metadata_store import MetadataStore

    store = MetadataStore(root / "data" / "projects.json")
    try:
        repo = store.get_repo(project_id, repo_id)
    except NotFoundError:
        return []
    return repo.plugin_data.get("project_editor", {}).get("custom_paths", [])


def get_custom_path(project_id: str, repo_id: str, custom_path_id: str | None) -> dict | None:
    """Looks up one of `repo_id`'s declared CustomPath entries by id —
    None if custom_path_id is falsy or no longer exists (e.g. it was
    removed after some pipeline ref was already pointed at it, or after a
    tool's Repo Studio Setting already chose it)."""
    if not custom_path_id:
        return None
    for custom_path in get_custom_paths(project_id, repo_id):
        if custom_path["id"] == custom_path_id:
            return custom_path
    return None


# Note: this file used to also have get_chosen_output_ref(tool_id) and
# get_publish_root(tool_id) — a single Publish Path chosen per tool per
# repo, read from a UkoreHub-side Repo Studio Setting tab. Removed
# 2026-08-03 when ModelPublisher/RigPublisher/AnimationPublisher moved to
# user-managed per-ticket Publish Paths entirely configured in Maya — see
# tickets.py's get_publish_root_for_ticket(tool_id, ticket), which
# resolves a specific ticket's own stored ref through the same
# resolve_ref()/get_custom_path() helpers below instead of one shared
# per-repo choice.
