# CLI Contract: MPV Auto-Deploy

**Feature**: 001-mpv-automation
**Date**: 2026-04-18

## Entry Points

### 1. `setup.py` (Main CLI)

```
python setup.py [OPTIONS]

Options:
  --install              Full install (detect → deps → fetch → deploy → verify)
  --update               Update scripts/shaders only (no config overwrite)
  --rollback [BACKUP]    Restore latest backup, or specific backup path
  --uninstall            Remove deployed files/config
  --verify               Verify current deployment integrity
  --status               Show installed script versions + audit log summary
  --interactive          Show numbered menu (default when no flags + TTY)
  --dry-run              Preview all actions without making changes
  --mpv-profile PROFILE  "windows-like" (default) or "native"
  --purge-config         With --uninstall: remove entire mpv config dir
  --remove-backups       With --uninstall: remove backup directories
  --remove-deps          With --uninstall: uninstall managed dependencies
  --remove-python        With --remove-deps: include python packages
  --remove-install-dir   With --uninstall: remove ~/.mpv-deploy + launcher

Exit codes:
  0   Success
  1   Fatal error
  130 User interrupted (Ctrl+C)
```

### 2. `mpv-config` Launcher (Post-Install)

```
mpv-config [OPTIONS]

Equivalent to: python <install_dir>/setup.py [OPTIONS]
Same options as setup.py above.
No flags + interactive terminal → shows menu automatically.
```

### 3. `install.sh` (Bootstrap)

```
curl -fsSL https://…/install.sh | bash

Behavior:
  1. Detect OS + distro
  2. Clone repo to ~/.mpv-deploy
  3. Install Python if missing
  4. Run setup.py --install
  5. Create ~/.local/bin/mpv-config launcher symlink

Requirements:
  - bash (explicit #!/usr/bin/env bash shebang)
  - curl or wget
  - Internet connection
```

### 4. `install.ps1` (Windows Bootstrap)

```
irm https://…/install.ps1 | iex

Behavior:
  Same as install.sh but for Windows.
  Uses winget for dependencies.
  Creates launcher in user PATH.
```

## Interactive Menu Contract

When `--interactive` or no flags + TTY:

```
+======================================================+
|              MPV Auto-Deploy System v1.0             |
+======================================================+

  Choose Action

  1) Full install
  2) Update scripts/shaders
  3) Rollback (latest backup)
  4) Rollback (specific backup path)
  5) Verify installation
  6) Show status
  7) Uninstall deployed files
  8) Full remove (files + backups + deps + install dir)
  0) Exit

  Select option [0-8]:
```

## Output Format Contract

### Detection Phase
Displays each detected property as a success/warn line:
```
  ✓ OS: linux (Linux-6.x-arch1-1-x86_64)
  ✓ Distro: arch
  ✓ Display: wayland
  ✓ GPU: nvidia
  ✓ Package manager: pacman
  ✓ mpv config dir: ~/.config/mpv
```

### Plan Phase
Displays categorized action plan with color-coded actions:
```
  System Packages:
    [=] SKIP    mpv         # already installed — no change
    [+] INSTALL ffsubsync   # install via pip: ffsubsync (optional)

  Scripts & Shaders to Download:
    [↓] FETCH   uosc        # download from github.com/tomasklaen/uosc

  Configuration Files:
    [→] DEPLOY  ~/.config/mpv/mpv.conf  # patched from template
```

### Summary Phase
Rich Table with status column:
```
╔════════════════════════════════════════╗
║  Summary                              ║
╠════════════════════════════════════════╣
║  ✓ uosc                    v5.x.x    ║
║  ✓ thumbfast                latest    ║
║  ✗ sponsorblock      404 Not Found    ║
╠════════════════════════════════════════╣
║  8 succeeded   1 failed              ║
╚════════════════════════════════════════╝
```

## Error Output Contract

Errors are displayed in red-bordered panels with actionable guidance:

```
╭─ Error ──────────────────────────────╮
│ Cannot reach GitHub.                 │
│                                      │
│ Check your internet connection.      │
│ If behind a proxy, set HTTP_PROXY.   │
╰──────────────────────────────────────╯
```

## File Output Contract

### `.deploy.lock.json`
```json
{
  "fetched_at": "2026-04-18T10:00:00+00:00",
  "scripts": {
    "uosc": {
      "name": "uosc",
      "version": "v5.x.x",
      "source": "github:tomasklaen/uosc@v5.x.x",
      "files_count": 42,
      "fetched_at": "2026-04-18T10:00:00+00:00"
    }
  }
}
```

### `.audit-log.json`
```json
{
  "schema_version": "1.0",
  "sessions": [
    {
      "session_id": "a1b2c3d4",
      "operation": "install",
      "started_at": "2026-04-18T10:00:00+00:00",
      "completed_at": "2026-04-18T10:05:00+00:00",
      "status": "completed",
      "packages": {
        "mpv": {"was_pre_existing": true, "action": "none", "status": "ok"}
      },
      "files": [
        {"path": "/home/user/.config/mpv/scripts", "operation": "symlink", "status": "ok"}
      ],
      "backups": []
    }
  ]
}
```
