"""Check Git-installable assets without rebuilding or downloading Studio."""
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integrations/atomworks-studio"
AGGREGATE = ROOT / "skills/bionemo-agent-toolkit/atomworks-studio"
ASSETS = (
    "studio-upstream.html",
    "studio-upstream.provenance.json",
    "studio-upstream.NOTICES.txt",
    "STUDIO_LICENSE.md",
)


class StudioDistributionTests(unittest.TestCase):
    def test_git_plugin_contains_matching_nonempty_assets(self):
        # Explicit presence checks matter: two equally unbuilt trees must fail.
        for name in ASSETS:
            with self.subTest(asset=name):
                paths = [base / "assets" / name for base in (SOURCE, AGGREGATE)]
                for path in paths:
                    self.assertFalse(path.is_symlink(), str(path))
                    self.assertTrue(path.is_file(), f"Missing Git-distributed asset: {path}")
                    self.assertGreater(path.stat().st_size, 0, str(path))
                self.assertEqual(
                    hashlib.sha256(paths[0].read_bytes()).hexdigest(),
                    hashlib.sha256(paths[1].read_bytes()).hexdigest(),
                    f"Run plugin_sync.py after rebuilding {name}",
                )
        html = (SOURCE / "assets/studio-upstream.html").read_text()
        self.assertGreater(len(html), 1_000_000, "Expected the bundled editor, not a placeholder")
        self.assertIn("<script>", html)
        self.assertIn("BSD 3-Clause", (SOURCE / "assets/STUDIO_LICENSE.md").read_text())

    def test_provenance_matches_public_source_build_pin(self):
        provenance = json.loads((SOURCE / "assets/studio-upstream.provenance.json").read_text())
        build = (SOURCE / "build-upstream.mjs").read_text()
        pin = re.search(r'const pin = "([0-9a-f]{40})";', build)
        self.assertIsNotNone(pin)
        self.assertEqual(provenance["commit"], pin.group(1))
        self.assertEqual(provenance["repository"], "https://github.com/RosettaCommons/atomworks-studio")
        self.assertEqual(provenance["tag"], "v0.0.1")
        self.assertIs(provenance["sourceEdited"], False)


if __name__ == "__main__":
    unittest.main()
