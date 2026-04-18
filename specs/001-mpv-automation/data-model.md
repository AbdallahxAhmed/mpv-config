# Data Model: MPV Auto-Deploy Automation

**Feature**: 001-mpv-automation
**Date**: 2026-04-18

## Entities

### Environment

Represents the detected machine state. Populated by `detector.py`.

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| os | string | `"windows"` \| `"linux"` \| `"macos"` | Detected operating system |
| distro | string | `"arch"` \| `"ubuntu"` \| `"fedora"` \| `""` | Linux distribution family |
| platform_key | string | `"windows"` \| `"arch"` \| `"ubuntu"` \| `"macos"` | Registry lookup key |
| display | string | `"wayland"` \| `"x11"` \| `""` | Display server (Linux only) |
| gpu_vendor | string | `"nvidia"` \| `"amd"` \| `"intel"` \| `""` | GPU vendor |
| pkg_manager | string | `"winget"` \| `"pacman"` \| `"apt"` \| `"dnf"` \| `"brew"` \| `""` | Primary package manager |
| aur_helper | string | `"paru"` \| `"yay"` \| `""` | AUR helper (Arch only) |
| config_dir | string | absolute path | Resolved mpv config directory |
| python_cmd | string | `"python"` \| `"python3"` | Python executable name |
| pip_cmd | string | `"pip"` \| `"pip3"` \| `"python3 -m pip"` | Pip command string |
| has_git | bool | | Whether git is available |
| installed | dict[str, bool] | | Per-dependency install status |

**Validation rules**:
- `os` is never empty (defaults to `"linux"`).
- `config_dir` is always an absolute path.
- `installed` keys match `SYSTEM_DEPS` keys exactly.

---

### ScriptEntry

Represents a third-party mpv script in the registry.

| Field | Type | Description |
|-------|------|-------------|
| name | string | Script identifier (e.g., `"uosc"`) |
| desc | string | Human-readable description |
| source.type | string | `"github_raw"` \| `"github_release"` |
| source.repo | string | GitHub `owner/repo` |
| source.branch | string | Branch for raw downloads |
| source.files | list[{src, dest}] | File mappings for raw downloads |
| source.asset_pattern | string | Asset name pattern for releases |
| source.pin | string \| None | Version pin for releases |
| install.map | dict[str, str] | Zip extraction path mappings |
| config | string \| None | Associated config file name |
| config_is_template | bool | Whether config needs patching |
| sys_deps | list[string] | Required system dependencies |
| optional_deps | list[string] | Optional system dependencies |
| script_deps | list[string] | Required mpv script dependencies |

**State transitions**: None (static registry data).

---

### ShaderEntry

Represents a shader pack (Anime4K).

| Field | Type | Description |
|-------|------|-------------|
| name | string | `"Anime4K"` |
| source.type | string | `"github_release"` |
| source.repo | string | `"bloc97/Anime4K"` |
| source.asset_pattern | string | `"Anime4K_v"` |
| source.pin | string | Version pin (e.g., `"v4.0.1"`) |
| dest | string | Target directory (`"shaders/"`) |
| extensions | list[string] | File extensions to extract |

---

### SystemDependency

Represents an installable package.

| Field | Type | Description |
|-------|------|-------------|
| \<platform\>.method | string | `"winget"` \| `"pacman"` \| `"apt"` \| `"brew"` \| `"pip"` \| `"aur"` \| `"manual"` |
| \<platform\>.pkg | string | Package name for the package manager |
| \<platform\>.id | string | Package ID (winget) |
| \<platform\>.flags | list[string] | Extra flags (e.g., `["--user"]`) |
| verify | list[string] | Command to verify installation |
| verify_alt | list[string] | Alternative verify command |

**Platforms**: `"windows"`, `"arch"`, `"ubuntu"`, `"macos"`, `"all"`.

---

### AuditLogSession

Represents a single tool invocation.

| Field | Type | Description |
|-------|------|-------------|
| session_id | string | UUID prefix (8 chars) |
| operation | string | `"install"` \| `"update"` \| `"uninstall"` \| `"rollback"` |
| started_at | string | ISO 8601 timestamp |
| completed_at | string \| None | ISO 8601 or None if in progress |
| status | string | `"in_progress"` \| `"completed"` \| `"completed_with_errors"` \| `"failed"` \| `"cancelled"` |
| environment | object | Snapshot of key env fields |
| packages | dict[str, PackageRecord] | Per-package state |
| files | list[FileRecord] | File operations log |
| backups | list[{path, created_at}] | Backup records |

**State transitions**:
```
in_progress → completed
in_progress → completed_with_errors
in_progress → failed
in_progress → cancelled
```

---

### PlanEntry

Represents a single planned action before execution.

| Field | Type | Description |
|-------|------|-------------|
| category | string | `"package"` \| `"fetch"` \| `"backup"` \| `"file"` |
| action | string | `"install"` \| `"skip"` \| `"remove"` \| `"backup"` \| `"deploy"` \| `"fetch"` \| `"create"` |
| target | string | Package name or file path |
| detail | string | Human-readable explanation |

## Relationships

```
Environment ─── detected by ──→ detector.py
     │
     ├── drives ──→ installer.py (which deps to install)
     ├── drives ──→ deployer.py  (paths, symlink vs copy)
     ├── drives ──→ registry.py  (platform defaults lookup)
     └── drives ──→ planner.py   (what plan to show)

ScriptEntry ─── fetched by ──→ fetcher.py
     │
     └── deployed by ──→ deployer.py

AuditLogSession ─── created by ──→ setup.py
     │
     ├── records from ──→ installer.py (packages)
     ├── records from ──→ deployer.py  (files)
     └── queried by ──→ cmd_uninstall (safe removal)
```
