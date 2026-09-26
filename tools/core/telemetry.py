"""
telemetry.py — MPV JSON-IPC named pipe emitter and atomic state file persistence.
"""

import os
import sys
import json
import tempfile
from typing import Dict, Any, Optional


class TelemetryBus:
    """Dispatches download telemetry to MPV via JSON-IPC Named Pipe and writes atomic state files."""

    def __init__(self, state_file: Optional[str] = None, mpv_pipe: Optional[str] = None):
        self.state_file = state_file
        self.mpv_pipe = mpv_pipe or os.environ.get("MPV_IPC_PIPE")

    def emit(self, payload: Dict[str, Any]):
        """Emit telemetry event both to MPV IPC and local atomic state file."""
        # 1. Update atomic state file (crash recovery fallback)
        if self.state_file:
            self.write_state_file(payload)

        # 2. Push directly into MPV IPC named pipe if connected
        if self.mpv_pipe:
            self.emit_to_mpv(payload)

    def write_state_file(self, data: Dict[str, Any]):
        """Atomically update state file."""
        if not self.state_file:
            return
        state_dir = os.path.dirname(os.path.abspath(self.state_file))
        os.makedirs(state_dir, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile("w", dir=state_dir, delete=False, encoding="utf-8") as tf:
                json.dump(data, tf, indent=2)
                temp_name = tf.name
            os.replace(temp_name, self.state_file)
        except Exception:
            pass

    def emit_to_mpv(self, payload: Dict[str, Any]):
        """Push telemetry into MPV over its IPC pipe without polling."""
        if not self.mpv_pipe:
            return
        try:
            line = json.dumps({
                "command": ["script-message-to", "toolbar", "download-progress", json.dumps(payload)]
            }) + "\n"

            if sys.platform == "win32":
                pipe_path = self.mpv_pipe
                if not pipe_path.startswith(r"\\.\pipe\\"):
                    pipe_path = r"\\.\pipe\\" + pipe_path
                with open(pipe_path, "wb", buffering=0) as p:
                    p.write(line.encode("utf-8"))
            else:
                import socket
                sock = socket.socket(socket.AF_UNIX)
                sock.connect(self.mpv_pipe)
                sock.sendall(line.encode("utf-8"))
                sock.close()
        except Exception:
            # If MPV was closed or pipe not ready, don't crash
            pass
