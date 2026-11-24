# Contract: scheduled uosc release check (C-008, SC-009, FR-016)

**Script**: `tools/check_uosc_release.py` (stdlib, `pathlib`, `http.client`, no `subprocess`)
**Workflow**: `.github/workflows/uosc-release-check.yml`

## Interfaces

```python
API_URL = "https://api.github.com/repos/tomasklaen/uosc/releases/latest"   # test seam
API_TAG_URL = "https://api.github.com/repos/tomasklaen/uosc/releases/tags/{tag}"
DEFAULT_DOWNLOAD_TIMEOUT_S = 120.0
MEMBER = "scripts/uosc/elements/Menu.lua"
MEMBER_MAIN = "scripts/uosc/main.lua"

def run(api_url: str | None = None, download_timeout: float = DEFAULT_DOWNLOAD_TIMEOUT_S, tag: str | None = None, write_options: Path | None = None, compare_options: Path | None = None, looks_path: Path = LOOKS_LUA) -> int
def check_dir(uosc_dir: Path, version: str, write_options: Path | None = None, compare_options: Path | None = None, looks_path: Path = LOOKS_LUA) -> int
def check_menu_constants(menu_lua: bytes, version: str = "5.13.0") -> list[str]
def extract_uosc_facts(main_lua: bytes, version: str) -> dict
def read_looks_keys(looks_lua: Path = LOOKS_LUA) -> tuple[list[str], list[str], list[str], list[str]]
def check_options(facts: dict, owned: list[str], color_keys: list[str], opacity_keys: list[str], bindings: list[str]) -> list[str]
def main(argv: list[str] | None = None) -> int
```

```text
python -m tools.check_uosc_release --latest [--download-timeout SECONDS] [--write-options PATH] [--compare-options PATH]
python -m tools.check_uosc_release --tag TAG [--download-timeout SECONDS] [--write-options PATH] [--compare-options PATH]
python -m tools.check_uosc_release --uosc-dir DIR --version TAG [--write-options PATH] [--compare-options PATH]
```

| Mode | Files from | Network |
|---|---|---|
| `--latest` → `run()` | `GET api_url` (JSON) → the `browser_download_url` of the asset named `uosc.zip` → in-memory zip → `MEMBER`, `MEMBER_MAIN` | yes |
| `--tag TAG` → `run(tag=TAG)` | `GET api_tag_url` (JSON) → the `browser_download_url` of the asset named `uosc.zip` → in-memory zip → `MEMBER`, `MEMBER_MAIN` | yes |
| `--uosc-dir DIR --version TAG` → `check_dir()` | `DIR/elements/Menu.lua`, `DIR/main.lua` (if present) | none |

Both modes call `patch_uosc_playlist_reorder.check_anchors()`. That function never
checks hashes, because a new release's hash is unknown (research R12). Nothing is
patched, written, imported or executed. When `main.lua` is available, option facts
are extracted and checked against `scripts/modules/looks.lua`.

## Exit codes and messages

| Exit | When | Output (GitHub annotation) |
|---|---|---|
| 0 | every anchor matches and options present | `uosc <tag>: all 8 anchors of uosc-playlist-reorder match` followed by `uosc <tag>: <n> owned options, runtime handler and <m> bindings present` (if main.lua present) |
| 1 | one or more anchors fail, menu constants fail, or options/bindings fail | anchor failures, menu constant failure (`uosc <tag>: menu constant "<text>" missing`), option problem lines (`option <key> missing`, `color <key> missing`, `opacity <key> missing`, `runtime option handler missing`, `binding <name> missing`), or options difference (`uosc <tag>: options differ from <path> at <key>`) |
| 2 | could not run | `::error title=uosc release check::uosc <tag or latest>: <reason>` |

Reasons for exit 2:

- `download did not finish within <N> s (<url>); the release check could not run`
- `HTTP <code> from <url>`
- `release has no uosc.zip asset`
- `uosc.zip has no member scripts/uosc/elements/Menu.lua`
- `release zip has no scripts/uosc/main.lua`
- `uosc.zip is not a valid zip`
- `main.lua: <block> not found`
- `cannot read <compare_options>: <reason>`
- `cannot write <write_options>: <reason>`

