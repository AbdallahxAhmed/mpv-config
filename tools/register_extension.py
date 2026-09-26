#!/usr/bin/env python3
"""
register_extension.py — Automatically pack and register MPV Companion Extension and Native Host in Windows Registry.

Works for Helium, Brave, Google Chrome, and Microsoft Edge under HKCU (zero admin elevation).
Derives a persistent, deterministic Extension ID via 2048-bit RSA key pair.
Generates valid CRX3 package and registers in Windows Registry.
"""

from __future__ import annotations

import os
import sys
import json
import base64
import shutil
import hashlib
import winreg
import subprocess
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
key_pkcs8_path = native_dir / "key_pkcs8.pem"
crx_path = root_dir / "tools" / "extension.crx"
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
        key_pkcs8_path.write_bytes(key.export_key(format='PEM', pkcs=8))
        log(f"Key saved to {key_pem_path}")
    else:
        key_pem = key_pem_path.read_bytes()
        key = RSA.import_key(key_pem)
        if not key_pkcs8_path.exists():
            key_pkcs8_path.write_bytes(key.export_key(format='PEM', pkcs=8))

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
        log(f"Deterministic Extension ID: {ext_id}")

    return pub_b64, ext_id

def find_chromium_binary() -> str | None:
    """Find any available Chromium browser executable to pack the extension."""
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\imput\Helium\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def pack_crx():
    """Pack extension into a signed .crx file using headless Chromium."""
    browser_bin = find_chromium_binary()
    if not browser_bin:
        log("Notice: No Chromium binary found to pack CRX. Using directory registration.")
        return

    key_to_use = str(key_pkcs8_path if key_pkcs8_path.exists() else key_pem_path)
    cmd = [
        browser_bin,
        "--headless=new",
        f"--pack-extension={ext_dir}",
        f"--pack-extension-key={key_to_use}"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if crx_path.exists():
            log(f"Successfully packed CRX extension: {crx_path} ({crx_path.stat().st_size} bytes)")
    except Exception as e:
        log(f"Notice: CRX packing attempt: {e}")

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

def register_browser_extension(browser_name: str, reg_key_path: str, ext_id: str, target_path: str):
    """Write extension path (CRX or folder) to HKCU\\Software\\...\\Extensions\\<id>."""
    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            f"{reg_key_path}\\{ext_id}",
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "path", 0, winreg.REG_SZ, target_path)
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
    pack_crx()
    create_native_host_manifest(ext_id)

    target_path = str(crx_path) if crx_path.exists() else str(ext_dir)
    host_json = str(host_manifest_path)

    # Browser targets (Helium, Brave, Chrome, Edge)
    targets = [
        ("Helium Browser", "Software\\Helium"),
        ("imput Helium", "Software\\imput\\Helium"),
        ("Google Chrome", "Software\\Google\\Chrome"),
        ("Brave Browser", "Software\\BraveSoftware\\Brave-Browser"),
        ("Microsoft Edge", "Software\\Microsoft\\Edge"),
    ]

    for browser_name, base_key in targets:
        register_browser_extension(browser_name, f"{base_key}\\Extensions", ext_id, target_path)
        register_native_messaging_host(browser_name, f"{base_key}\\NativeMessagingHosts", host_json)

    log("MPV Companion registered successfully. Ready for plug-and-play browsing!")

if __name__ == "__main__":
    main()
