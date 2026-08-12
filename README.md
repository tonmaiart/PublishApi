# 📚 PublishApi Technical & Integration Documentation

> **Version:** 1.0.0
> **Target Audience:** Pipeline Developers, Technical Directors (TDs), and Tool Integrators
> **Environment:** Maya Side (Python 3 in Maya / UkoreHub Environment)

---

## 1. Overview & Architecture

`PublishApi` is a shared Maya-side library and single source of truth for:

1. **Publish Target Resolution** — Resolves publish destinations from Project Editor pipeline connections.
2. **Folder Versioning (`vNNN`)** — Automatically creates sequential version directories.
3. **Ticket-Based Validation & Export** — Manages publish tickets and executes attached validation/export scripts.

`PublishApi` is primarily consumed by `MayaPublisher` and was previously used by `ModelPublisher`, `RigPublisher`, and `AnimationPublisher`.

### Key Capabilities

* **Pipeline-Aware Resolution:** Resolves target publish folders dynamically from Project Editor's declared pipeline connections (`pipeline_inputs` and `custom_paths`), avoiding hardcoded path replacement conventions such as `.../share/...` → `.../publish/...`.
* **Ticket Management System:** Stores publish targets, folder structures, and script configurations on a per-ticket basis in `.ukorehub/<tool_id>_tickets.json`.
* **Scripted Validation & Export Engine:** Executes Python scripts attached to tickets. Scripts can perform validation checks or execute export/copy operations through a contextual `context` dictionary.
* **Automatic Versioning:** Scans existing directories for `vNNN` patterns and automatically creates the next sequential version.
* **Maya Launcher Bridge Integration:** Registers the `maya-scripts/` directory and UkoreHub root in the shared `PYTHONPATH` bridge for seamless imports inside Maya.

---

## 2. Directory & Storage Structure

### 2.1 Repository Layout

```text
PublishApi/
├── manifest.json                     # Plugin metadata & dependencies
├── plugin.py                         # Bridge registration entry point
├── README.md                         # High-level summary documentation
└── maya-scripts/
    └── PublishApi/
        ├── __init__.py               # Package exports
        ├── repo_paths.py             # Pipeline ref & path resolution logic
        ├── tickets.py                # Ticket storage, lifecycle & script execution
        ├── ticket_manager_dialog.py  # PySide QDialog UI for managing tickets
        └── versioning.py             # vNNN folder scanning & creation helpers
```

### 2.2 On-Disk Metadata & Script Locations

#### Ticket Configuration

Ticket configuration is stored directly inside the active local repository clone:

```text
<active_repo_root>/.ukorehub/<tool_id>_tickets.json
```

This file is committed to Git so that ticket configuration can be shared across the team.

#### Validation & Export Scripts

Validation and export scripts are stored in:

```text
<active_repo_root>/PublishValidation/<scripts_tool_id>/
```

Each script is a `.py` file checked into Git.

---

## 3. Core API Reference

### 3.1 `PublishApi.repo_paths`

Handles resolution of UkoreHub pipeline connections and repository metadata from disk.

#### `get_active_repo() -> tuple[Project | None, Repo | None, Path | None]`

Returns the currently active `(project, repo, repo_path)` in UkoreHub by reading:

```text
cache/local_config.json
data/projects/<project_id>.json  (Schema v2 project blob)
```

Returns:

```text
(project, repo, repo_path)
```

---

#### `get_pipeline_refs() -> list[dict]`

Returns all pipeline input connections configured for the active repository under:

```python
plugin_data["project_editor"]["pipeline_inputs"]
```

---

#### `resolve_ref(ref: dict) -> tuple[Project, Repo, Path] | None`

Resolves a pipeline reference dictionary such as:

```python
{
    "project_id": "proj_123",
    "repo_id": "repo_model_pub"
}
```

into its target:

```text
(project, repo, repo_path)
```

Returns `None` if the reference cannot be resolved.

---

#### `get_custom_paths(project_id: str, repo_id: str) -> list[dict]`

Retrieves declared `CustomPath` records for a project/repository.

Example return value:

```python
[
    {
        "id": "cp_characters",
        "label": "Characters",
        "path": "publish/characters"
    }
]
```

---

