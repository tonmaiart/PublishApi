"""Per-ticket configuration for MayaPublisher (before the 2026-08-05
merge, three separate plugins: ModelPublisher, RigPublisher,
AnimationPublisher) — replaces the old single "repo_publish_target"
choice (one Publish Path per tool per repo, picked in a UkoreHub-side
Repo Studio Setting tab) with user-managed
**tickets**, created/renamed/deleted entirely from each tool's own Maya
window (see ticket_manager_dialog.py). Each ticket has its own display
`name`, its own immutable on-disk `folder_name`, its own `publish_target`
(a pipeline connection ref, same shape the old single choice used), and
its own folder of attached scripts. As of 2026-08-05, `function.py`'s
`publish()` does **not** export/copy any file itself — it only resolves
the destination and creates the versioned folder, then hands that off to
this ticket's attached scripts, which decide entirely for themselves what
to export/copy there (see `run_validation_scripts`'s `context` argument
below). A script whose `validate()` returns `False` (or raises) still
blocks the publish from being reported as successful, same as before —
these scripts are now both the gate *and* the mechanism.

Storage: <active repo's own local clone>/.ukorehub/<tool_id>_tickets.json,
key "tickets", a flat list — committed to that repo's own git history like
any other pipeline config (PublishValidation/'s scripts, validation_scripts_dir()
below), not gitignored, since ticket definitions (publish target, attached
scripts) are team-shared pipeline config every artist on that repo needs,
not personal/per-machine scratch state. Moved out of the old shared
data/plugins/core/<tool_id>.json blob (which held every studio repo's
tickets in one cloud-synced file, keyed by "<project_id>:<repo_id>") since
that file requires Google Cloud Storage access this Maya process doesn't
have (no google-cloud-storage in mayapy's site-packages) — see
_migrate_from_shared_store below for how an existing repo's tickets saved
under the old shared blob are carried forward into its own repo-local file
on first access. Every function here follows repo_paths.py's own
"construct the store straight off disk" convention — Maya's Python has no
PluginAPI instance to call plugin_config_store() through.

Validation scripts are real .py files living in a **fixed, repo-committed
folder** — <active repo's own local clone>/PublishValidation/<tool_id>/ —
normally authored/edited entirely outside this tool (a text editor,
committed to the repo like any other pipeline code, shared to the whole
team via that repo's own git history), though `create_script` (added
2026-08-05) can also seed a new one from a template without leaving Maya.
A ticket just stores which of the scripts sitting in that folder apply to
it and in what order (`ticket["script_names"]`, an ordered list of
filenames — see `attach_script`/`detach_script`/`move_script`). Loading
borrows the "folder of individually loaded
scripts" convention from tmlib.core.QuickData
(plugins/repo_internal/MayaToolkit/maya-scripts/tmlib/core/QuickData.py, used by
the PythonReader toolkit, formerly "QuickScript") — same
importlib.util.spec_from_file_location/exec_module mechanism as its
run_script_file(), except we call validate() instead of run() and collect
the bool results instead of discarding them."""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

from PublishApi import repo_paths


def _repo_ticket_store(tool_id: str):
    """The active repo's own .ukorehub/<tool_id>_tickets.json — None if
    there's no active repo. Reuses PluginConfigStore (core/extensibility/
    config_store.py) purely for its atomic JSON load/set, not for anything
    data/plugins/core/-specific; it works on any Path."""
    from core.extensibility.config_store import PluginConfigStore

    _project, _repo, repo_path = repo_paths.get_active_repo()
    if repo_path is None:
        return None
    return PluginConfigStore(repo_path / ".ukorehub" / f"{tool_id}_tickets.json")


def _migrate_from_shared_store(tool_id: str, project_id: str, repo_id: str) -> list[dict]:
    """One-time carry-forward for a repo that already had tickets saved in
    the old shared data/plugins/core/<tool_id>.json blob (pre-migration to
    each repo's own .ukorehub/ folder) — either this repo's "tickets"[key]
    entry, or (if that repo never had tickets yet) an old-style single
    "repo_publish_target" choice, carried forward as a "Main" ticket
    instead of silently losing it (this is exactly the RigTeam ->
    PublishToUnity choice made earlier via the now-removed UkoreHub
    Repository Setting tab). [] if neither exists."""
    import uuid

    from core.extensibility.config_store import PluginConfigStore

    root = repo_paths.find_ukorehub_root()
    shared_store = PluginConfigStore(root / "data" / "plugins" / "core" / f"{tool_id}.json")
    key = f"{project_id}:{repo_id}"

    tickets = shared_store.get("tickets", {}).get(key)
    if tickets is not None:
        return tickets

    legacy = shared_store.get("repo_publish_target", {}).get(key)
    if legacy is None:
        return []
    return [
        {
            "id": uuid.uuid4().hex,
            "name": "Main",
            "folder_name": "Main",
            "publish_target": {
                "project_id": legacy.get("project_id"),
                "repo_id": legacy.get("repo_id"),
                "custom_path_id": legacy.get("custom_path_id"),
            },
            "script_names": [],
        }
    ]


