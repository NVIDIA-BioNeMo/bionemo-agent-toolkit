"""Regression coverage for the advisory SkillSpector workflow."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scan_skills import changed_paths, scan_skills, select_skills


class SelectionTests(unittest.TestCase):
    def test_nested_eval_changes_select_only_affected_skills(self):
        msa = Path("nim-skills/meta-skills/msa-structure-prediction-pipeline")
        openfold = Path("nim-skills/openfold2-nim")
        boltz = Path("nim-skills/boltz2-nim")
        changed = [
            msa / "evals/evals.json", openfold / "SKILL.md",
            Path("skills/bionemo-agent-toolkit/skills/openfold2-nim/skill.oms.sig"),
        ]
        self.assertEqual(select_skills([boltz, openfold, msa], changed), [msa, openfold])

    def test_full_scan_and_empty_diff_are_distinct(self):
        skills = [Path("nim-skills/b"), Path("nim-skills/a")]
        self.assertEqual(select_skills(skills, None), sorted(skills))
        self.assertEqual(select_skills(skills, []), [])
        self.assertEqual(select_skills(skills, [Path("README.md")]), [])

    def test_common_path_prefix_does_not_select_another_skill(self):
        skill = Path("nim-skills/a")
        self.assertEqual(select_skills([skill], [Path("nim-skills/a-extra/SKILL.md")]), [])

    def test_git_diff_keeps_deleted_and_renamed_paths_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args):
                return subprocess.run(
                    ["git", *args], cwd=repo, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )

            git("init")
            git("config", "user.name", "Scan test")
            git("config", "user.email", "scan-test@example.invalid")
            a, b = repo / "nim-skills/a", repo / "nim-skills/b"
            a.mkdir(parents=True)
            b.mkdir(parents=True)
            (a / "SKILL.md").write_text("A")
            (b / "SKILL.md").write_text("B")
            (a / "old name.md").write_text("reference")
            (b / "removed.md").write_text("removed reference")
            git("add", ".")
            git("-c", "commit.gpgsign=false", "commit", "-m", "base")
            base = git("rev-parse", "HEAD").stdout.decode().strip()
            (a / "old name.md").rename(b / "new name.md")
            (b / "removed.md").unlink()
            git("add", "-A")
            git("-c", "commit.gpgsign=false", "commit", "-m", "move and delete")
            changed = changed_paths(repo, base)
            self.assertCountEqual(changed, [a / "old name.md", b / "new name.md", b / "removed.md"])
            self.assertEqual(select_skills([a, b], changed), [a, b])


class ScanTests(unittest.TestCase):
    def test_failures_do_not_skip_later_skills_and_baselines_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "a", root / "b"
            baseline = a / "config/skillspector-baseline.yml"
            baseline.parent.mkdir(parents=True)
            baseline.write_text("version: 1\nrules: []\n")
            b.mkdir()
            calls = []

            def scan(command, **kwargs):
                calls.append(command)
                report = Path(command[command.index("--output") + 1])
                report.write_text(json.dumps({
                    "risk_assessment": {"score": 77 if len(calls) == 1 else 10},
                    "issues": [], "suppressed_count": 0,
                    "analysis_completeness": {"status": "complete"},
                }))
                return subprocess.CompletedProcess(command, 1 if len(calls) == 1 else 0)

            with patch("scan_skills.subprocess.run", side_effect=scan), patch.dict("os.environ", {}, clear=True):
                self.assertEqual(scan_skills([a, b], root / "reports"), 1)
            self.assertEqual(len(calls), 2)
            self.assertIn("--no-llm", calls[0])
            self.assertIn("--baseline", calls[0])
            self.assertIn(str(baseline), calls[0])
            self.assertIn("--show-suppressed", calls[0])
            self.assertNotIn("--baseline", calls[1])
            self.assertIn("| b | 0 | 10 |", (root / "reports/summary.md").read_text())

    def test_missing_report_cannot_be_reported_as_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("scan_skills.subprocess.run", return_value=subprocess.CompletedProcess([], 0)), patch.dict("os.environ", {}, clear=True):
                self.assertEqual(scan_skills([root / "skill"], root / "reports"), 2)
            self.assertIn("unavailable", (root / "reports/summary.md").read_text())


if __name__ == "__main__":
    unittest.main()
