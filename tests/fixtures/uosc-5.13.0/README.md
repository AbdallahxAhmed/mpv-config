# uosc 5.13.0 fixture

Unmodified upstream files used by the spec 005 tests (patcher, deployer and the
uosc release check).

| File | Source | SHA-256 | Lines |
|---|---|---|---|
| `elements/Menu.lua` | `scripts/uosc/elements/Menu.lua` in `uosc.zip`, release `5.13.0` (https://github.com/tomasklaen/uosc/releases/download/5.13.0/uosc.zip) | `0cbc42afbe72f3f76f069995744de1e772d706445ed7987d1bffaafed50f2f49` | 1831 |
| `LICENSE` | `LICENSE.LGPL` at tag `5.13.0` (https://github.com/tomasklaen/uosc/blob/5.13.0/LICENSE.LGPL) | `dc626520dcd53a22f727af3ee42c770e56c97a64fe3adb063799d8ab032fe551` | 502 |
| `uosc-options.json` | Extracted facts from `scripts/uosc/main.lua` in release `5.13.0` via `python -m tools.check_uosc_release --tag 5.13.0 --write-options tests/fixtures/uosc-5.13.0/uosc-options.json` (upstream `main.lua` SHA-256: `bf97dcde4f1b8bd74a5e1c672a436a5584b5db2dc9413ab5585745afd9e1dd8d`) | — | 172 |

No copy of uosc `main.lua` is kept in the repository because upstream contains an embedded third-party API key.

uosc is licensed under the GNU LGPL 2.1 (see `LICENSE`). The files are copied as
published: LF line endings, no changes. `.gitattributes` marks this directory
`-text`, and a test fails if `elements/Menu.lua` changes.

To refresh on a pin bump (C-009), follow quickstart §5 in
`specs/005-playlist-drag-reorder/quickstart.md`.