#### `get_custom_path(

```
project_id: str,
repo_id: str,
custom_path_id: str | None
```

) -> dict | None`

Looks up a specific `CustomPath` dictionary by ID.

Returns `None` if the requested path does not exist.

---

### 3.2 `PublishApi.tickets`

Manages publish tickets, target resolution, and validation/export script execution.

#### `list_tickets(tool_id: str) -> list[dict]`

Lists all tickets configured for `tool_id` in the active repository.

The function also triggers automatic migration from legacy shared ticket storage when applicable.

---

#### `create_ticket(

```
tool_id: str,
name: str,
folder_name: str
```

) -> dict`

Creates a new ticket entry.

Important behavior:

* `folder_name` is **immutable** after ticket creation.
* This preserves historical version directories.
* Raises `ValueError` if `folder_name` collides with an existing ticket in the repository.

---

#### `get_publish_root_for_ticket(

```
tool_id: str,
ticket: dict
```

) -> str`

Resolves the full physical path on disk for the ticket's `publish_target`.

Result format:

```text
<target_repo_cloned_path>/<custom_path_relative_path>
```

Raises `RuntimeError` with human-readable guidance when:

* The target repository is not cloned.
* The target path is invalid.
* The referenced custom path cannot be resolved.

---

#### `run_validation_scripts(

```
tool_id: str,
ticket: dict,
context: dict | None = None
```

) -> tuple[bool, str]`

Executes all scripts attached to the ticket in the order specified by:

```python
ticket["script_names"]
```

Returns:

```python
(True, "")
```

when all scripts succeed.

If a script fails or raises an exception, returns:

```python
(False, error_message)
```

---

### 3.3 `PublishApi.versioning`

Handles directory creation and `vNNN` version scanning.

#### `get_new_version(base_dir: str) -> int`

Scans the immediate subdirectories of `base_dir` for directories matching:

```text
vNNN
```

For example:

```text
v001
v002
v003
```

If the highest existing version is `v002`, the function returns:

```python
3
```

---

#### `get_version_directory(

```
publish_root: str,
subfolder: str,
version: int | None = None
```

) -> tuple[str, int]`

Ensures the following directory structure exists:

```text
<publish_root>/<subfolder>/vNNN/
```

Parameters:

| Parameter      | Type          | Description                                                 |
| -------------- | ------------- | ----------------------------------------------------------- |
| `publish_root` | `str`         | Path returned by `get_publish_root_for_ticket()`            |
| `subfolder`    | `str`         | Target subfolder, typically `ticket["folder_name"]`         |
| `version`      | `int \| None` | Explicit version number, or `None` for automatic versioning |

When `version` is `None`, the next available version is automatically selected.

Returns:

```python
(version_dir_path, version_number)
```

---

## 4. Ticket Data Model & Script Writing Guide

### 4.1 Ticket Object Schema

A typical ticket object looks like:

```json
{
  "id": "a1b2c3d4e5f6...",
  "name": "Character Hi-Poly",
  "folder_name": "Character_Hi",
  "publish_target": {
    "project_id": "proj_123",
    "repo_id": "repo_model_pub",
    "custom_path_id": "cp_characters"
  },
  "script_names": [
    "01_check_naming.py",
    "02_export_maya_ascii.py"
  ],
  "export_type": "playblast"
}
```

### 4.2 Writing Validation & Export Scripts

Scripts are stored under:

```text
<repo_root>/PublishValidation/<scripts_tool_id>/<script_name>.py
```

Each script must define a `validate()` function.

The function may:

* Accept no arguments for a pure validation check.
* Accept one `context` argument for validation, export, or file-copy operations.

### Script Template & Example

Example file:

```text
PublishValidation/maya_publisher/02_export_maya_ascii.py
```

```python
import os


def validate(context=None):
    """
    Validation logic and/or file export.

    Returns:
        bool: True if validation/export succeeds,
              False to block the publish.
    """
    if context is None:
        # Check-only fallback.
        return True

    version_dir = context["version_dir"]
    version = context["version"]
    ticket = context["ticket"]
    mode = context["mode"]
    tool_id = context["tool_id"]

    print(
        f"Publishing version {version} "
        f"to {version_dir} for mode '{mode}'..."
    )

    # Example export operation:
    #
    # folder_name = ticket["folder_name"]
    # ma_path = os.path.join(
    #     version_dir,
    #     f"{folder_name}_v{version:03d}.ma"
    # )
    #
    # export_scene(ma_path)

    return True
