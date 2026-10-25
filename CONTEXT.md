# CONTEXT.md — mpv-config project reference

> Stable briefing for any session (human or agent): structure, mechanisms, and the
> project's canonical vocabulary. For volatile state (open items, latest deploy
> status, acceptance checks) read `AGENTS.md` instead; for history read `CHANGELOG.md`.
> Last refreshed: 2026-10-25 · main @ `45aad00` (deployed 2026-10-23).

## 1. Canonical terms — use these names verbatim

| Term | Meaning |
| --- | --- |
| **source repo** | `~\Desktop\mpv-config-clean` (origin `github.com/AbdallahxAhmed/mpv-config`). ALL edits, tests and commits happen here. |
| **deploy clone** | `~\.mpv-config-deploy` — the editable pip install that points at the source repo; its `__editable__` finder beats `sys.path`, so `git pull` it before every test/import run. |
| **deployed config** | The live mpv config the user runs: `%APPDATA%\mpv` (Windows) / `~/.config/mpv` (Linux/macOS). |
| **deploy sequence** | commit → push → `git -C ~\.mpv-config-deploy pull --ff-only` → `python -m deploy.deployer --update` (interactive prompt: answer `y`). |
| **bootstrap scripts** | `install.ps1` (Windows) / `install.sh` (Linux/macOS): clone/update the deploy clone, pip-install it editable, run the installer. |
| **the CLI** | `mpv-config` = `python -m mpv_config`. Subcommands `install` `verify` `update` `rollback` `status` `sync-deps` `uninstall` forward to the deployer; `download` runs the in-process media downloader. |
| **the deployer** | `python -m deploy.deployer` — the engine: detect → plan → fetch → deps → deploy → verify. |
| **the registry** | `deploy/registry.py` — single source of truth: third-party `SCRIPTS`, `SHADERS`, `ANIME4K_CHAINS`, `SCALER_TIERS`, `SYSTEM_DEPS`, platform defaults. |
| **templates** | `config/mpv.conf.template` / `input.conf.template` — `{{PLACEHOLDER}}` substitution plus `{{#if NAME}}` conditional blocks, patched per platform by the deployer. |
| **staging dir** | Temp `.mpv-install-stage-*` — where the fetcher's downloads land first. |
| **prepared dir** | Temp `.mpv-install-prepared-*` — the complete final tree, assembled offline, then swapped in transactionally. |
| **asset dirs** | `scripts/`, `shaders/`, `fonts/` — the three deployable trees. |
| **custom scripts** | First-party Lua written for this config (repo `scripts/`, deployed as-is). |
| **vendored scripts** | Upstream Lua patched and tracked in the repo (`ytdl_hook`, `thumbfast`, `SmartSkip`). **Vendored patches win** over fetched upstream copies. |
| **fetched scripts** | Third-party Lua downloaded at install per the registry (`uosc`, `memo`, `evafast`, `sponsorblock`, `autosubsync`, `autoload`, `pause-when-minimize`). |
| **manifest** | `.deploy.lock.json` in the deployed config — versions + sha256 of every deployed file; `status`/`update` read it. |
| **audit log** | `.audit-log.json` — what the tool did; `uninstall` only removes packages the log shows this tool itself installed. |
| **backups** | `<config-dir>.backup.<timestamp>` snapshots next to the config dir; `rollback` restores the latest (or a named) one. |
| **cross-platform parity** | THE design rule: every OS gets the same performance, style, layout and functions — Windows, Linux (X11 & KDE Wayland) and macOS are equal targets, none is "first". One template set + one script set serve all platforms; only the plumbing differs (rendering backend, hwdec, package manager, config dir, OS-specific extras such as the Arabic layout twins). |
| **profiles** | mpv profiles in `mpv.conf`: `[live-action]` (light, no shaders), `[anime]` (Anime4K chain), `[wayland-144hz-fix]` (conditional, KDE Wayland only), `[protocol.https/http/ytdl]` (streaming cache). |
| **profile picker** | `scripts/profile_picker.lua` — offline anime detection; applies `[anime]` vs `[live-action]`; owns the Anime4K mode. |
| **Anime4K modes** | `off` `fast` `A` `A+A` `B` `B+B` `C` `C+A` — shader chains from `ANIME4K_CHAINS`; persisted in `script-opts/anime4k.conf`. |
| **default streaming quality** | `script-opts/stream_quality.conf` `default_quality` (shipped `1080`; `0` = uncapped) — single source of truth for the stream format. |
| **fast quality switch** | Toolbar-driven reload of an already-extracted stream (~1 s instead of a ~4–6 s yt-dlp round-trip). |
| **layout twins** | `src/mpv_config/layout_twins.py` — deploy-time generator appending same-physical-key Arabic-101 twin bindings to the deployed `input.conf` on every install/update (`c→ؤ a→ش h→ا n→ى ?→؟` singles; `b/G/B` as `ل-ا/ل-أ/ل-آ` key sequences). Only `g` is untwinnable (`ل` must stay unbound) and carries the `Ctrl+Shift+m` control-code backup (mechanics: see AGENTS.md). |
| **layout guard** | `scripts/keyboard_layout.lua` + `src/mpv_config/layout_guard.py` — the retired Windows keyboard hook (translated keys to US characters while mpv was focused). Opt-in via `script-opts/keyboard_layout.conf` `enabled=yes`; disabled by default since the twins. |
| **experience profiles** | `--mpv-profile`: `windows-like` / `linux-like` / `native` — the parity mechanism: the same gpu-next baseline everywhere, with only the rendering backend (d3d11 / Vulkan / VideoToolbox) swapped per platform. |
| **scaler tiers** | `--scaler-tier`: `light` / `balanced` / `quality`. |
| **display modes** | `--display-mode`: `fixed` (display-resample, default) / `vrr` (audio-sync, no interpolation). |

