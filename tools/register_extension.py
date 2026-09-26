#!/usr/bin/env python3
"""
register_extension.py — Automatically register MPV Companion Extension and Native Host in Windows Registry.

Works for Brave, Google Chrome, and Microsoft Edge under HKCU (requires zero admin elevation).
Derives a persistent, deterministic Extension ID via 2048-bit RSA key pair.
"""

from __future__ import annotations

import os
import sys
import json
import base64
import hashlib
import winreg
from pathlib import Path

# Setup encoding safety for Windows terminal
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

root_dir = Path(__file__).resolve().parent.parent
ext_dir = root_dir / "tools" / "extension"
native_dir = root_dir / "tools" / "native_host"
manifest_path = ext_dir / "manifest.json"
key_pem_path = native_dir / "key.pem"
host_manifest_path = native_dir / "com.mpv.cookiesync.json"
host_bat_path = native_dir / "cookie_sync.bat"

def log(msg: str):
    print(f"[MPV Extension Installer] {msg}")

def ensure_key_and_manifest() -> tuple[str, str]:
    """Ensure RSA private key exists, generate if missing, and return base64 pubkey + extension id."""
    try:
        from Cryptodome.PublicKey import RSA
    except ImportError:
        try:
            from Crypto.PublicKey import RSA  # type: ignore
        except ImportError:
            log("Error: pycryptodome/pycryptodomex is required. Please install via uv/pip.")
            sys.exit(1)

    native_dir.mkdir(parents=True, exist_ok=True)
    ext_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate or load RSA private key
    if not key_pem_path.exists():
        log("Generating persistent 2048-bit RSA key pair for stable Extension ID...")
        key = RSA.generate(2048)
        key_pem = key.export_key(format='PEM')
        key_pem_path.write_bytes(key_pem)
        log(f"Key saved to {key_pem_path}")
    else:
        key_pem = key_pem_path.read_bytes()
        key = RSA.import_key(key_pem)

    # 2. Get public key in DER format
    pub_der = key.publickey().export_key(format='DER')
    pub_b64 = base64.b64encode(pub_der).decode('utf-8')

    # 3. Calculate deterministic Extension ID
    sha = hashlib.sha256(pub_der).hexdigest()
    ext_id = "".join(chr(int(c, 16) + 97) for c in sha[:32])

    # 4. Inject key into manifest.json
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["key"] = pub_b64
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        log(f"Updated manifest.json. Deterministic Extension ID: {ext_id}")

    return pub_b64, ext_id

def create_native_host_manifest(ext_id: str):
    """Generate the Native Messaging Host manifest JSON with absolute path to batch launcher."""
    host_manifest = {
        "name": "com.mpv.cookiesync",
        "description": "MPV and yt-dlp Automatic Cookie Sync Host",
        "path": str(host_bat_path),
        "type": "stdio",
        "allowed_origins": [
            f"chrome-extension://{ext_id}/"
        ]
    }
    host_manifest_path.write_text(json.dumps(host_manifest, indent=2), encoding="utf-8")
    log(f"Generated Native Messaging Host manifest: {host_manifest_path}")

def register_browser_extension(browser_name: str, reg_key_path: str, ext_id: str, ext_path: str):
    """Write unpacked extension path to HKCU\\Software\\...\\Extensions\\<id>."""
    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            f"{reg_key_path}\\{ext_id}",
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "path", 0, winreg.REG_SZ, ext_path)
        winreg.SetValueEx(key, "version", 0, winreg.REG_SZ, "1.0")
        winreg.CloseKey(key)
        log(f"Extension registered in {browser_name} registry.")
    except Exception as e:
        log(f"Notice: register {browser_name} extension: {e}")

def register_native_messaging_host(browser_name: str, reg_key_path: str, host_json_path: str):
    """Register Native Messaging Host under HKCU\\Software\\...\\NativeMessagingHosts\\com.mpv.cookiesync."""
    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            f"{reg_key_path}\\com.mpv.cookiesync",
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, host_json_path)
        winreg.CloseKey(key)
        log(f"Native host registered in {browser_name} registry.")
    except Exception as e:
        log(f"Notice: register {browser_name} native host: {e}")

def main():
    log("Registering MPV Media & Cookie Companion in Chromium browsers...")
    _, ext_id = ensure_key_and_manifest()
    create_native_host_manifest(ext_id)

    ext_folder = str(ext_dir)
    host_json = str(host_manifest_path)

    # Browser targets (Brave, Chrome, Edge)
    targets = [
        ("Brave Browser", "Software\\BraveSoftware\\Brave-Browser"),
        ("Google Chrome", "Software\\Google\\Chrome"),
        ("Microsoft Edge", "Software\\Microsoft\\Edge"),
    ]

    for browser_name, base_key in targets:
        register_browser_extension(browser_name, f"{base_key}\\Extensions", ext_id, ext_folder)
        register_native_messaging_host(browser_name, f"{base_key}\\NativeMessagingHosts", host_json)

    log("MPV Companion registered successfully. Ready for plug-and-play browsing!")

if __name__ == "__main__":
    main()