## Deadline (research R8)

- A single `deadline = time.monotonic() + download_timeout` covers the API request,
  up to 5 redirects and the zip body.
- Connections use `http.client.HTTPSConnection`. `HTTPConnection` is allowed only
  when the host is `127.0.0.1` or `localhost`.
- The socket timeout is set to `max(0.01, deadline - time.monotonic())` at connect
  and before **every** read. Reads use `resp.read1(65536)`. The deadline is checked
  after each read.
- A watchdog `threading.Timer(remaining, shutdown)` starts just before each
  `getresponse()` and is cancelled in `finally`. `shutdown` calls
  `conn.sock.shutdown(socket.SHUT_RDWR)`. This bounds the status-line and header
  reads, which `getresponse()` performs internally, as well as the body.
- A hang or a trickle, in the headers or the body, ends at the deadline with the
  "did not finish within" reason and exit 2.
- Size limits are reused from `deploy.fetcher`: `MAX_DOWNLOAD_BYTES`,
  `MAX_ARCHIVE_MEMBERS`, `MAX_EXPANDED_BYTES`, `_safe_zip_name`. `from deploy import
  fetcher` imports without `rich` (checked 2026-11-20).
- The token is `GITHUB_TOKEN`, or else `GH_TOKEN`. It is sent only when the request
  host is exactly `api.github.com`: never to a redirect target and never to a test
  server.

## Workflow

```yaml
name: uosc release check
on:
  schedule: [{cron: '41 5 * * 1'}]   # weekly, Monday 05:41 UTC
  workflow_dispatch:
permissions: {contents: read}
jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - name: Check latest uosc release (reorder anchors, theme options)
        timeout-minutes: 5
        env: {GITHUB_TOKEN: '${{ secrets.GITHUB_TOKEN }}'}
        run: python -m tools.check_uosc_release --latest --download-timeout 120
      - name: Compare pinned uosc 5.13.0 options
        timeout-minutes: 5
        env: {GITHUB_TOKEN: '${{ secrets.GITHUB_TOKEN }}'}
        run: python -m tools.check_uosc_release --tag 5.13.0 --compare-options tests/fixtures/uosc-5.13.0/uosc-options.json --download-timeout 120
```

## Tests (offline, in-process `run()` / `check_dir()`)

| Test | Setup | Expect |
|---|---|---|
| pass on 5.13.0 | `check_dir(tests/fixtures/uosc-5.13.0, "5.13.0")` | 0 |
| broken anchor (SC-009) | copy the fixture to a temp dir, change one byte inside the `menu-key` anchor | 1; output contains `5.13.0`, `menu-key` and `elements/Menu.lua` |
| missing owned key | zip whose `main.lua` lacks an owned key | 1; output names the key |
| missing handler | zip whose `main.lua` lacks the handler line | 1; output contains `runtime option handler missing` |
| missing main.lua | zip without `scripts/uosc/main.lua` | 2; `release zip has no scripts/uosc/main.lua` |
| write options | `--write-options` on a release zip | 0; writes sorted JSON |
| compare options | `--compare-options` against altered options | 1; output names the differing key |
| hung server | local `http.server` on 127.0.0.1: sends headers with `Content-Length: 1048576`, then sleeps 30 s; `run(api_url=…, download_timeout=1)` | 2 within 5 s; output contains `did not finish within 1 s` |
| trickling body | same, but sends 1 body byte every 0.2 s | 2 within 5 s; same text |
| trickled headers | sends the status line and headers 1 byte every 0.2 s | 2 within 5 s; same text |
| HTTP error | API answers 500 | 2, `HTTP 500 from <url>` |
| invalid zip | asset body is not a zip | 2, `uosc.zip is not a valid zip` |
| missing asset | API JSON without `uosc.zip` | 2, `release has no uosc.zip asset` |
| missing member | zip without `MEMBER` | 2, `has no member` |
| token scope | API and asset on 127.0.0.1, `GITHUB_TOKEN` set | the server sees no `Authorization` header |
| CLI smoke | `subprocess.run([sys.executable, "-m", "tools.check_uosc_release", "--uosc-dir", …, "--version", "5.13.0"])` with a list, not `shell=True` | exit 0 |
