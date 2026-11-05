"""Regression coverage for validation artifacts during source imports."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import plugin_sync


class ArtifactOwnershipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.source = self.repo / "library-skills/demo"
        self.payload = self.repo / "skills/bionemo-agent-toolkit/skills/demo"
        self.source.mkdir(parents=True)
        self.payload.mkdir(parents=True)
        self.manifest = self.repo / "components.d/demo.yml"
        self.manifest.parent.mkdir()
        self.register(self.source)
        (self.repo / "plugins").symlink_to("skills", target_is_directory=True)
        (self.repo / "skills.sh.json").write_text(json.dumps({
            "groupings": [{"skills": ["demo"]}],
        }))
        for directory in (self.source, self.payload):
            (directory / "SKILL.md").write_text("Demo skill\n")
        self.artifacts = ("BENCHMARK.md", "skill-card.md", "skill.oms.sig")
        for artifact in self.artifacts:
            (self.source / artifact).write_text(f"Upstream {artifact}\n")
            (self.payload / artifact).write_text(f"Aggregate {artifact}\n")
        patched = patch.multiple(
            plugin_sync,
            REPO=self.repo,
            SKILLS_ROOT=self.repo / "skills",
            AGGREGATE_ROOT=self.payload.parent.parent,
            AGGREGATE_SKILLS=self.payload.parent,
            LEGACY_PLUGINS=self.repo / "plugins",
            CONFIG=self.repo / "skills.sh.json",
        )
        patched.start()
        self.addCleanup(patched.stop)

    def register(self, catalog_dir):
        self.manifest.write_text(
            "name: Demo\nrepo: example/demo\nref: main\nskills:\n"
            "  - path: skills\n"
            f'    catalog_dir: "{catalog_dir.relative_to(self.repo)}"\n'
        )

    def test_import_replaces_old_aggregate_artifacts_with_source_versions(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(plugin_sync.write(), 0)
            self.assertEqual(plugin_sync.check(), 0)
        for artifact in self.artifacts:
            self.assertEqual((self.payload / artifact).read_bytes(),
                             (self.source / artifact).read_bytes())

    def test_import_check_detects_missing_or_changed_source_artifacts(self):
        with redirect_stdout(io.StringIO()):
            plugin_sync.write()
        for artifact in self.artifacts:
            for missing in (False, True):
                with self.subTest(artifact=artifact, missing=missing):
                    target = self.payload / artifact
                    if missing:
                        target.unlink()
                    else:
                        target.write_text("stale aggregate version")
                    output = io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(plugin_sync.check(), 1)
                    self.assertIn(artifact, output.getvalue())
                    target.write_bytes((self.source / artifact).read_bytes())

    def assert_native_artifacts_preserved(self):
        before = {name: (self.payload / name).read_bytes() for name in self.artifacts}
        with redirect_stdout(io.StringIO()):
            self.assertEqual(plugin_sync.write(), 0)
            self.assertEqual(plugin_sync.check(), 0)
        for artifact, content in before.items():
            self.assertEqual((self.payload / artifact).read_bytes(), content)

    def test_native_skills_keep_aggregate_generated_artifacts(self):
        self.manifest.unlink()
        self.assert_native_artifacts_preserved()

    def test_registration_does_not_cover_a_similarly_named_native_skill(self):
        self.register(self.source.with_name("demo-other"))
        self.assert_native_artifacts_preserved()

    def test_native_artifacts_are_preserved_without_matching_registration(self):
        self.register(self.repo / "open-models-skills/demo")
        self.assert_native_artifacts_preserved()

    def test_container_registration_covers_nested_skills(self):
        container = self.source.parent / "product"
        container.mkdir()
        self.source = self.source.rename(container / "demo")
        self.register(container)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(plugin_sync.write(), 0)
            self.assertEqual(plugin_sync.check(), 0)
        for artifact in self.artifacts:
            self.assertEqual((self.payload / artifact).read_bytes(),
                             (self.source / artifact).read_bytes())

    def test_import_does_not_keep_artifacts_removed_upstream(self):
        for artifact in self.artifacts:
            (self.source / artifact).unlink()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(plugin_sync.check(), 1)
            self.assertEqual(plugin_sync.write(), 0)
            self.assertEqual(plugin_sync.check(), 0)
        for artifact in self.artifacts:
            self.assertFalse((self.payload / artifact).exists())


if __name__ == "__main__":
    unittest.main()