def list_tickets(tool_id: str) -> list[dict]:
    """The active repo's tickets for `tool_id`, running the one-time
    shared-store migration if this repo's own .ukorehub/ file has none
    yet. [] if there's no active repo."""
    project, repo, _repo_path = repo_paths.get_active_repo()
    if project is None:
        return []

    store = _repo_ticket_store(tool_id)
    if store is None:
        return []
    tickets = store.get("tickets")

    if tickets is None:
        tickets = _migrate_from_shared_store(tool_id, project.id, repo.id)
        store.set("tickets", tickets)

    return tickets


def _save_tickets(tool_id: str, tickets: list[dict]) -> None:
    store = _repo_ticket_store(tool_id)
    if store is None:
        return
    store.set("tickets", tickets)


def create_ticket(tool_id: str, name: str, folder_name: str) -> dict:
    """Raises ValueError if `folder_name` collides with an existing
    ticket's folder for this repo — two tickets silently sharing one
    version-history folder is a footgun worth blocking outright, not
    something to quietly allow."""
    import uuid

    project, _repo, _repo_path = repo_paths.get_active_repo()
    if project is None:
        raise RuntimeError("No active repo selected in UkoreHub.")

    existing = list_tickets(tool_id)
    if any(t["folder_name"] == folder_name for t in existing):
        raise ValueError(f"A ticket already publishes into folder '{folder_name}' for this repo.")

    ticket = {
        "id": uuid.uuid4().hex,
        "name": name,
        "folder_name": folder_name,
        "publish_target": None,
        "script_names": [],
    }
    existing.append(ticket)
    _save_tickets(tool_id, existing)
    return ticket


def _update_ticket(tool_id: str, ticket_id: str, mutate) -> None:
    tickets = list_tickets(tool_id)
    for ticket in tickets:
        if ticket["id"] == ticket_id:
            mutate(ticket)
            break
    _save_tickets(tool_id, tickets)


def rename_ticket(tool_id: str, ticket_id: str, new_name: str) -> None:
    """Only `name` changes — `folder_name` is immutable after creation, so
    renaming a ticket never moves/breaks its already-published versions."""
    _update_ticket(tool_id, ticket_id, lambda t: t.update(name=new_name))


def set_ticket_publish_target(tool_id: str, ticket_id: str, ref: dict | None) -> None:
    _update_ticket(tool_id, ticket_id, lambda t: t.update(publish_target=ref))


def set_ticket_export_type(tool_id: str, ticket_id: str, export_type: str) -> None:
    """Only meaningful for animation_publisher tickets ("playblast" or
    "unreal") — Rig/Model tickets never get this key."""
    _update_ticket(tool_id, ticket_id, lambda t: t.update(export_type=export_type))


def delete_ticket(tool_id: str, ticket_id: str) -> None:
    """Removes the ticket's JSON entry only — does not delete its scripts
    folder or any already-published output. Deleting a folder the user
    might not realize still matters (old versions, scripts they forgot
    about) is exactly the kind of silent destructive action this codebase
    avoids elsewhere."""
    tickets = [t for t in list_tickets(tool_id) if t["id"] != ticket_id]
    _save_tickets(tool_id, tickets)


