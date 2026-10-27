"""README Table of Contents integrity: every TOC link must resolve as it would on GitHub."""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

HTML_ANCHOR_RE = re.compile(r'<a\s+(?:id|name)=["\']([^"\']+)["\']')
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


def github_heading_slug(title: str) -> str:
    """Approximate GitHub's heading anchor (github-slugger) for this repo's headings.

    Lowercase, strip backticks/emoji/punctuation, and map each space to one
    hyphen. Hyphen runs are preserved (GitHub never collapses them) and nothing
    is trimmed: an emoji heading such as "📊 Project status" slugs to
    "-project-status", not "project-status" — so emoji headings need explicit
    <a id="..."> anchors for TOC links to resolve.
    """
    title = title.replace("`", "")
    slug = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    return slug.lower().replace(" ", "-")


class ReadmeTocTests(unittest.TestCase):
    def _extract_toc_and_targets(self, file_path: Path):
        text = file_path.read_text(encoding="utf-8")

        # Find the Table of Contents block
        toc_match = re.search(r"## 📑 [^\n]+\n\n(.*?)\n---", text, re.DOTALL)
        self.assertIsNotNone(toc_match, f"Table of Contents not found in {file_path.name}")
        toc_text = toc_match.group(1)

        # Extract all markdown anchor links [text](#anchor) from the TOC
        toc_links = re.findall(r"\[([^\]]+)\]\(#([^\)]+)\)", toc_text)
        self.assertGreater(len(toc_links), 0, f"No TOC links found in {file_path.name}")

        # Extract HTML anchors (<a id="..."> or <a name="...">)
        html_anchors = set(HTML_ANCHOR_RE.findall(text))

        # GitHub also generates an anchor per heading; mirror its algorithm so
        # headings without an explicit HTML anchor are validated the same way
        # GitHub resolves them.
        heading_slugs = set()
        for line in text.splitlines():
            m = HEADING_RE.match(line)
            if m:
                heading_slugs.add(github_heading_slug(m.group(2)))

        all_targets = html_anchors | heading_slugs
        return toc_links, all_targets

    def test_readme_en_toc_links_resolve(self):
        readme = REPO_ROOT / "README.md"
        toc_links, all_targets = self._extract_toc_and_targets(readme)

        # Ensure we have all 36 major sections indexed
        self.assertEqual(len(toc_links), 36)

        missing = []
        for text, anchor in toc_links:
            if anchor not in all_targets:
                missing.append(f"[{text}](#{anchor})")

        self.assertEqual(missing, [], f"Broken TOC anchors in README.md: {missing}")

    def test_readme_ar_toc_links_resolve(self):
        readme_ar = REPO_ROOT / "README.ar.md"
        toc_links, all_targets = self._extract_toc_and_targets(readme_ar)

        # Ensure we have all 36 major sections indexed
        self.assertEqual(len(toc_links), 36)

        missing = []
        for text, anchor in toc_links:
            if anchor not in all_targets:
                missing.append(f"[{text}](#{anchor})")

        self.assertEqual(missing, [], f"Broken TOC anchors in README.ar.md: {missing}")

    def test_toc_count_parity(self):
        readme_en = REPO_ROOT / "README.md"
        readme_ar = REPO_ROOT / "README.ar.md"

        en_links, _ = self._extract_toc_and_targets(readme_en)
        ar_links, _ = self._extract_toc_and_targets(readme_ar)

        self.assertEqual(
            len(en_links),
            len(ar_links),
            f"TOC link count mismatch: EN has {len(en_links)}, AR has {len(ar_links)}",
        )

    def test_no_duplicate_anchor_ids(self):
        for name in ("README.md", "README.ar.md"):
            with self.subTest(file=name):
                text = (REPO_ROOT / name).read_text(encoding="utf-8")
                ids = HTML_ANCHOR_RE.findall(text)
                duplicates = sorted({anchor_id for anchor_id in ids if ids.count(anchor_id) > 1})
                self.assertEqual(duplicates, [], f"Duplicate anchor ids in {name}: {duplicates}")


if __name__ == "__main__":
    unittest.main()