## 2. What this project is

`mpv-config` turns mpv into an out-of-the-box, high-fidelity player with
**cross-platform parity**: Windows, Linux (X11 & KDE Wayland) and macOS all get
the SAME performance, style, layout and functions — same uosc chrome (borderless
everywhere), same keybindings, same scripts, same quality stack (gpu-next/
libplacebo, platform-appropriate hwdec, Anime4K, 10-bit pipeline,
display-resample). Only the plumbing under them differs per OS. No hand-edited
config files; integrated streaming and downloading (hardened yt-dlp hook, fast
quality switch, plugin downloader, clipboard watcher, Chrome extension), all
deployed transactionally with snapshot/verify/rollback. v1.0.0 released 2026-10-07.

## 3. Repository layout

```text
config/          the deploy payload: mpv.conf.template, input.conf.template,
                 script-opts/*.conf (deployed verbatim) and *.conf.template
                 (patched at deploy: autosubsync, keyboard_layout)
scripts/         custom + vendored Lua; scripts/modules/ = shared Lua modules
                 (stream_policy.lua; main.lua is just a scanner marker)
deploy/          the deploy engine: registry, detector, fetcher, planner,
                 installer (system deps), transaction, verifier, audit_log, ui
src/mpv_config/  the pip package: cli/ (the mpv-config command), layout_guard.py
                 (Windows keyboard hook), downloaders/ (plugin framework)
tools/           download_worker.py (16-connection turbo), universal_downloader,
                 vtt_translate, yt_dlp_plugins/extractor (custom yt-dlp
                 extractors + _sitekit.py site-policy mixin), extension/ +
                 native_host/ (Chrome MV3 extension + cookie-sync host),
                 core/ (engine/session/clipboard/flaresolverr/registry/telemetry),
                 patch_uosc_*.py (post-deploy uosc patchers), apply_youtube_gui.py
tests/           Python unittest (≈420 cases) + tests/lua/ offline regressions
                 (run by tests/run_lua_tests.py)
specs/           Spec Kit: 003-installer-and-kde-fixes, 004-playback-performance
docs/            YOUTUBE_GUI.md, AUDIT.md (historical); README.md + README.ar.md
install.ps1/.sh  bootstrap scripts; Watch-Clipboard.cmd / Download-Video.cmd helpers
```

Deployed layout (`%APPDATA%\mpv`): `mpv.conf` + `mpv.conf.user` + `input.conf`,
`script-opts/`, `scripts/`, `shaders/`, `fonts/`, `shader_cache/`, `chapters/`,
`tools/` (helper binaries: yt-dlp.exe, ffmpeg.exe, download_worker.py,
vtt_translate.py, alass-cli.exe; aria2c.exe sits at the config root),
`.deploy.lock.json`, `.audit-log.json`, `keyboard_layout.log`, `memo-history.log`.

## 4. Environments, commands, constants

