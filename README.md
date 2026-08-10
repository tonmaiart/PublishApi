# plugins/repo_internal/PublishApi/

Shared Maya-side library — the single source of truth for "where does a
publish go" and "how do I create the next version folder" — consumed by
`MayaPublisher`. Does not
launch Maya; like every other Maya tool plugin here, `plugin.py` itself
exists purely to contribute a `PYTHONPATH` entry to
`plugins/repo_internal/maya_launcher/`'s shared `maya_launcher_env_bridge`
`PluginConfigStore`.

As of 2026-08-03, this is also where MayaPublisher's shared **ticket
management** lives (`tickets.py` + `ticket_manager_dialog.py`, both
Maya-side, under `maya-scripts/PublishApi/`) — the original
`ModelPublisher`/`RigPublisher`/`AnimationPublisher` each used to have
their own UkoreHub-side Repo Studio Setting tab for a single per-repo
Publish Path choice; that's gone now in favor of user-managed **tickets**,
each with its own Publish Path and validation scripts, created/edited
entirely from inside Maya. See "Tickets" below.

Added 2026-07-19, alongside splitting the original `UkorePublisher` plugin
into `ModelPublisher`/`RigPublisher`/`AnimationPublisher` (themselves
merged into one `MayaPublisher` plugin on 2026-08-05 — see
`plugins/repo_internal/MayaPublisher/README.md`) — see
`plugins/repo_internal/maya_launcher/README.md` for the bridge convention this
follows.