```

### 4.3 Context Dictionary

When `run_validation_scripts()` is called with a context, the following keys are available:

| Key           | Type   | Description                                                |
| ------------- | ------ | ---------------------------------------------------------- |
| `version_dir` | `str`  | Full path to the newly created `vNNN` directory            |
| `version`     | `int`  | Numeric version, e.g. `3` for `v003`                       |
| `ticket`      | `dict` | Full dictionary definition of the active ticket            |
| `mode`        | `str`  | Active publisher mode, e.g. `model`, `rig`, or `animation` |
| `tool_id`     | `str`  | Publishing tool ID, e.g. `maya_publisher`                  |

Example:

```python
context = {
    "version_dir": "D:/Projects/AssetRepo/Character_Hi/v003",
    "version": 3,
    "ticket": ticket,
    "mode": "rig",
    "tool_id": "maya_publisher",
}
```

---

## 5. End-to-End Developer Integration Example

The following example demonstrates how a Maya publishing tool can use `PublishApi` to execute a complete publish workflow.

```python
from PublishApi import repo_paths, tickets, versioning


TOOL_ID = "maya_publisher"
SCRIPTS_TOOL_ID = "rig_publisher"


def publish_active_ticket(
    ticket_id: str,
    publish_mode: str = "rig"
):
    # 1. Fetch available tickets.
    all_tickets = tickets.list_tickets(TOOL_ID)

    ticket = next(
        (t for t in all_tickets if t["id"] == ticket_id),
        None
    )

    if not ticket:
        raise ValueError(
            f"Ticket ID '{ticket_id}' not found."
        )

    # 2. Resolve the destination publish root.
    publish_root = tickets.get_publish_root_for_ticket(
        TOOL_ID,
        ticket
    )

    # 3. Create the next version folder:
    #    <publish_root>/<folder_name>/vNNN/
    version_dir, version_num = (
        versioning.get_version_directory(
            publish_root=publish_root,
            subfolder=ticket["folder_name"]
        )
    )

    print(
        f"Target Version Directory: "
        f"{version_dir} (v{version_num:03d})"
    )

    # 4. Assemble the execution context.
    context = {
        "version_dir": version_dir,
        "version": version_num,
        "ticket": ticket,
        "mode": publish_mode,
        "tool_id": TOOL_ID,
    }

    # 5. Run validation and export scripts attached
    #    to the ticket.
    success, error_msg = (
        tickets.run_validation_scripts(
            tool_id=SCRIPTS_TOOL_ID,
            ticket=ticket,
            context=context
        )
    )

    if not success:
        print(
            f"❌ Publish Failed:\n{error_msg}"
        )
        return False

    print(
        f"✅ Successfully published "
        f"{ticket['name']} v{version_num:03d}!"
    )

    return True
```

### Workflow Summary

The publish workflow is:

```text
Load Ticket
    │
    ▼
Resolve Publish Target
    │
    ▼
Create Next Version Directory
    │
    ▼
Build Execution Context
    │
    ▼
Run Validation / Export Scripts
    │
    ├── Failed ──► Block Publish
    │
    └── Success ─► Publish Complete
```

---

## 6. UI Integration (`TicketManagerDialog`)

To open the ticket management GUI inside Maya using PySide:

```python
from tmlib.module.PySide import QtWidgets
from PublishApi.ticket_manager_dialog import TicketManagerDialog


def open_ticket_manager(parent_window=None):
    dialog = TicketManagerDialog(
        parent=parent_window,
        tool_id="maya_publisher",
        tool_label="Maya Publisher",
        show_export_type=True,
        scripts_tool_id="rig_publisher"
    )

    dialog.exec_()
