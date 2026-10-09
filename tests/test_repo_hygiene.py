"""Repository hygiene guards.

The project once committed private keys. These tests encode the rules that stop a
repeat so they run in CI on every push: no key material is tracked, ``.gitignore``
blocks it, and no tracked file carries a hard-coded personal path.
"""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Third-party material that is vendored rather than authored here. It is still
# scanned for key material, but not for example paths written by other people.
VENDORED_PREFIXES = (".agent/", ".agents/", ".specify/")

KEY_SUFFIXES = (".pem", ".key", ".crt", ".p12", ".pfx")
REQUIRED_GITIGNORE_ENTRIES = ("*.pem", "*.key", "*.crt", "*.p12", "*.pfx", ".env")

# Assembled in pieces so that this file does not match its own pattern.
PRIVATE_KEY_BLOCK = re.compile("-----BEGIN [A-Z ]*" + "PRIVATE KEY" + "-----")

# A drive-letter user-profile path (any slash style, also inside file:// URLs and
# JSON-escaped strings) and a Unix-style home directory path. Group 1 is the account.
WINDOWS_PROFILE_PATH = re.compile(
    r"(?i)(?<![a-z0-9])[a-z]:[\\/]+users[\\/]+([^\\/\s\"'`<>|*?:\[\]]+)"
)
UNIX_HOME_PATH = re.compile(r"(?<![A-Za-z0-9_])/(?:home|Users)/([A-Za-z0-9_.-]+)/")

# Placeholders and OS-provided directories: not a person's account.
GENERIC_ACCOUNTS = {"user", "username", "you", "yourname", "name", "me", "example", "runner"}
GENERIC_ACCOUNTS |= {"public", "default", "all users"}
PLACEHOLDER_PREFIXES = ("%", "$", "{", "~")

# (file, account) pairs that are third-party examples inside vendored configuration.
KNOWN_THIRD_PARTY_PATHS = {("config/script-opts/SmartSkip.conf", "eisa01")}

MAX_SCANNED_BYTES = 5_000_000


def _is_placeholder(account):
    lowered = account.lower()
    return lowered in GENERIC_ACCOUNTS or lowered.startswith(PLACEHOLDER_PREFIXES)


class RepositoryHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        git = shutil.which("git")
        if git is None or not (REPO_ROOT / ".git").exists():
            raise unittest.SkipTest("not a git checkout")
        listing = subprocess.run(
            [git, "ls-files", "-z"], cwd=str(REPO_ROOT), capture_output=True, check=False
        )
        if listing.returncode != 0:
            raise unittest.SkipTest("git ls-files is unavailable")
        names = listing.stdout.decode("utf-8", errors="replace").split("\0")
        cls.tracked = [name for name in names if name and (REPO_ROOT / name).is_file()]

    def tracked_texts(self, skip_vendored=False):
        for name in self.tracked:
            if skip_vendored and name.startswith(VENDORED_PREFIXES):
                continue
            data = (REPO_ROOT / name).read_bytes()
            if len(data) > MAX_SCANNED_BYTES or b"\0" in data[:8192]:
                continue  # binary or oversized: not scanned as text
            yield name, data.decode("utf-8", errors="replace")

    def test_no_key_or_certificate_files_are_tracked(self):
        offenders = [name for name in self.tracked if name.lower().endswith(KEY_SUFFIXES)]
        self.assertEqual(offenders, [])

    def test_gitignore_blocks_secret_material(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        entries = {line.strip() for line in text.splitlines()}
        missing = [entry for entry in REQUIRED_GITIGNORE_ENTRIES if entry not in entries]
        self.assertEqual(missing, [], f".gitignore is missing: {missing}")

    def test_no_private_key_blocks_are_tracked(self):
        offenders = [name for name, text in self.tracked_texts() if PRIVATE_KEY_BLOCK.search(text)]
        self.assertEqual(offenders, [])

    def test_no_personal_paths_are_tracked(self):
        offenders = []
        for name, text in self.tracked_texts(skip_vendored=True):
            for pattern in (WINDOWS_PROFILE_PATH, UNIX_HOME_PATH):
                for match in pattern.finditer(text):
                    account = match.group(1)
                    if _is_placeholder(account):
                        continue
                    if (name, account.lower()) in KNOWN_THIRD_PARTY_PATHS:
                        continue
                    offenders.append(f"{name}: {match.group(0)}")
        self.assertEqual(
            offenders,
            [],
            "Hard-coded personal paths found; use Path.home(), os.environ or relative links",
        )


if __name__ == "__main__":
    unittest.main()
