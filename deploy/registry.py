"""
registry.py — The single source of truth.

Maps every third-party script/shader to its upstream GitHub source,
fetch strategy, file layout, and dependency chain.
"""

import os

WINDOWS_PROGRAM_FILES = os.environ.get("ProgramFiles", "C:\\Program Files")
WINDOWS_MPV_DIR = os.path.join(WINDOWS_PROGRAM_FILES, "mpv")
WINDOWS_FFMPEG_DIR = os.path.join(WINDOWS_MPV_DIR, "ffmpeg")
WINDOWS_YTDLP_DIR = os.path.join(WINDOWS_MPV_DIR, "yt-dlp")
WINDOWS_UV_DIR = os.path.join(WINDOWS_MPV_DIR, "uv")
WINDOWS_FFSUBSYNC_DIR = os.path.join(WINDOWS_MPV_DIR, "ffsubsync")
WINDOWS_ALASS_DIR = os.path.join(WINDOWS_MPV_DIR, "alass")
WINDOWS_AUTOHOTKEY_DIR = os.path.join(WINDOWS_MPV_DIR, "autohotkey")
WINDOWS_FFMPEG_BIN_DIR = os.path.join(WINDOWS_FFMPEG_DIR, "bin")
# Standalone GitHub binaries (alass, yt-dlp on distros with frozen packages)
# go into the user's own PATH dir; Ubuntu/Fedora add ~/.local/bin to PATH
# via the profile when it exists. The installer also symlinks into
# /usr/local/bin when the current PATH cannot see the binary yet.
LINUX_BIN_DIR = os.path.expanduser("~/.local/bin")
LINUX_ALASS_DIR = LINUX_BIN_DIR

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
                {
                    "src": "sponsorblock_shared/main.lua",
                    "dest": "scripts/sponsorblock_shared/main.lua",
                },
                {
                    "src": "sponsorblock_shared/sponsorblock.py",
                    "dest": "scripts/sponsorblock_shared/sponsorblock.py",
                },
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
            "pin": "v0.40.0",
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
            "pin": "v0.40.0",
            "files": [
                {
                    "src": "TOOLS/lua/pause-when-minimize.lua",
                    "dest": "scripts/pause-when-minimize.lua",
                }
            ],
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

ANIME4K_CHAINS = {
    "off": "",
    "fast": "Anime4K_Clamp_Highlights;Anime4K_Upscale_CNN_x2_S;Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Upscale_CNN_x2_S",
    "A": "Anime4K_Clamp_Highlights;Anime4K_Restore_CNN_VL;Anime4K_Upscale_CNN_x2_VL;Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Upscale_CNN_x2_M",
    "A+A": "Anime4K_Clamp_Highlights;Anime4K_Restore_CNN_VL;Anime4K_Upscale_CNN_x2_VL;Anime4K_Restore_CNN_M;Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Upscale_CNN_x2_M",
    "B": "Anime4K_Clamp_Highlights;Anime4K_Restore_CNN_Soft_VL;Anime4K_Upscale_CNN_x2_VL;Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Upscale_CNN_x2_M",
    "B+B": "Anime4K_Clamp_Highlights;Anime4K_Restore_CNN_Soft_VL;Anime4K_Upscale_CNN_x2_VL;Anime4K_Restore_CNN_Soft_M;Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Upscale_CNN_x2_M",
    "C": "Anime4K_Clamp_Highlights;Anime4K_Upscale_Denoise_CNN_x2_VL;Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Upscale_CNN_x2_M",
    "C+A": "Anime4K_Clamp_Highlights;Anime4K_Upscale_Denoise_CNN_x2_VL;Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Restore_CNN_M;Anime4K_Upscale_CNN_x2_M",
}

SCALER_TIERS = {
    "light": {"scale": "spline36", "cscale": "spline36", "dscale": "mitchell"},
    "balanced": {"scale": "ewa_lanczos", "cscale": "spline36", "dscale": "mitchell"},
    "quality": {"scale": "ewa_lanczos", "cscale": "ewa_lanczos", "dscale": "mitchell"},
}