The agent's working machine is Windows — the constants below are THIS machine's,
not the project's scope. The project targets Windows/Linux/macOS equally and CI
runs all three.

- **Test suites:** `python -m unittest discover -s tests` and `python tests/run_lua_tests.py`.
  A rare transient single failure in the network-port tests (unreleased socket) —
  re-run before believing a failure.
- **mpv binary:** `C:\Program Files\mpv\mpv.exe`. **Test clip:**
  `%TEMP%\opencode\clip_1080p24_10bit.mkv`. **Test URL:** `http://127.0.0.1:8731/clip.mkv`.
- **Global yt-dlp config** (written by the deployer on Windows): `%APPDATA%\yt-dlp\config`
  — aria2c 16-connection downloads, 1080p ceiling. Custom extractor plugins deploy to
  `%APPDATA%\yt-dlp\plugins\` and `Program Files\mpv\yt_dlp_plugins\`.

## 5. Scripts — who does what

### UI
- **uosc** (fetched) — the entire mouse UI: timeline, top bar, volume, contextual
  menus. Configured by `script-opts/uosc.conf`; patched after deploy by
  `tools/patch_uosc_timeline_thumb.py` (timeline mouse-leave thumbnail cleanup).
- **player-toolbar.lua** (custom) — the toolbar brain: Stable Volume button, the
  **Quality menu** (rows marked `●` offered / `○` cap-only; per-row *Set as
  default* persists to `stream_quality.conf`, *Just this video* is session-only),
  and the fast quality switch trigger.
- **help_overlay.lua** (custom) — curated cheat sheet on `?` / `F9`.
- **sub_backdrop.lua** (custom) — Netflix-style subtitle backdrop toggle (`b`).
- **ytdl-sub-menu.lua** (custom) — on-demand YouTube captions menu (`Ctrl+c`);
  zero extraction work at file-load.

### Thumbnails
- **thumbfast.lua** (vendored, patched) — seekbar hover previews;
  `script-opts/thumbfast.conf`. Local patches: race-condition hardening;
  `is_same_video()` (same path OR duration±1.5 s + title) keeps the overlay alive
  across quality switches; no worker pre-spawn for network streams and a 16 MiB /
  1 s worker cache — the worker is a SECOND mpv, and pre-spawning it on a stream
  made it eat ~43% of the connection (playback fell ~2 s behind).

### Quality switching (streaming)
- **ytdl_hook.lua** (vendored, heavily extended) — mpv's built-in hook is off
  (`ytdl=no`); this one runs unconditionally. It builds `ytdl-format` from the
  default streaming quality, pins `youtube:player_client=default,-web` with a
  remembered unpinned retry, filters dubs (best bitrate per language/role), keeps
  the extraction cache across quality switches, and redirects a load of the
  canonical URL to the pre-resolved signed URL (`stream-open-filename`) — that
  redirect IS the fast quality switch, and it keeps the playlist on re-extractable
  canonical URLs instead of expiring GoogleVideo links.
- **player-toolbar.lua** — the menu and the switch trigger; snapshots and restores
  the extraction cache around the switch; falls back to a full reload if the
  signed URLs expired.
- **stream_policy.lua** (module, `scripts/modules/`) — pure metadata policy shared
  by the toolbar and the captions menu: URL validation, quality labels, format
  building. No mpv calls, no I/O.

### The rest
| Script | Role |
| --- | --- |
| `keyboard_layout.lua` (custom) | Spawns the layout guard after the first file-loaded; its conf carries the exact python command line (written by the installer). Disabled by default — the layout twins replaced it; flip `enabled=yes` for non-Arabic-101 layouts. |
| `profile_picker.lua` (custom) | Anime detection (offline signals: release group 4, user series list 4, jpn-audio+episode 3, jpn+multi 2, weaker singles; threshold 3) → applies `[anime]`/`[live-action]`; reads and persists the Anime4K mode. |
| `smart_motion.lua` (custom) | Runtime motion controller: per-file cadence analysis picks presentation clock/interpolation/tscale; `stream_web_parity` for streams; ships `oversample` at runtime (see traps). Toggle `Ctrl+Alt+m`. |
| `smart-paste.lua` (custom) | `Ctrl+V` paste-to-open / `Ctrl+Shift+V` to playlist, with URL normalization and local-file protection. |
| `SmartSkip.lua` (vendored) | Intro/outro/silence/chapter skipping (`>` `<` `?` `Ctrl+.` …). |
| `memo` (fetched) | Watch history menu (`h`). |
| `evafast` (fetched) | Hybrid fast-forward on `RIGHT`. |
| `sponsorblock` (fetched) | Segment marking/voting (`g` `G` `B` `Ctrl+B`). |
| `autosubsync` (fetched) | Subtitle sync menu (`n`); needs ffmpeg + ffsubsync (alass optional). |
| `autoload`, `pause-when-minimize` (fetched, pinned to mpv v0.40.0) | Directory autoplay; pause on minimize. |

**Precedence rule** (`tx.prepare_assets`): old live files survive (even unknown
ones) → fetched upstream overlays them → repo `scripts/` (custom + vendored)
overlays everything. Vendored patches always win.

## 6. Shaders (Anime4K) — how they are organized

- No shader files are tracked in the repo. The registry's `SHADERS` entry fetches
  the `bloc97/Anime4K` GitHub release, pinned **v4.0.1**, at install time; every
  `.glsl` archive member is flattened into the deployed config's `shaders/`
  (39 files live today).
- A **mode** (`A`, `A+A`, …) maps in `ANIME4K_CHAINS` to a semicolon-separated
  list of shader names. `_resolve_anime_chain()` expands each name to
  `~~/shaders/<name>.glsl`, joins with `;` (Windows) / `:` (Linux), and the result
  is baked into the `[anime]` profile's `glsl-shaders` line via the
  `{{ANIME_CHAIN}}` template placeholder.
- **Install-time choice**: interactive installs ask which mode to ship (or pass
  `--anime-preset`); the answer seeds `script-opts/anime4k.conf` (`mode=A`
  default). An existing `anime4k.conf` is the user's own and is never rewritten.
- **Runtime**: `profile_picker.lua` reads `anime4k.conf` whenever it applies the
  `[anime]` profile. `Ctrl+1..6` select modes, `Ctrl+0` = off, `Ctrl+g` cycles,
  `Ctrl+Shift+g` forces manual override of the anime detection; every choice is
  persisted and survives restarts.
- `[anime]` also drops `scale` to `spline36` (Anime4K does the upscaling; ewa on
  top drops frames) and runs 2-pass deband; `[live-action]` ships no shaders.
- Streams: `apply_anime_profile_to_streams=no` by default — the VL CNN chains
  cost 18–44 mistimed frames at 1080p/144 Hz; turn Anime4K on per-stream with
  `Ctrl+1..6` instead.
- First-frame speed: `gpu-shader-cache-dir=~~/shader_cache`.

## 7. How the installer works

### Bootstrap scripts
- `install.ps1` (Windows): clone/update `~\.mpv-config-deploy` →
  `pip install --user --quiet --editable .` → `python -m mpv_config install`.
- `install.sh` (Linux/macOS): same, but into a private venv at
  `~/.local/share/mpv-config/venv` (PEP 668-safe; falls back to uv when
  ensurepip is missing), then a `~/.local/bin/mpv-config` symlink.
- Running either from inside a checkout fast-forwards it first — it never
  reinstalls stale code.

### The pipeline (`cmd_install` in the deployer)
1. **detect** (`detector.py`) — OS/distro/display/GPU, installed binaries, mpv
   version. Floor is mpv ≥ 0.40; older distro builds get upgraded (PPA etc.).
2. **plan + confirm** (`planner.py`) — colour-coded table of every action,
   explicit Yes/No (`--dry-run` to preview).
3. **fetch** (`fetcher.py`) — all registry scripts + Anime4K into the staging
   dir. **Fail-closed**: an incomplete fetch aborts before anything is installed.
4. **install deps** (`installer.py`) — per-platform methods (winget / pacman /
   apt / dnf / brew / PPA / uv / AUR / GitHub assets) so every OS converges on
   the same toolset (mpv ≥ 0.40, yt-dlp, ffmpeg, python, uv, optional
   ffsubsync/alass). Every dep is fail-closed
   except mpv: on mpv failure it deploys a config sanitized for the existing mpv
   (unknown options commented out) instead of aborting.
5. **deploy** (`deployer.deploy()`) — assemble the complete tree offline in the
   prepared dir, then swap transactionally:
   - existing `mpv.conf`, `input.conf`, `mpv.conf.user` and every existing
     `script-opts/*.conf` are **personal and preserved** — profile flags only
     seed fresh installs;
   - repair migrations fix stale options/bindings in old deployed configs
     (`_migrate_input_conf`, `_migrate_mpv_conf`, `_migrate_uosc_conf`,
     `_migrate_smartskip_conf`);
   - uosc timeline-thumb patch applied; Start-Menu/Desktop `mpv.lnk` repointed
     (target + WorkingDirectory); yt-dlp global config + custom extractor
     plugins deployed;
   - the whole config dir is snapshotted first (`backup_existing`).
6. **verify** (`verifier.py`) — structure/binary checks plus a scripts-disabled
   mpv startup sanity check; any failure rolls the transaction back.

### Safety model
Same-filesystem transaction (`transaction.py`): operation lock, prepared-dir
swap, `mpv.backup.<ts>` snapshots, `.deploy.lock.json` manifest (versions +
sha256), `.audit-log.json` ownership log. `uninstall` removes only manifest-owned
files and only packages the audit log proves this tool installed. `rollback`
restores the latest (or a named) snapshot.

### Key deployer flags
`--anime-preset` · `--scaler-tier` · `--display-mode` · `--dither-depth` ·
`--stream-quality` (seeds fresh deploys only) · `--mpv-profile` ·
`--mpv-version` · `--dry-run` — plus `--uninstall`'s `--purge-config`,
`--remove-backups`, `--remove-deps`, `--remove-install-dir`.

## 8. Tests & CI

`python -m unittest discover -s tests` (≈420 cases, 43 skipped) and
`python tests/run_lua_tests.py`. CI: `test.yml` (3 OS × Python 3.10–3.12 + Ruff),
`youtube-gui.yml` (Lua offline regressions), `extractor-health.yml` (daily probe
of the custom yt-dlp extractors), `release.yml` (PyPI trusted publishing).

## 9. Known traps (do not regress)

- **tscale cannot affect vsync jitter** (measured, commit `a97468e`) — both
  `linear` and `oversample` measure ~5e-05 jitter; `smart_motion.lua` ships
  `oversample` at runtime because `linear` cross-fades ghost-trail 24/25/30 fps
  content. Never chase jitter by changing tscale.
- **A static `override-display-fps` caused a 282 Hz estimation bug** — the
  Wayland-only conditional `[wayland-144hz-fix]` profile is the deliberate fix.
- **Runtime VK→char queries are banned in the guard** (`MapVirtualKeyExW`/`ToUnicodeEx` measured returning scan codes, identical across layouts, under polluted key state). The twins table came from a one-shot OFFLINE probe — `ToUnicodeEx` with an explicit layout handle, a zeroed key-state array and the dead-key double-call — cross-checked against xkb `ara(basic)`; that pattern is fine, live queries are not.
- **Never bind `ل` as a single, or ASCII twins, in input.conf** — `b` emits `لا` as two key events, and mpv key sequences (`ل-ا` etc.) consume both ONLY while `ل` has no single binding of its own (a single-key binding on a sequence's first element wins). `ا` is allowed as `h`'s twin: a completed sequence swallows the second event (measured). The Arabic shift layer maps `>`/`<` to plain `.`/`,` (binding those changes US behavior; mpv cannot distinguish `Shift+.` from `.`). `layout_twins._validate` enforces all of it.
  codes, identical across layouts) — never reintroduce VK→char queries; the
  guard uses the layout HANDLE (`GetKeyboardLayout(mpv_thread)` low word ≠ `0x0409`).
- **The guard spawn line must end with `>nul 2>&1`** — without it `io.popen`
  blocks mpv's script thread on the guard's pipe.
- **`mp.get_config_dir` does not exist in this mpv build** — always
  `pcall(mp.get_property, "config-dir")`.
- Repo hygiene: `key_pkcs8.pem` and `*.pem` are git-ignored;
  `tests/test_repo_hygiene.py` enforces it. `cache/`, `downloads/`,
  `tools/marquee/` are untracked local dirs.

## 10. Agent operating rules (standing, from the user)

- ALL tests must run silent and headless (the user watches videos while the agent
  works): `--no-audio --ao=null --vo=null --no-terminal --really-quiet`, hidden
  windows, no focus stealing, no audio.
- NEVER kill processes the user started — only agent-spawned ones, matched by
  command line (`thumbfast.out`, `127.0.0.1:8731`, `mpv_probe_pipe`).
- Replies to the user go in SHORT ARABIC; work/reasoning in English.