**Never gated by `plugins/repo_internal/maya_launcher/`'s per-repo Enable
Plugin gating** — unlike every other tool plugin listed above, this one has no
legitimate reason to ever be disabled per-repo (it's pure infrastructure,
not an artist-facing feature), and `maya_launcher/plugin.py`'s
`open_maya_file` force-includes its bridge contribution regardless of what
a repo's stored tool list says. See that plugin's README's "Per-repo tool
toggle" section for why — this was added after a repo whose stored list
predated this plugin's existence hit `ModuleNotFoundError: No module named
'PublishApi'` inside a consuming Maya tool's own repo-context module.

## Files

- `manifest.json` — plugin id `publish_api`, entry point `plugin.py`.
- `plugin.py` — `register(api)`: contributes `maya-scripts/` **and**
  `api.app_root` to the shared bridge (so `import core.store`/`core.paths`/
  `core.extensibility.config_store` resolve inside Maya's Python).
- `maya-scripts/PublishApi/repo_paths.py`:
  - `find_ukorehub_root()` — locates the UkoreHub install root from this
    file's own position on disk (`parents[5]`).
  - `get_active_repo()` — `(project, repo, repo_path)` for whichever repo
    UkoreHub currently has active, constructing `LocalConfigStore`/
    `MetadataStore` straight off disk (Maya's Python has no `PluginAPI`
    instance to go through).
  - `get_pipeline_refs()` — every `{"project_id", "repo_id",
    "custom_path_id"}` dict the active repo has connected to via "Connect
    Pipeline Input Path..." in Project Editor, read directly from
    `data/plugins/core/project_editor.json`.
  - `resolve_ref(ref)` — a pipeline ref (or any `{"project_id","repo_id"}`
    dict) resolved to `(project, repo, repo_path)`.
  - `get_custom_paths(project_id, repo_id)` / `get_custom_path(project_id,
    repo_id, custom_path_id)` — a repo's own declared `CustomPath` catalog
    (`{"id","label","path"}`, `path` relative to that repo's root — see
    `plugins/core/project_editor`'s `custom_paths_settings_page.py`) and
    a single lookup by id.
  - **Removed 2026-08-03**: `get_chosen_output_ref(tool_id)` and
    `get_publish_root(tool_id)` — the old "one Publish Path per tool per
    repo" resolution. Dead code once all three Publishers moved to
    per-ticket Publish Paths — see `tickets.py`'s
    `get_publish_root_for_ticket(tool_id, ticket)` below, which resolves
    through the same `resolve_ref()`/`get_custom_path()` helpers above,
    just keyed off a specific ticket's own stored choice instead of one
    shared per-repo value.
- `maya-scripts/PublishApi/versioning.py`:
  - `make_sure_folder_exist(path)` — trivial `os.makedirs` wrapper.
  - `get_new_version(base_dir)` — next available `vNNN` integer under a
    directory, by scanning its immediate subfolders.
  - `get_version_directory(publish_root, subfolder, version=None)` —
    creates and returns `(version_dir, version_number)` for
    `<publish_root>/<subfolder>/vNNN/`. `publish_root` is always
    `tickets.get_publish_root_for_ticket(tool_id, ticket)`'s result;
    `subfolder` is the ticket's own `folder_name` (see "Tickets" below).
- `maya-scripts/PublishApi/tickets.py` — user-managed **tickets**, all
  keyed under MayaPublisher's single `tool_id` ("maya_publisher") for
  storage regardless of which mode a repo publishes as (see "Tickets"
  below for the full shape).
- `maya-scripts/PublishApi/ticket_manager_dialog.py` — `TicketManagerDialog`:
  the shared "Manage Tickets..." `QDialog` MayaPublisher's own
  `interface.py` opens (parameterized by `tool_id`/`tool_label`/
  `show_export_type`/`scripts_tool_id`) — create/rename/delete tickets,
  pick each ticket's own Publish Path from the active repo's declared
  pipeline connections (same list `repo_paths.get_pipeline_refs()`
  resolves), and — only when `show_export_type=True` (MayaPublisher's
  Animation mode) — a Playblast/Unreal Export combo box per ticket.
  Two script panes side by side: "Available Scripts" (checkable, checking
  a box calls `tickets.attach_script`/`detach_script` immediately, same
  self-persisting-checkbox convention the Requirements & Plugins tab uses)
  and "Run Order" (added 2026-08-05, just the checked ones in the order
  `run_validation_scripts` will actually call them — "Move Up"/"Move Down"
  call `tickets.move_script`). "Create Script..." (added 2026-08-05) seeds
  a new file from `tickets.create_script`'s template and opens it; "Edit
  Script..." and "Open Script Folder..." both use `os.startfile` (on
  `tickets.validation_scripts_dir(scripts_tool_id)` or a specific file in
  it) to hand off to whatever program is registered for `.py` files on
  this machine — this dialog itself never edits a script's contents.
  `scripts_tool_id` (defaults to `tool_id`) decouples the validation-script
  *folder* lookup from ticket *storage*: MayaPublisher passes the repo's
  configured mode's **old** tool id here (e.g. `"rig_publisher"`) so
  `PublishValidation/rig_publisher/` keeps resolving for an
  already-migrated repo without moving anything — see
  `plugins/repo_internal/MayaPublisher/maya-scripts/MayaPublisher/function.py`'s
  `MODE_TOOL_IDS`. "Save Publish Path" is an explicit button, not
  autosave-on-click (same deliberate-commit reasoning the old, now-removed
  `publish_target_settings_page.py` adopted on the UkoreHub side).

## Tickets

Replaces the old "one Publish Path chosen per tool per repo" model
(a UkoreHub-side Repo Studio Setting tab, one choice, applied to every
publish from that repo) with tickets a studio admin creates/manages
**per repo, entirely from inside Maya** via each Publisher's own "Manage
Tickets..." button:

- Each ticket has its own display `name` and its own on-disk `folder_name`
  — kept separate on purpose, and `folder_name` is immutable after
  creation, so renaming a ticket later never moves or breaks its
  already-published version history.
- Each ticket has its own `publish_target` (a pipeline connection ref,
  same shape the old single per-repo choice used) — different tickets on
  the same repo can publish to entirely different destinations.
- Each ticket has a list of attached **scripts** — `ticket["script_names"]`,
  filenames referencing `.py` files that live in a **fixed** folder, not
  owned per-ticket: `tickets.validation_scripts_dir(tool_id)` =
  `<active repo's own local clone>/PublishValidation/<tool_id>/`. A TD
  writes/commits the actual scripts there entirely outside this tool (a
  text editor, checked into the repo like any other pipeline code, shared
  to the whole team via that repo's own git history) — "Manage Tickets..."
  only lets a studio admin pick which of the scripts already sitting in
  that folder apply to a given ticket, it never authors one. Each script
  defines one `validate() -> bool` function (or, as of 2026-08-05,
  `validate(context) -> bool` — see below); all of a ticket's attached
  scripts must return `True` (or be absent/have no `validate()`) for
  `function.py`'s `publish()` to be reported successful. Modeled after
  `plugins/repo_internal/MayaToolkit/maya-scripts/tmlib/core/QuickData.py`'s
  folder-of-scripts convention (used by the `PythonReader` toolkit,
  formerly "QuickScript") — same `importlib.util.spec_from_file_location`
  + `exec_module` loading mechanism, just calling `validate()` instead of
  `run()` and collecting the bool results instead of discarding them. A
  script name a ticket still references that's since been removed/renamed
  in that folder is a hard failure (not a silent skip) — it means the
  ticket's configuration needs re-checking, not that the check passed.
  **2026-08-05: these scripts are no longer pure checks.** MayaPublisher's
  `function.py` used to export/copy a file automatically once every
  attached script returned `True`; now it doesn't export anything itself
  at all — `run_validation_scripts(tool_id, ticket, context)` optionally
  passes a `context` dict (`version_dir`, `version`, `ticket`, `mode`,
  `tool_id` — inspected via the script's own `validate` signature, so the
  original zero-argument contract still works unchanged) that a script
  can use to actually export/copy whatever it decides belongs in
  `context["version_dir"]`. See
  `plugins/repo_internal/MayaPublisher/README.md`'s "Publish is a scripted
  step" for the full reasoning and the caveat about scripts that do file
  work then a later script fails.
- Tickets on repos configured for MayaPublisher's Animation mode
  additionally carry an `export_type` (`"playblast"` or `"unreal"`) — see
  `plugins/repo_internal/MayaPublisher/README.md`.

Storage: `<active repo's own local clone>/.ukorehub/<tool_id>_tickets.json`,
key `"tickets"`, a flat list — committed to that repo's own git history,
same as the validation scripts themselves (see above), not UkoreHub's own
`data/`. Ticket definitions (publish target, attached scripts) are
team-shared pipeline config every artist on the repo needs, not
per-machine app state. Previously lived in a single shared, cloud-synced
`data/plugins/core/<tool_id>.json` (every studio repo's tickets in one
file, keyed `"<project_id>:<repo_id>"`) — moved out since that file needs
Google Cloud Storage access this Maya process doesn't have (no
`google-cloud-storage` in mayapy's site-packages); see `tickets.py`'s
`_migrate_from_shared_store` for how an existing repo's tickets are
carried forward into its own repo-local file on first access.

**Migration**: the first time a repo's tickets are listed and its own
`.ukorehub/<tool_id>_tickets.json` doesn't exist yet, its entry from the
old shared blob (if any) is carried forward, or — failing that — an
old-style single Publish Path choice (from before 2026-08-03) is
auto-created as a `"Main"` ticket. Nothing gets silently lost by this
change.

## Why this replaces the old `share`/`publish` path-swap convention

Before this plugin existed, `UkorePublisher`'s publish root was derived by
string-swapping `.../share/...` for `.../publish/...` in the current Maya
scene's own file path (`UkoreMaya/core/Logic.py`'s `convert_to_publish_path`,
still present in `plugins/repo_internal/MayaToolkit/` — unrelated tools may still
use it, this plugin just doesn't). That convention had no connection to
UkoreHub's own Project/Repo/pipeline model at all — it only worked because
every studio scene file happened to sit under a folder literally named
`share`. `tickets.get_publish_root_for_ticket(tool_id, ticket)` resolves
the destination from Project Editor's actual declared pipeline
**connection** a specific ticket has chosen (e.g. `RigTeam`'s "Main"
ticket resolves to wherever `RigPublish` — the repo it connected to — is
cloned, further scoped down to whichever `CustomPath` that connection
points at, e.g. `RigPublish/Character`), which is correct regardless of
where the artist's local clone happens to live on disk, and keeps
publishing in sync with whatever the studio has declared in Project
Editor's graph.

## Working on this plugin

Read/edit only files under this folder unless the change is specifically
about how `MayaPublisher` *consumes* this API (a genuine
cross-plugin task, not a reason to read them by default) — see the
`ukorehub-plugin` skill.
# PublishApi