def get_publish_root_for_ticket(tool_id: str, ticket: dict) -> str:
    """The publish destination root for this specific ticket — its own
    chosen Publish Path, resolved to <target repo's cloned path>/<its
    chosen CustomPath's own relative path>. Same RuntimeError-with-
    human-message contract the old per-tool get_publish_root(tool_id) had,
    just resolved from ticket["publish_target"] instead — no "auto-pick
    the repo's only connection" fallback, since each ticket now makes its
    own explicit choice."""
    project, _repo, _ = repo_paths.get_active_repo()
    if project is None:
        raise RuntimeError(
            "No active repo selected in UkoreHub. Open UkoreHub, pick a project/repo, then try again."
        )

    ref = ticket.get("publish_target")
    if ref is None:
        raise RuntimeError(
            f"Ticket '{ticket['name']}' has no Publish Path set yet. "
            "Pick one under Manage Tickets... in this tool's window."
        )

    resolved = repo_paths.resolve_ref(ref)
    if resolved is None:
        raise RuntimeError(f"Ticket '{ticket['name']}'s chosen Publish Path's target repo no longer exists.")
    _target_project, target_repo, target_repo_path = resolved

    if not target_repo_path.is_dir():
        raise RuntimeError(
            f"Publish Path target repo '{target_repo.name}' hasn't been cloned yet — clone it in UkoreHub first."
        )

    custom_path = repo_paths.get_custom_path(ref["project_id"], ref["repo_id"], ref.get("custom_path_id"))
    if custom_path is None:
        raise RuntimeError(
            f"'{target_repo.name}'s declared Custom Path for ticket '{ticket['name']}' no longer exists — "
            "re-pick a Publish Path for this ticket under Manage Tickets..."
        )

    # See developer/bug-history/2026-07-20-playblast-custom-path-leading-slash.md /
    # developer/bug-history/2026-08-03-publishapi-custom-path-leading-slash.md —
    # custom_path["path"] is raw user input; a leading separator would
    # anchor this join to the current drive root instead of target_repo_path.
    return str(target_repo_path / custom_path["path"].lstrip("/\\"))


def validation_scripts_dir(tool_id: str) -> Path:
    """The fixed, repo-committed folder validation scripts for `tool_id`
    live in — <active repo's own local clone>/PublishValidation/<tool_id>/
    — created on first use if it doesn't exist yet. Unlike ticket
    metadata, this is NOT under UkoreHub's own data/: it's part of the
    active repo's own checked-out pipeline code, so it's naturally
    shared/versioned via that repo's own git history (a TD commits a
    script here like any other pipeline file) instead of UkoreHub's
    install. Per-tool (not shared across Rig/Model/Animation) since a
    Rig-scene check and a Model-scene check are rarely the same script."""
    _project, _repo, repo_path = repo_paths.get_active_repo()
    if repo_path is None:
        raise RuntimeError("No active repo selected in UkoreHub.")
    folder = repo_path / "PublishValidation" / tool_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_available_scripts(tool_id: str) -> list[Path]:
    """Every .py file currently sitting in this repo's fixed validation-
    script folder for `tool_id` — normally authored/edited outside this
    tool (a text editor, committed to the repo), though `create_script`
    below (added 2026-08-05) can also seed one from a starter template.
    See ticket_manager_dialog.py's "Open Script Folder..."/"Edit Script..."
    buttons for jumping straight to this folder/a specific file."""
    folder = validation_scripts_dir(tool_id)
    return sorted(p for p in folder.iterdir() if p.suffix == ".py")


_SCRIPT_TEMPLATE = '''"""Publish script for MayaPublisher.

validate() runs whenever this script is attached to a ticket (Manage
Tickets... > Available Scripts) and that ticket is published. Return True
to let the publish proceed, False to block it and show an artist-facing
error. Raising an exception also blocks the publish, with the exception
message shown the same way.

Every attached script on a ticket runs, in the order shown under Manage
Tickets... > Run Order (use Move Up/Down to change it) — even scripts
after one that already failed, so put pure checks and real file work in
whichever order makes sense for this ticket.

Accept one optional argument, `context`, to also do real publish work
(copy/export files) instead of just checking something — a script with a
plain validate() (no arguments) still works exactly like a check-only
script always has:

    context = {
        "version_dir": str,  # already-created destination folder for this publish
        "version": int,      # version number just created, e.g. 3 for v003
        "ticket": dict,       # the full ticket dict (name, folder_name, export_type, ...)
        "mode": str,          # "rig" / "model" / "animation" - this repo's Publish Mode
        "tool_id": str,       # "maya_publisher"
    }
"""

# import os
# from UkoreMaya.core import Pipeline


def validate(context):
    # Example — copy the current scene as a Maya Ascii file into this
    # publish's version folder. Replace with whatever this ticket actually
    # needs to check and/or export, or remove the context argument
    # entirely for a check-only script.
    #
    # folder_name = context["ticket"]["folder_name"]
    # version = context["version"]
    # ma_path = os.path.join(context["version_dir"], "{}_v{:03d}.ma".format(folder_name, version))
    # Pipeline.export_maya_common(export_file_path=ma_path)

    return True
'''