SYSTEM_DEPS = {
    # ── Category A — CLI executables ── NEVER pip ──────────────
    "mpv": {
        "windows": {
            "method": "github_asset",
            # PRIMARY: zhongfly publishes daily builds with date+commit tags
            # like "2026-05-15-4498c0ff81". The old pin "2025-01-15" was a
            # plain date that has never existed as a real tag → 404.
            # Leaving pin=None means "use latest release", which is the
            # right default for daily-build repos. Users can override the
            # tag with --mpv-version <tag> (existing CLI flag).
            "repo": "zhongfly/mpv-winbuild",
            "pin": None,
            "fallback_repo": "shinchiro/mpv-winbuild-cmake",
            # WHY per-repo asset patterns:
            # zhongfly names assets as: mpv-x86_64[-v3]-YYYYMMDD-git-HASH.7z
            # shinchiro names assets as: mpv-x86_64[-v3]-git-HASH.7z (no date)
            # A single regex cannot match both — the old code's `\d{8}` made
            # the shinchiro fallback effectively dead.
            "asset_patterns": {
                "zhongfly/mpv-winbuild": {
                    "avx2": r"^mpv-x86_64-v3-\d{8}-git-[0-9a-f]+\.7z$",
                    "plain": r"^mpv-x86_64-\d{8}-git-[0-9a-f]+\.7z$",
                },
                "shinchiro/mpv-winbuild-cmake": {
                    "avx2": r"^mpv-x86_64-v3-git-[0-9a-f]+\.7z$",
                    "plain": r"^mpv-x86_64-git-[0-9a-f]+\.7z$",
                },
            },
            # Very loose fallback if both repos change naming in the future.
            "asset_pattern_generic": r"^mpv-x86_64(?:-v3)?(?:-\d{8})?-git-[0-9a-f]+\.7z$",
            "install_dir": WINDOWS_MPV_DIR,
            "ensure_in_dir": WINDOWS_MPV_DIR,
            "bin_names": ["mpv.exe"],
        },
        # prefer_optimized_repo: on CachyOS the deployer enables the
        # x86-64-v3/v4 optimized repos first so a plain `pacman -S mpv` pulls
        # the AVX2/AVX512 rebuild instead of the generic Arch build.
        "arch": {"method": "pacman", "pkg": "mpv", "prefer_optimized_repo": True},
        # Ubuntu/Mint apt repos ship ancient mpv (Noble: 0.37) that fails on
        # clipboard-monitor and sub-ass-use-video-data.  "ppa" adds
        # ppa:ubuntuhandbook1/mpv for the latest stable build (installer.py).
        "ubuntu": {"method": "ppa", "pkg": "mpv"},
        "fedora": {"method": "dnf", "pkg": "mpv"},
        "macos": {"method": "brew", "pkg": "mpv"},
        "verify": ["mpv", "--version"],
    },
    "yt-dlp": {
        # arch keeps pacman (tracks current). Windows/Ubu-class distros:
        # the standalone GitHub binary, refreshed at most every 7 days —
        # YouTube changes break old extractors weekly and apt/fedora ship
        # frozen ancient versions.
        "windows": {
            "method": "direct_url",
            "url": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
            "install_dir": WINDOWS_YTDLP_DIR,
            "dest_name": "yt-dlp.exe",
            "ensure_in_dir": WINDOWS_YTDLP_DIR,
            "bin_names": ["yt-dlp.exe"],
            "refresh_days": 7,
        },
        "arch": {"method": "pacman", "pkg": "yt-dlp", "prefer_optimized_repo": True},
        # x86_64 hosts only: yt-dlp_linux is the official standalone build
        # (bundle includes its own Python). ARM hosts would want
        # yt-dlp_linux_aarch64 instead — not a target machine today.
        "ubuntu": {
            "method": "github_release_file",
            "repo": "yt-dlp/yt-dlp",
            "asset_patterns": [r"^yt-dlp_linux$", r"^yt-dlp$"],
            "install_dir": LINUX_BIN_DIR,
            "dest_name": "yt-dlp",
            "refresh_days": 7,
        },
        "fedora": {
            "method": "github_release_file",
            "repo": "yt-dlp/yt-dlp",
            "asset_patterns": [r"^yt-dlp_linux$", r"^yt-dlp$"],
            "install_dir": LINUX_BIN_DIR,
            "dest_name": "yt-dlp",
            "refresh_days": 7,
        },
        "macos": {"method": "brew", "pkg": "yt-dlp"},
        "verify": ["yt-dlp", "--version"],
    },
    "ffmpeg": {
        "windows": {
            "method": "github_release_zip",
            "repo": "BtbN/FFmpeg-Builds",
            "asset_patterns": [
                r"^ffmpeg-master-latest-win64-gpl\.zip$",
                r"^ffmpeg-master-latest-win64-gpl-shared\.zip$",
                r"^ffmpeg-.*-win64-gpl\.zip$",
                r"^ffmpeg-.*-win64-gpl-shared\.zip$",
            ],
            "install_dir": WINDOWS_FFMPEG_DIR,
            "bin_subdir": "bin",
            "expected_bins": ["ffmpeg.exe", "ffprobe.exe", "ffplay.exe"],
            "ensure_in_dir": WINDOWS_FFMPEG_BIN_DIR,
            "bin_names": ["ffmpeg.exe"],
        },
        "arch": {"method": "pacman", "pkg": "ffmpeg", "prefer_optimized_repo": True},
        "ubuntu": {"method": "apt", "pkg": "ffmpeg"},
        "fedora": {"method": "dnf", "pkg": "ffmpeg"},
        "macos": {"method": "brew", "pkg": "ffmpeg"},
        "verify": ["ffmpeg", "-version"],
    },
    "python": {
        "windows": {"method": "winget", "id": "Python.Python.3.11"},
        "arch": {"method": "pacman", "pkg": "python", "prefer_optimized_repo": True},
        "ubuntu": {"method": "apt", "pkg": "python3"},
        "fedora": {"method": "dnf", "pkg": "python3"},
        "macos": {"method": "brew", "pkg": "python@3"},
        "verify": ["python", "--version"],
        "verify_alt": ["python3", "--version"],
    },
    "aria2": {
        "windows": {"method": "winget", "id": "aria2.aria2"},
        "arch": {"method": "pacman", "pkg": "aria2", "prefer_optimized_repo": True},
        "ubuntu": {"method": "apt", "pkg": "aria2"},
        "fedora": {"method": "dnf", "pkg": "aria2"},
        "macos": {"method": "brew", "pkg": "aria2"},
        "verify": ["aria2c", "--version"],
    },
    "ffsubsync": {
        "arch": {"method": "aur", "pkg": "python-ffsubsync", "fallback_pkg": "ffsubsync"},
        "ubuntu": {
            "method": "uv_tool",
            "pkg": "ffsubsync",
            "uv_python": "3.11",
            "uv_no_fallback": True,
        },
        "fedora": {
            "method": "uv_tool",
            "pkg": "ffsubsync",
            "uv_python": "3.11",
            "uv_no_fallback": True,
        },
        "macos": {
            "method": "uv_tool",
            "pkg": "ffsubsync",
            "uv_python": "3.11",
            "uv_no_fallback": True,
        },
        "windows": {
            "method": "uv_tool",
            "pkg": "ffsubsync",
            "bin_dir": WINDOWS_FFSUBSYNC_DIR,
            "ensure_in_dir": WINDOWS_FFSUBSYNC_DIR,
            "bin_names": ["ffsubsync.exe", "ffsubsync", "ffsubsync.cmd"],
            "uv_python": "3.11",
            "uv_no_fallback": True,
        },
        "verify": ["ffsubsync", "--version"],
    },
    "alass": {
        # Arch/CachyOS: AUR build first; the prebuilt GitHub release binary is
        # the fallback when no AUR helper exists (or the build fails).
        "arch": {
            "method": "aur",
            "pkg": "alass-bin",
            "fallback_pkg": "alass",
            "fallback": {
                "method": "github_release_file",
                "repo": "kaegi/alass",
                "asset_patterns": [r"^alass-linux64$", r"^alass-lin.*64.*$"],
                "install_dir": LINUX_ALASS_DIR,
                "dest_name": "alass",
            },
        },
        # No alass package exists in Ubuntu/Fedora repos. kaegi ships a
        # standalone Linux binary in the releases (a Rust build, no extra
        # runtime deps).
        "ubuntu": {
            "method": "github_release_file",
            "repo": "kaegi/alass",
            "asset_patterns": [r"^alass-linux64$", r"^alass-lin.*64.*$"],
            "install_dir": LINUX_ALASS_DIR,
            "dest_name": "alass",
        },
        "fedora": {
            "method": "github_release_file",
            "repo": "kaegi/alass",
            "asset_patterns": [r"^alass-linux64$", r"^alass-lin.*64.*$"],
            "install_dir": LINUX_ALASS_DIR,
            "dest_name": "alass",
        },
        "windows": {
            "method": "github_release_zip",
            "repo": "kaegi/alass",
            "asset_patterns": [
                r"^alass-.*windows.*x64.*\.zip$",
                r"^alass-.*win64.*\.zip$",
                r"^alass-.*win.*\.zip$",
            ],
            "install_dir": WINDOWS_ALASS_DIR,
            "expected_bins": ["alass.exe", "alass-cli.exe"],
            "ensure_in_dir": WINDOWS_ALASS_DIR,
            "bin_names": ["alass.exe", "alass-cli.exe"],
        },
        "verify": ["alass", "--version"],
    },
    "uv": {
        "windows": {
            "method": "github_release_zip",
            "repo": "astral-sh/uv",
            "asset_patterns": [
                r"^uv-x86_64-pc-windows-msvc\.zip$",
                r"^uv-.*windows.*x86_64.*\.zip$",
            ],
            "install_dir": WINDOWS_UV_DIR,
            "expected_bins": ["uv.exe"],
            "ensure_in_dir": WINDOWS_UV_DIR,
            "bin_names": ["uv.exe"],
        },
        "arch": {"method": "uv"},
        "ubuntu": {"method": "uv"},
        "fedora": {"method": "uv"},
        "macos": {"method": "uv"},
        "verify": ["uv", "--version"],
    },
    "autohotkey": {
        "windows": {
            "method": "github_release_zip",
            "repo": "AutoHotkey/AutoHotkey",
            "asset_patterns": [
                r"^AutoHotkey_.*\.zip$",
            ],
            "install_dir": WINDOWS_AUTOHOTKEY_DIR,
            "expected_bins": ["AutoHotkey64.exe"],
            "ensure_in_dir": WINDOWS_AUTOHOTKEY_DIR,
            "bin_names": ["AutoHotkey64.exe"],
        },
        "verify": ["AutoHotkey64.exe", "/?"],
    },
}

import platform

MPV_PROFILE_DEFAULT = "windows-like" if platform.system() == "Windows" else "linux-like"

# ─── mpv version policy ──────────────────────────────────────────────────
# The templates use options that only exist in recent mpv: clipboard-monitor
# landed in 0.40, sub-ass-use-video-data in 0.39.  Instead of forking the
# config per distro release, the installer upgrades mpv itself until it meets
# this floor: on Ubuntu/Mint it adds ppa:ubuntuhandbook1/mpv (latest stable
# .debs for 22.04/24.04/25.x, classic packages not sandboxed); Arch/Fedora/
# macOS distro packages already track upstream; Windows always installs the
# latest zhongfly daily build.
MPV_MINIMUM_VERSION = (0, 40, 0)

MPV_EXPERIENCE_PROFILES = {
    # Cross-platform baseline intended to make behavior as consistent as possible.
    # Per-OS technical compatibility fallbacks are applied in deployer.py.
    "windows-like": {
        "gpu_api": "d3d11",
        "hwdec": "d3d11va",
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
        "hwdec": "d3d11va",
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
    "fedora": {
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
    "fedora": {
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
