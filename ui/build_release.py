#!/usr/bin/env python3
"""Reproducible release builds of mpv-config-ui.

    python ui/build_release.py --write   build all targets, pin hashes in ui/release.json
    python ui/build_release.py --check   build all targets, fail unless they match the pins

Pure-Go (CGO off) builds with -trimpath, an empty build id and a fixed
toolchain are bit-for-bit reproducible, so the SHA-256 pins committed in
ui/release.json can be re-derived by anyone. The release workflow runs
--check before publishing: a binary that does not match the reviewed source
is never uploaded. The CLI downloads the .gz asset and verifies the pinned
hash of the decompressed binary before running it.
"""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent
MANIFEST = UI_DIR / "release.json"
GO_VERSION = "go1.24.7"
TARGETS = [
    ("linux", "amd64"),
    ("linux", "arm64"),
    ("windows", "amd64"),
    ("windows", "arm64"),
    ("darwin", "amd64"),
    ("darwin", "arm64"),
]


def version_from_source():
    for line in (UI_DIR / "main.go").read_text(encoding="utf-8").splitlines():
        if line.startswith("const version = "):
            return line.split('"')[1]
    raise SystemExit("const version not found in ui/main.go")


def build(goos, goarch, out_dir):
    name = f"mpv-config-ui_{goos}_{goarch}" + (".exe" if goos == "windows" else "")
    target = out_dir / name
    env = dict(
        os.environ,
        CGO_ENABLED="0",
        GOOS=goos,
        GOARCH=goarch,
        GOAMD64="v1",
        GOARM64="v8.0",
        GOTOOLCHAIN="local",
        GOFLAGS="-mod=readonly",
    )
    subprocess.run(
        [
            "go",
            "build",
            "-trimpath",
            "-buildvcs=false",
            "-ldflags=-s -w -buildid=",
            "-o",
            str(target),
            ".",
        ],
        cwd=UI_DIR,
        env=env,
        check=True,
    )
    data = target.read_bytes()
    gz = target.with_name(target.name + ".gz")
    with (
        open(gz, "wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as z,
    ):
        z.write(data)
    return (
        f"{goos}-{goarch}",
        gz.name,
        hashlib.sha256(data).hexdigest(),
        len(data),
        gz.stat().st_size,
    )


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=str(UI_DIR.parent / "dist" / "ui"))
    args = ap.parse_args()

    found = subprocess.run(
        ["go", "env", "GOVERSION"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if found != GO_VERSION:
        raise SystemExit(f"reproducible builds need {GO_VERSION}, found {found}")

    out_dir = Path(args.out)
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    version = version_from_source()
    assets = {}
    for goos, goarch in TARGETS:
        key, file, digest, size, gz_size = build(goos, goarch, out_dir)
        assets[key] = {"file": file, "sha256": digest}
        print(f"{key:15} {digest}  {size / 1e6:5.1f} MB  ({gz_size / 1e6:.1f} MB gz)")

    manifest = {"version": version, "tag": f"ui-v{version}", "go": GO_VERSION, "assets": assets}
    if args.write:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"pinned {len(assets)} builds in {MANIFEST.relative_to(UI_DIR.parent)}")
        return 0
    pinned = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if pinned != manifest:
        print("build does not match ui/release.json:", file=sys.stderr)
        print(json.dumps(pinned, indent=2), file=sys.stderr)
        print(json.dumps(manifest, indent=2), file=sys.stderr)
        return 1
    print("all builds match ui/release.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
