"""
audit_log.py — Operation audit log / manifest for safe rollback and uninstall.

Records every action taken by the installer (package installs, file operations,
backups) together with whether each package was pre-existing.  This makes
rollback and uninstall safe: packages and files that existed before this tool
was first run will never be automatically removed.

Log file: <mpv config dir>/.audit-log.json
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

LOG_SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    """
    Persistent JSON audit log for all installer sessions.

    Each session (install / update / uninstall / rollback) is appended to the
    ``sessions`` list.  Within a session every touched package and file is
    recorded along with a timestamp and outcome so the full history is always
    available for safe rollback decisions.
    """

    def __init__(self, log_path: str):
        self.log_path = log_path
        self._data: Dict[str, Any] = {
            "schema_version": LOG_SCHEMA_VERSION,
            "sessions": [],
        }
        self._current_session: Optional[Dict[str, Any]] = None
        self._load()

    # ─── Persistence ───────────────────────────────────────────────────

    def _load(self):
        """Load an existing log file; start fresh if absent or corrupt."""
        if not os.path.isfile(self.log_path):
            return
        try:
            with open(self.log_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and "sessions" in data:
                self._data = data
        except (json.JSONDecodeError, OSError):
            # Corrupt log — preserve it but start a clean one
            corrupt_path = self.log_path + ".corrupt"
            try:
                os.replace(self.log_path, corrupt_path)
            except OSError:
                pass

    def save(self):
        """Write the current log to disk atomically (best-effort)."""
        log_dir = os.path.dirname(self.log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        tmp = self.log_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.log_path)
        except OSError:
            pass  # Non-fatal: logging is best-effort

    # ─── Session lifecycle ─────────────────────────────────────────────

    def start_session(self, operation: str, env) -> str:
        """
        Begin a new session record and return its short session_id.

        Parameters
        ----------
        operation:
            One of ``"install"``, ``"update"``, ``"uninstall"``, ``"rollback"``.
        env:
            Detected ``Environment`` object (used for context metadata).
        """
        session_id = str(uuid.uuid4())[:8]
        self._current_session = {
            "session_id": session_id,
            "operation": operation,
            "started_at": _now_iso(),
            "completed_at": None,
            "status": "in_progress",
            "environment": {
                "os": getattr(env, "os", ""),
                "distro": getattr(env, "distro", ""),
                "platform_key": getattr(env, "platform_key", ""),
                "config_dir": getattr(env, "config_dir", ""),
            },
            "initial_package_state": getattr(env, "installed", {}).copy() if hasattr(env, "installed") else {},
            "packages": {},
            "files": [],
            "backups": [],
        }
        self._data["sessions"].append(self._current_session)
        self.save()
        return session_id

    def complete_session(self, status: str = "completed"):
        """
        Finalise the active session.

        Parameters
        ----------
        status:
            ``"completed"``, ``"completed_with_errors"``, ``"failed"``,
            or ``"cancelled"``.
        """
        sess = self._require_session()
        sess["status"] = status
        sess["completed_at"] = _now_iso()
        self._current_session = None
        self.save()

    def _require_session(self) -> Dict[str, Any]:
        if self._current_session is None:
            raise RuntimeError(
                "No active audit session — call start_session() first."
            )
        return self._current_session

    # ─── Recording helpers ─────────────────────────────────────────────

    def record_package(
        self,
        name: str,
        was_pre_existing: bool,
        action: str,
        status: str,
        detail: str = "",
        error_context: Optional[Dict[str, Any]] = None,
    ):
        """
        Record the state and outcome for a system package.

        Parameters
        ----------
        name:
            Package identifier, e.g. ``"mpv"``, ``"ffsubsync"``.
        was_pre_existing:
            ``True`` if the package was already installed *before* this run.
        action:
            ``"install"``, ``"uninstall"``, ``"skip"``, or ``"none"``.
        status:
            ``"ok"``, ``"failed"``, or ``"skipped"``.
        detail:
            Optional human-readable note.
        error_context:
            Optional dictionary with error details (type, traceback, env).
        """
        entry: Dict[str, Any] = {
            "was_pre_existing": was_pre_existing,
            "action": action,
            "status": status,
            "detail": detail,
            "recorded_at": _now_iso(),
        }
        if error_context:
            entry["error_context"] = error_context
            
        self._require_session()["packages"][name] = entry
        self.save()

    def record_file(
        self,
        path: str,
        operation: str,
        status: str,
        detail: str = "",
        backup_path: Optional[str] = None,
        error_context: Optional[Dict[str, Any]] = None,
    ):
        """
        Record a file or directory operation.

        Parameters
        ----------
        path:
            Absolute path of the affected file / directory.
        operation:
            ``"copy"``, ``"modify"``, ``"delete"``, ``"backup"``, ``"create"``, ``"symlink"``.
        status:
            ``"ok"`` or ``"failed"``.
        detail:
            Optional note (e.g. number of files, error message).
        backup_path:
            If a backup copy was made, its path.
        error_context:
            Optional dictionary with error details (type, traceback, env).
        """
        entry: Dict[str, Any] = {
            "path": path,
            "operation": operation,
            "status": status,
            "detail": detail,
            "timestamp": _now_iso(),
        }
        if backup_path:
            entry["backup_path"] = backup_path
        if error_context:
            entry["error_context"] = error_context
            
        self._require_session()["files"].append(entry)
        self.save()

    def record_backup(self, backup_path: str):
        """Record a config-directory backup."""
        self._require_session()["backups"].append(
            {"path": backup_path, "created_at": _now_iso()}
        )
        self.save()

    # ─── Query helpers ─────────────────────────────────────────────────

    def get_pre_existing_packages(self) -> Dict[str, bool]:
        """
        Return ``{package_name: was_pre_existing}`` based on the **first**
        install/update session that recorded each package.

        Packages absent from the log are treated as pre-existing (the safe
        conservative default — we never remove something we did not install).
        """
        seen: Dict[str, bool] = {}
        for session in self._data["sessions"]:
            if session.get("operation") not in ("install", "update"):
                continue
            for name, info in session.get("packages", {}).items():
                if name not in seen:
                    # Default to True (pre-existing) if key is missing
                    seen[name] = info.get("was_pre_existing", True)
        return seen

    def get_packages_installed_by_us(self) -> List[str]:
        """Return names of packages that were NOT pre-existing and were
        successfully installed by this tool (safe to auto-uninstall)."""
        return [
            name
            for name, was_there in self.get_pre_existing_packages().items()
            if not was_there
        ]

    def get_latest_backup(self) -> Optional[str]:
        """Return the path of the most recently recorded backup."""
        candidates: List[tuple] = []
        for session in self._data["sessions"]:
            for bk in session.get("backups", []):
                path = bk.get("path", "")
                ts = bk.get("created_at", "")
                if path:
                    candidates.append((ts, path))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def sessions(self) -> List[Dict[str, Any]]:
        """Return a copy of all recorded sessions."""
        return list(self._data["sessions"])

    def generate_diagnostic_report(self) -> str:
        """
        Iterate latest session, collect all entries where status == "failed",
        group by category (packages/files), return formatted markdown string suitable for Rich rendering.
        """
        if not self._data.get("sessions"):
            return "No sessions available."
            
        latest = self._data["sessions"][-1]
        lines = []
        
        failed_pkgs = {k: v for k, v in latest.get("packages", {}).items() if v.get("status") == "failed"}
        if failed_pkgs:
            lines.append("[bold red]Failed Packages:[/bold red]")
            for k, v in failed_pkgs.items():
                err = v.get("error_context", {}).get("type", "")
                err_str = f" ({err})" if err else ""
                detail = v.get("detail", "")
                lines.append(f"  • [yellow]{k}[/yellow]: {detail}{err_str}")
                
        failed_files = [f for f in latest.get("files", []) if f.get("status") == "failed"]
        if failed_files:
            if lines:
                lines.append("")
            lines.append("[bold red]Failed Files:[/bold red]")
            for f in failed_files:
                path = f.get("path", "")
                op = f.get("operation", "")
                err = f.get("error_context", {}).get("type", "")
                err_str = f" ({err})" if err else ""
                detail = f.get("detail", "")
                lines.append(f"  • [yellow]{op}[/yellow] on {path}: {detail}{err_str}")
                
        if not lines:
            return "[green]No failures in latest session.[/green]"
            
        return "\n".join(lines)
