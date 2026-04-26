"""
registry.py — The single source of truth.

Maps every third-party script/shader to its upstream GitHub source,
fetch strategy, file layout, and dependency chain.
"""

SCRIPTS = [
    {
        "name": "uosc",
        "desc": "Modern on-screen UI for mpv",
        "source": {
            "type": "github_release",
            "repo": "tomasklaen/uosc",
            "asset_pattern": "uosc.zip",
            "pin": None,
        },
        "install": {
            "map": {"scripts/uosc/": "scripts/uosc/", "fonts/": "fonts/"},
        },
        "config": "uosc.conf",
        "sys_deps": [],
        "script_deps": ["thumbfast"],
    },
    {
        "name": "thumbfast",
        "desc": "On-the-fly thumbnail generator",
        "source": {
            "type": "github_raw",
            "repo": "po5/thumbfast",
            "branch": "master",
            "files": [{"src": "thumbfast.lua", "dest": "scripts/thumbfast.lua"}],
        },
        "config": None,
        "sys_deps": [],
        "script_deps": [],
    },
    {
        "name": "SmartSkip",
        "desc": "Smart chapter/silence skip & auto-skip",
        "source": {
            "type": "github_raw",
            "repo": "Eisa01/mpv-scripts",
            "branch": "master",
            "files": [{"src": "scripts/SmartSkip.lua", "dest": "scripts/SmartSkip.lua"}],
        },
        "config": "SmartSkip.conf",
        "sys_deps": [],
        "script_deps": [],
    },
    {
        "name": "sponsorblock",
        "desc": "Skip YouTube sponsored segments",
        "source": {
            "type": "github_raw",
            "repo": "po5/mpv_sponsorblock",
            "branch": "master",
            "files": [
                {"src": "sponsorblock.lua", "dest": "scripts/sponsorblock.lua"},
                {"src": "sponsorblock_shared/main.lua", "dest": "scripts/sponsorblock_shared/main.lua"},
                {"src": "sponsorblock_shared/sponsorblock.py", "dest": "scripts/sponsorblock_shared/sponsorblock.py"},
            ],
        },
        "config": None,
        "sys_deps": ["python"],
        "script_deps": [],
    },
    {
        "name": "autosubsync",
        "desc": "Automatic subtitle synchronization",
        "source": {
            "type": "github_raw",
            "repo": "joaquintorres/autosubsync-mpv",
            "branch": "v0.33",
            "files": [
                {"src": "autosubsync.lua", "dest": "scripts/autosubsync/autosubsync.lua"},
                {"src": "helpers.lua", "dest": "scripts/autosubsync/helpers.lua"},
                {"src": "main.lua", "dest": "scripts/autosubsync/main.lua"},
                {"src": "menu.lua", "dest": "scripts/autosubsync/menu.lua"},
                {"src": "subtitle.lua", "dest": "scripts/autosubsync/subtitle.lua"},
            ],
        },
        "config": "autosubsync.conf",
        "config_is_template": True,
        "sys_deps": ["ffmpeg", "ffsubsync"],
        "optional_deps": ["alass"],
        "script_deps": [],
    },
    {
        "name": "autoload",
        "desc": "Auto-load directory files into playlist",
        "source": {
            "type": "github_raw",
            "repo": "mpv-player/mpv",
            "branch": "master",
            "files": [{"src": "TOOLS/lua/autoload.lua", "dest": "scripts/autoload.lua"}],
        },
        "config": None,
        "sys_deps": [],
        "script_deps": [],
    },
    {
        "name": "memo",
        "desc": "Recent files / watch history menu",
        "source": {
            "type": "github_raw",
            "repo": "po5/memo",
            "branch": "master",
            "files": [{"src": "memo.lua", "dest": "scripts/memo.lua"}],
        },
        "config": "memo.conf",
        "sys_deps": [],
        "script_deps": ["uosc"],
    },
    {
        "name": "evafast",
        "desc": "Hybrid fast-forward and seeking",
        "source": {
            "type": "github_raw",
            "repo": "po5/evafast",
            "branch": "master",
            "files": [{"src": "evafast.lua", "dest": "scripts/evafast.lua"}],
        },
        "config": "evafast.conf",
        "sys_deps": [],
        "script_deps": ["uosc"],
    },
    {
        "name": "pause-when-minimize",
        "desc": "Pause playback on window minimize",
        "source": {
            "type": "github_raw",
            "repo": "mpv-player/mpv",
            "branch": "master",
            "files": [{"src": "TOOLS/lua/pause-when-minimize.lua", "dest": "scripts/pause-when-minimize.lua"}],
        },
        "config": None,
        "sys_deps": [],
        "script_deps": [],
    },
]

SHADERS = {
    "name": "Anime4K",
    "desc": "Real-time anime upscaling shaders",
    "source": {
        "type": "github_release",
        "repo": "bloc97/Anime4K",
        "asset_pattern": "Anime4K_v",
        "pin": "v4.0.1",
    },
    "dest": "shaders/",
    "extensions": [".glsl"],
}