def create_script(tool_id: str, script_name: str) -> Path:
    """Creates a new .py file in this tool's validation-script folder
    (validation_scripts_dir(tool_id)), seeded from _SCRIPT_TEMPLATE above
    so a studio admin doesn't have to remember the validate(context)
    contract from scratch. Adds a .py suffix if the caller didn't include
    one. Raises ValueError if a script with this name already exists —
    never silently overwrites a TD's existing work. Doesn't attach the new
    script to any ticket; that's still a separate, explicit checkbox
    action (see attach_script)."""
    if not script_name.endswith(".py"):
        script_name += ".py"

    folder = validation_scripts_dir(tool_id)
    script_path = folder / script_name
    if script_path.exists():
        raise ValueError(f"A script named '{script_name}' already exists in {folder}.")

    script_path.write_text(_SCRIPT_TEMPLATE, encoding="utf-8")
    return script_path


def attach_script(tool_id: str, ticket_id: str, script_name: str) -> None:
    """Marks one of list_available_scripts()'s files as applying to this
    ticket, appended to the end of its run order (script_names — see
    move_script) if not already attached. Stores just the filename, not a
    full path — the fixed folder itself is derived from the active repo +
    tool_id, never per-ticket."""

    def _mutate(t: dict) -> None:
        names = list(t.get("script_names", []))
        if script_name not in names:
            names.append(script_name)
        t["script_names"] = names

    _update_ticket(tool_id, ticket_id, _mutate)


def detach_script(tool_id: str, ticket_id: str, script_name: str) -> None:
    """Un-marks a script for this ticket — never deletes the actual file
    in validation_scripts_dir(), which may still be attached to other
    tickets or repos."""

    def _mutate(t: dict) -> None:
        t["script_names"] = [n for n in t.get("script_names", []) if n != script_name]

    _update_ticket(tool_id, ticket_id, _mutate)


def move_script(tool_id: str, ticket_id: str, script_name: str, delta: int) -> None:
    """Shifts `script_name` earlier (delta=-1) or later (delta=+1) in this
    ticket's own run order (script_names) — run_validation_scripts runs
    every attached script in exactly this list's order. No-op if
    script_name isn't attached or the move would go out of bounds (already
    first/last)."""

    def _mutate(t: dict) -> None:
        names = list(t.get("script_names", []))
        if script_name not in names:
            return
        index = names.index(script_name)
        new_index = index + delta
        if not (0 <= new_index < len(names)):
            return
        names[index], names[new_index] = names[new_index], names[index]
        t["script_names"] = names

    _update_ticket(tool_id, ticket_id, _mutate)


def run_validation_scripts(tool_id: str, ticket: dict, context: dict | None = None) -> tuple[bool, str]:
    """Loads every one of this ticket's attached scripts (same
    importlib.util.spec_from_file_location + exec_module mechanism
    QuickData.run_script_file uses) and calls validate() on each. Runs
    every script — doesn't stop at the first failure — so the artist sees
    everything wrong in one message (note: a script that does real file
    work, not just a check, will still have already run by the time a
    later script's failure is reported — see MayaPublisher's README).

    As of 2026-08-05, `validate` may optionally take one argument —
    `context` (a dict with at least `version_dir`, the already-created
    destination folder this publish resolved/versioned): this is what
    lets a script decide entirely for itself what to export/copy where,
    instead of the calling plugin doing a hardcoded export before this
    function even runs. A zero-argument `validate()` (the original
    contract, checks only, no file work) still works unchanged — dispatch
    below inspects the function's own signature rather than requiring
    every caller to pass a context. A script with no validate() defined
    is treated as a pass-through; a script name the ticket still
    references but that's no longer present in the fixed folder (e.g.
    renamed/removed by a TD) is treated as a hard failure, since that's a
    configuration problem worth surfacing rather than silently ignoring."""
    script_names = ticket.get("script_names", [])
    if not script_names:
        return True, ""

    folder = validation_scripts_dir(tool_id)
    failures: list[str] = []
    for script_name in script_names:
        script_path = folder / script_name
        if not script_path.exists():
            failures.append(
                f"{script_name}: no longer found in PublishValidation/{tool_id}/ — "
                "re-check this ticket's attached scripts under Manage Tickets..."
            )
            continue

        module_name = script_path.stem
        try:
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 - a broken script must not crash publish()
            failures.append(f"{script_name}: failed to load ({exc})")
            continue

        validate = getattr(module, "validate", None)
        if validate is None:
            print(f"[PublishApi.tickets] {script_name} has no validate() — treating as pass.")
            continue

        try:
            wants_context = len(inspect.signature(validate).parameters) >= 1
            passed = validate(context) if wants_context else validate()
        except Exception as exc:  # noqa: BLE001 - same reasoning as the load try/except above
            failures.append(f"{script_name}: raised {exc}")
            continue

        if not passed:
            failures.append(f"{script_name}: validate() returned False")

    if failures:
        message = "Publish blocked by validation script(s):\n" + "\n".join(f"- {f}" for f in failures)
        return False, message

    return True, ""
