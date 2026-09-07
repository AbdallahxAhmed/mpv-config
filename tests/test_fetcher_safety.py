import io
import json
import os
import tempfile
import unittest
import zipfile
from unittest import mock

from deploy.fetcher import fetch_release


def _zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _latest_release_payload():
    """Unpinned entries resolve the newest release, so the API returns a list."""
    return json.dumps(
        [
            {
                "tag_name": "v1",
                "assets": [
                    {"name": "uosc.zip", "browser_download_url": "https://x/uosc.zip"}
                ],
            }
        ]
    )


def _pinned_release_payload():
    """A pinned entry hits /tags/<pin>, which returns a single release object."""
    return json.dumps(
        {
            "tag_name": "v1",
            "assets": [
                {"name": "uosc.zip", "browser_download_url": "https://x/uosc.zip"}
            ],
        }
    )


UOSC_ENTRY = {
    "name": "uosc",
    "source": {"repo": "tomasklaen/uosc", "asset_pattern": "uosc.zip"},
    "install": {"map": {"scripts/uosc/": "scripts/uosc/", "fonts/": "fonts/"}},
}


class TestFetcherSafety(unittest.TestCase):
    def test_fetch_release_rejects_path_traversal_member(self):
        release_payload = _latest_release_payload()
        zip_payload = _zip_bytes({"scripts/uosc/../../../outside.lua": "x"})
        entry = json.loads(json.dumps(UOSC_ENTRY))
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("deploy.fetcher._request", side_effect=[release_payload, zip_payload]):
                with self.assertRaises(ValueError):
                    fetch_release(entry, tmpdir)
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "outside.lua")))

    def test_fetch_release_accepts_release_root_prefix(self):
        release_payload = _latest_release_payload()
        zip_payload = _zip_bytes(
            {
                "uosc-v1/scripts/uosc/main.lua": "print('ok')",
                "uosc-v1/fonts/uosc-icons.ttf": "font",
            }
        )
        entry = json.loads(json.dumps(UOSC_ENTRY))
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("deploy.fetcher._request", side_effect=[release_payload, zip_payload]):
                meta = fetch_release(entry, tmpdir)
            self.assertGreater(meta["files_count"], 0)
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "scripts", "uosc", "main.lua")))
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "fonts", "uosc-icons.ttf")))

    def test_fetch_release_pinned_tag_reads_single_release_object(self):
        release_payload = _pinned_release_payload()
        zip_payload = _zip_bytes({"uosc-v1/scripts/uosc/main.lua": "print('ok')"})
        entry = json.loads(json.dumps(UOSC_ENTRY))
        entry["source"]["pin"] = "v1"
        entry["install"]["map"] = {"scripts/uosc/": "scripts/uosc/"}
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("deploy.fetcher._request", side_effect=[release_payload, zip_payload]):
                meta = fetch_release(entry, tmpdir)
            self.assertGreater(meta["files_count"], 0)
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "scripts", "uosc", "main.lua")))


if __name__ == "__main__":
    unittest.main()