SYSTEM_DEPS = {
    # ── Category A — CLI executables ── NEVER pip ──────────────
    "mpv": {
        "windows": {
            "method": "github_asset",
            "repo": "zhongfly/mpv-winbuild",
            # Asset selection: v3 (AVX2) vs regular decided at install time
            "install_dir": "C:\\Program Files\\mpv",
        },
        "arch":    {"method": "pacman", "pkg": "mpv"},
        "ubuntu":  {"method": "apt",    "pkg": "mpv"},
        "fedora":  {"method": "dnf",    "pkg": "mpv"},
        "macos":   {"method": "brew",   "pkg": "mpv"},
        "verify":  ["mpv", "--version"],
    },
    "yt-dlp": {
        "windows": {"method": "winget", "id": "yt-dlp.yt-dlp"},
        "arch":    {"method": "pacman", "pkg": "yt-dlp"},
        "ubuntu":  {"method": "apt",    "pkg": "yt-dlp"},        # was pip
        "fedora":  {"method": "dnf",    "pkg": "yt-dlp"},
        "macos":   {"method": "brew",   "pkg": "yt-dlp"},
        "verify":  ["yt-dlp", "--version"],
    },
    "ffmpeg": {
        "windows": {"method": "winget", "id": "Gyan.FFmpeg"},
        "arch":    {"method": "pacman", "pkg": "ffmpeg"},
        "ubuntu":  {"method": "apt",    "pkg": "ffmpeg"},
        "fedora":  {"method": "dnf",    "pkg": "ffmpeg"},
        "macos":   {"method": "brew",   "pkg": "ffmpeg"},
        "verify":  ["ffmpeg", "-version"],
    },
    "python": {
        "windows": {"method": "winget",  "id": "Python.Python.3.11"},
        "arch":    {"method": "pacman",  "pkg": "python"},
        "ubuntu":  {"method": "apt",     "pkg": "python3"},
        "fedora":  {"method": "dnf",     "pkg": "python3"},
        "macos":   {"method": "brew",    "pkg": "python@3"},
        "verify":  ["python", "--version"],
        "verify_alt": ["python3", "--version"],
    },
    "ffsubsync": {
        "arch":    {"method": "aur", "pkg": "python-ffsubsync", "fallback_pkg": "ffsubsync"},
        "ubuntu":  {"method": "pipx", "pkg": "ffsubsync"},        # pipx used as fallback — no native package available
        "fedora":  {"method": "pipx", "pkg": "ffsubsync"},
        "macos":   {"method": "pipx", "pkg": "ffsubsync"},
        "windows": {"method": "pipx", "pkg": "ffsubsync"},
        "verify":  ["ffsubsync", "--version"],
    },
    "alass": {
        "arch":    {"method": "aur", "pkg": "alass-bin", "fallback_pkg": "alass"},
        "windows": {"method": "manual", "url": "https://github.com/kaegi/alass/releases"},
        "verify":  ["alass", "--version"],
    },
}

import platform

MPV_PROFILE_DEFAULT = "windows-like" if platform.system() == "Windows" else "linux-like"

MPV_EXPERIENCE_PROFILES = {
    # Cross-platform baseline intended to make behavior as consistent as possible.
    # Per-OS technical compatibility fallbacks are applied in deployer.py.
    "windows-like": {
        "gpu_api": "d3d11",
        "hwdec": "auto-safe",
        # Empty means no explicit override; let mpv pick a suitable context.
        "gpu_context": "",
        "vo": "gpu-next",
    },
    "linux-like": {
        "gpu_api": "vulkan",
        "hwdec": "auto-safe",
        "gpu_context": "",
        "vo": "gpu-next",
    },
    # Keeps old platform-specific behavior.
    "native": {},
}

PLATFORM_NATIVE_MPV_DEFAULTS = {
    "windows": {
        "gpu_api": "d3d11",
        "hwdec": "auto-safe",
        "gpu_context": "",
        "vo": "gpu-next",
    },
    "arch": {
        "gpu_api": "vulkan",
        "hwdec": "auto-safe",
        "gpu_context": "auto",
        "vo": "gpu-next",
    },
    "ubuntu": {
        "gpu_api": "vulkan",
        "hwdec": "auto-safe",
        "gpu_context": "",
        "vo": "gpu-next",
    },
    "macos": {
        "gpu_api": "auto",
        "hwdec": "videotoolbox",
        "gpu_context": "",
        "vo": "gpu-next",
    },
}

PLATFORM_REQUIRED_DEFAULTS = {
    # Platform-required values that are not user experience choices.
    "windows": {
        "shader_sep": ";",
        "config_dir": "%APPDATA%/mpv",
        "ffmpeg_path": "auto",
        "ffsubsync_path": "auto",
        "alass_path": "auto",
    },
    "arch": {
        "shader_sep": ":",
        "config_dir": "~/.config/mpv",
        "ffmpeg_path": "/usr/bin/ffmpeg",
        "ffsubsync_path": "auto",
        "alass_path": "auto",
    },
    "ubuntu": {
        "shader_sep": ":",
        "config_dir": "~/.config/mpv",
        "ffmpeg_path": "/usr/bin/ffmpeg",
        "ffsubsync_path": "auto",
        "alass_path": "auto",
    },
    "macos": {
        "shader_sep": ":",
        "config_dir": "~/.config/mpv",
        "ffmpeg_path": "ffmpeg",
        "ffsubsync_path": "auto",
        "alass_path": "auto",
    },
}

# Backward-compatible merged view for legacy callers.
# NOTE: treat as read-only compatibility data.
PLATFORM_DEFAULTS = {
    key: {**PLATFORM_NATIVE_MPV_DEFAULTS[key], **PLATFORM_REQUIRED_DEFAULTS[key]}
    for key in PLATFORM_NATIVE_MPV_DEFAULTS
}