```

### Parameters

| Parameter          | Description                                                        |
| ------------------ | ------------------------------------------------------------------ |
| `parent`           | Optional parent Maya window                                        |
| `tool_id`          | Tool ID used for ticket storage                                    |
| `tool_label`       | Display name shown in the UI                                       |
| `show_export_type` | Enables the Playblast / Unreal export type selector                |
| `scripts_tool_id`  | Optional separate tool ID used to locate validation/export scripts |

---

## 7. Recommended Integration Pattern

For a new Maya publisher, the recommended integration is:

1. Use `tickets.list_tickets()` to load configured publish tickets.
2. Resolve the destination with `tickets.get_publish_root_for_ticket()`.
3. Create the version directory using `versioning.get_version_directory()`.
4. Build a `context` dictionary containing publish information.
5. Execute ticket scripts using `tickets.run_validation_scripts()`.
6. Treat a `False` result as a publish-blocking failure.
7. Keep validation/export scripts under `PublishValidation/<scripts_tool_id>/`.
8. Keep ticket configuration under `.ukorehub/<tool_id>_tickets.json`.
9. Do not modify `folder_name` after a ticket has been created.
10. Avoid hardcoded `share` → `publish` path replacement; use pipeline/custom-path resolution instead.

---

## 8. Important Design Principles

### Single Source of Truth

`PublishApi` should remain the central location for:

* Publish target resolution.
* Ticket configuration.
* Version directory creation.
* Validation/export script execution.

Publisher tools should avoid duplicating this logic.

### Pipeline-Driven Paths

Publish paths should be determined from Project Editor configuration rather than relying on assumptions about repository layouts.

This makes the publishing system adaptable to different projects, repositories, and pipeline configurations.

### Immutable Ticket Folder Names

Once a ticket has been created, its `folder_name` should not be changed.

For example:

```text
Character_Hi/
├── v001/
├── v002/
└── v003/
```

Changing the ticket's folder name later could make historical publish versions difficult to locate or associate with the original ticket.

### Script-Based Extensibility

The ticket system allows publishing behavior to be extended without modifying the core `PublishApi`.

A ticket can attach multiple scripts:

```json
{
  "script_names": [
    "01_check_naming.py",
    "02_check_scene.py",
    "03_export_maya_ascii.py"
  ]
}
```

Scripts execute in the configured order.

---

## 9. File Naming Example

A typical published Maya scene could use the ticket folder name and version:

```text
<publish_root>/
└── Character_Hi/
    ├── v001/
    │   └── Character_Hi_v001.ma
    ├── v002/
    │   └── Character_Hi_v002.ma
    └── v003/
        └── Character_Hi_v003.ma
```

Example export code:

```python
import os


def validate(context=None):
    if context is None:
        return True

    version_dir = context["version_dir"]
    version = context["version"]
    ticket = context["ticket"]

    folder_name = ticket["folder_name"]

    export_path = os.path.join(
        version_dir,
        f"{folder_name}_v{version:03d}.ma"
    )

    print(f"Export path: {export_path}")

    # Maya export implementation goes here.

    return True
```

---

## 10. Error Handling

Publisher integrations should handle the following expected errors.

### Ticket Not Found

```python
ticket = next(
    (t for t in tickets.list_tickets(TOOL_ID)
     if t["id"] == ticket_id),
    None
)

if not ticket:
    raise ValueError(
        f"Ticket ID '{ticket_id}' not found."
    )
```

### Publish Target Resolution Failure

`get_publish_root_for_ticket()` may raise `RuntimeError` when the target repository or custom path cannot be resolved.

The publisher should display the returned error message to the user and stop the publish operation.

### Validation Failure

A validation script can intentionally return:

```python
return False
```

The publish operation should then be blocked.

### Script Exception

If an attached script raises an exception, `run_validation_scripts()` returns:

```python
(False, error_message)
```

The publisher should report the error and treat the publish as failed.

---

## 11. Summary

`PublishApi` provides a centralized publishing foundation for Maya tools within the UkoreHub environment.

Its main responsibilities are:

```text
Pipeline Configuration
        │
        ▼
Publish Target Resolution
        │
        ▼
Ticket Configuration
        │
        ▼
Version Directory Creation
        │
        ▼
Validation / Export Scripts
        │
        ▼
Published Asset
```

By keeping target resolution, ticket management, versioning, and script execution inside `PublishApi`, individual Maya publisher tools can remain focused on their specific publishing workflows while sharing the same pipeline behavior and conventions.
