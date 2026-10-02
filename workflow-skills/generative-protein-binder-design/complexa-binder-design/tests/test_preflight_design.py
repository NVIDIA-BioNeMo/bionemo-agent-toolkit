"""Offline regression coverage for PDB/chain preflight and the UniProt path."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import biotite.structure.io.pdb as pdb
import biotite.structure.io.pdbx as pdbx
import biotite.structure as struc
import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/preflight_design.py"
SPEC = importlib.util.spec_from_file_location("preflight_design", SCRIPT)
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


def structure_text(partner=True, insertion="", extra_partner=False, partner_size=1, distal_x=30.0):
    # Residue IDs are deliberately offset and shared across chains. Only B10
    # and B20 contact the partner; B30 is distant and must not become a hotspot.
    residues = [("B", 10, "ALA", 0.0, 0.0), ("B", 20, "GLY", 4.0, 0.0),
                ("B", 30, "SER", distal_x, 0.0)]
    if partner:
        residues.append(("A", 10, "ALA", 2.0, 3.0))
        residues.extend(("A", 10 + i, "ALA", 100.0 + i, 100.0) for i in range(1, partner_size))
    if extra_partner:
        residues.append(("C", 10, "ALA", 30.0, 3.0))
    lines = []
    for serial, (chain, resid, name, x, y) in enumerate(residues, 1):
        code = insertion if serial == 1 else ""
        lines.append(
            f"ATOM  {serial:5d} {'CA':^4s} {name:>3s} {chain}{resid:4d}{code:1s}   "
            f"{x:8.3f}{y:8.3f}{0.0:8.3f}{1.0:6.2f}{20.0:6.2f}           C  "
        )
    return "\n".join([*lines, "TER", "END", ""])


class TestPreflightDesign(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "target.pdb"
        self.target.write_text(structure_text())
        self.repo = Path(self.tmp.name) / "complexa"
        self.repo.mkdir()

    def full_run(self, run_dir, **kwargs):
        with patch.object(PREFLIGHT.P, "_complexa_repo", return_value=self.repo), \
             patch.object(PREFLIGHT.P, "_run", side_effect=AssertionError("unexpected external helper")), \
             patch.object(PREFLIGHT.P, "submit_complexa", return_value=iter(())) as submit, \
             patch.object(PREFLIGHT.P, "extract_complexa_designs", return_value=iter(())):
            events = list(PREFLIGHT.P.run(mode="full", run_dir=str(run_dir), **kwargs))
        return events, submit

    def registered_target(self):
        config = self.repo / "configs/targets/targets_dict.yaml"
        entries = yaml.safe_load(config.read_text())["target_dict_cfg"]
        self.assertEqual(len(entries), 1)
        return next(iter(entries.values()))

    def assert_interface(self, report):
        self.assertEqual(report["full_length"], 3)
        self.assertEqual(report["conditioned_length"], 3)
        self.assertEqual(report["chain"], "B")
        self.assertEqual(report["source"], "pdb_interface")
        self.assertEqual(report["final_hotspots"], ["B10(ALA)", "B20(GLY)"])
        self.assertTrue(all(passed for passed, _ in report["checks"].values()))

    def test_local_pdb_keeps_author_chain_numbering_and_partner_contacts(self):
        with patch.object(PREFLIGHT.P, "_run", side_effect=AssertionError("unexpected external helper")):
            self.assert_interface(PREFLIGHT.plan(str(self.target), chain="B"))

    def test_pdb_id_uses_rcsb_without_requiring_uniprot(self):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(structure_text().encode())) as fetch:
            with patch.object(PREFLIGHT.P, "_run", side_effect=AssertionError("unexpected UniProt lookup")):
                report = PREFLIGHT.plan("1BRS", chain="B")
        self.assertEqual(report["pdb"], "1BRS")
        fetch.assert_called_once_with("https://files.rcsb.org/download/1brs.pdb", timeout=120)
        self.assert_interface(report)

    def test_local_cif_uses_author_fields(self):
        array = pdb.PDBFile.read(io.StringIO(structure_text())).get_structure(model=1)
        cif = pdbx.CIFFile()
        pdbx.set_structure(cif, array)
        path = self.target.with_suffix(".cif")
        cif.write(path)
        self.assert_interface(PREFLIGHT.plan(str(path), chain="B"))

    def test_chain_choice_is_explicit_for_multichain_inputs(self):
        for chain, message in ((None, "select a target with --chain"), ("Z", "absent")):
            with self.subTest(chain=chain), self.assertRaisesRegex(ValueError, message):
                PREFLIGHT.plan(str(self.target), chain=chain)

    def test_single_chain_has_no_invented_interface_and_nonzero_cli_status(self):
        self.target.write_text(structure_text(partner=False))
        report = PREFLIGHT.plan(str(self.target))
        self.assertEqual(report["chain"], "B")
        self.assertEqual(report["n_hotspots"], 0)
        self.assertEqual(report["source"], "none")
        self.assertFalse(report["checks"][">=1_hotspots"][0])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(PREFLIGHT.main([str(self.target)]), 1)
        self.assertIn("NEEDS ATTENTION", output.getvalue())

    def test_insertion_codes_are_not_silently_merged_into_integer_hotspots(self):
        self.target.write_text(structure_text(insertion="A"))
        with self.assertRaisesRegex(ValueError, "insertion codes"):
            PREFLIGHT.plan(str(self.target), chain="B")

    def test_uniprot_accessibility_and_hotspot_path_still_works(self):
        model = pdb.PDBFile.read(io.StringIO(structure_text(partner=False))).get_structure(model=1)
        hotspots = [{"chain": "B", "position": p, "source": "uniprot"} for p in (10, 20)]

        def run(command, **kwargs):
            if str(PREFLIGHT.P.FETCH_STRUCTURE) in command:
                cif = pdbx.CIFFile()
                pdbx.set_structure(cif, model)
                cif.write(Path(command[-1], "AF-P04626-F1-model_v4.cif"))
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.CompletedProcess(command, 0, json.dumps({"features": []}), "")

        with patch.object(PREFLIGHT.P, "_run", side_effect=run), \
             patch.object(PREFLIGHT.HS, "resolve_hotspots", return_value=(hotspots, [(10, 20)], "uniprot", [])), \
             patch.object(PREFLIGHT.HS, "accessibility", return_value={"note": "extracellular"}):
            report = PREFLIGHT.plan("P04626")
        self.assertEqual(report["uniprot"], "P04626")
        self.assertEqual(report["conditioned_length"], 2)
        self.assertEqual(report["topology"], "extracellular")
        self.assertEqual(report["final_hotspots"], ["B10(ALA)", "B20(GLY)"])

    def test_full_run_derives_the_preflight_interface_without_a_hotspots_file(self):
        output = Path(self.tmp.name) / "preflight"
        preflight = PREFLIGHT.plan(str(self.target), chain="B", out_dir=output)
        events, submit = self.full_run(Path(self.tmp.name) / "run", target_file=str(self.target), chain="B")
        self.assertFalse([e.message for e in events if e.status == "error"])
        submit.assert_called_once()
        entry = self.registered_target()
        self.assertEqual(entry["hotspot_residues"], ["B10", "B20"])
        self.assertEqual(entry["target_input"], "B10-10, B20-20, B30-30")
        self.assertEqual(Path(entry["target_path"]).read_bytes(), Path(preflight["prepared_target"]).read_bytes())
        saved = json.loads((output / "hotspots.json").read_text())
        self.assertEqual(saved["hotspot_residues"], preflight["hotspot_residues"])
        self.assertEqual(saved["partner_chain"], "A")

    def test_multiple_partners_require_one_explicit_interface_before_compaction(self):
        self.target.write_text(structure_text(extra_partner=True))
        with self.assertRaisesRegex(ValueError, "--partner-chain"):
            PREFLIGHT.plan(str(self.target), chain="B")
        for partner, expected in (("A", ["B10(ALA)", "B20(GLY)"]), ("C", ["B30(SER)"])):
            with self.subTest(partner=partner):
                report = PREFLIGHT.plan(str(self.target), chain="B", partner_chain=partner)
                self.assertEqual(report["final_hotspots"], expected)
                self.assertEqual(report["partner_chain"], partner)
        events, submit = self.full_run(Path(self.tmp.name) / "ambiguous", target_file=str(self.target), chain="B")
        self.assertTrue(any("--partner-chain" in e.message for e in events if e.status == "error"))
        submit.assert_not_called()
        events, submit = self.full_run(Path(self.tmp.name) / "chosen", target_file=str(self.target),
                                       chain="B", partner_chain="C")
        self.assertFalse([e.message for e in events if e.status == "error"])
        self.assertEqual(self.registered_target()["hotspot_residues"], ["B30"])

    def test_partner_geometry_never_changes_the_registered_target_or_crop(self):
        for size in (1, 400):
            with self.subTest(partner_residues=size):
                self.target.write_text(structure_text(partner_size=size))
                output = Path(self.tmp.name) / f"preflight-{size}"
                report = PREFLIGHT.plan(str(self.target), chain="B", out_dir=output)
                events, submit = self.full_run(Path(self.tmp.name) / f"run-{size}",
                                               target_file=str(self.target), chain="B")
                self.assertFalse([e.message for e in events if e.status == "error"])
                entry = self.registered_target()
                actual = PREFLIGHT.P._read_first_model(Path(entry["target_path"]))
                self.assertEqual(set(actual.chain_id), {"B"})
                self.assertEqual(struc.get_residue_count(actual), report["conditioned_length"])
                self.assertEqual(report["conditioned_length"], 3)
                self.assertEqual(Path(entry["target_path"]).read_bytes(), Path(report["prepared_target"]).read_bytes())

    def test_saved_preflight_files_can_be_handed_to_generation(self):
        output = Path(self.tmp.name) / "prepared"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(PREFLIGHT.main([str(self.target), "--chain", "B", "--out", str(output)]), 0)
        report = json.loads((output / "preflight.json").read_text())
        events, submit = self.full_run(Path(self.tmp.name) / "handoff", target_file=report["prepared_target"],
                                       hotspots=report["hotspots_path"])
        self.assertFalse([e.message for e in events if e.status == "error"])
        self.assertEqual(self.registered_target()["hotspot_residues"], ["B10", "B20"])
        self.assertEqual(Path(self.registered_target()["target_path"]).read_bytes(), Path(report["prepared_target"]).read_bytes())

    def test_full_run_stops_before_gpu_without_a_valid_epitope(self):
        self.target.write_text(structure_text(partner=False))
        events, submit = self.full_run(Path(self.tmp.name) / "empty", target_file=str(self.target))
        self.assertTrue(any("preflight failed" in e.message for e in events if e.status == "error"))
        submit.assert_not_called()

    def test_crop_respects_even_residue_budget_and_preserves_hotspots(self):
        lines = [f"ATOM  {i:5d}  CA  ALA B{i:4d}    {float(i):8.3f}{0.0:8.3f}{0.0:8.3f}  1.00 20.00           C  "
                 for i in range(1, 501)]
        self.target.write_text("\n".join([*lines, "TER", "END", ""]))
        hs = Path(self.tmp.name) / "explicit.json"
        hs.write_text(json.dumps([{"chain": "B", "position": p} for p in (200, 201)]))
        report = PREFLIGHT.plan(str(self.target), binder_max=154, hotspots=hs,
                                out_dir=Path(self.tmp.name) / "cropped")
        actual = PREFLIGHT.P._read_first_model(Path(report["prepared_target"]))
        self.assertEqual(struc.get_residue_count(actual), 346)
        self.assertEqual(report["conditioned_length"], 346)
        self.assertTrue(all(ok for ok, _ in report["checks"].values()))
        self.assertEqual(report["final_hotspots"], ["B200(ALA)", "B201(ALA)"])
        # The default budget used by generation must produce the same actual
        # crop and hotspots, not merely a matching estimated residue count.
        default = PREFLIGHT.plan(str(self.target), hotspots=hs,
                                 out_dir=Path(self.tmp.name) / "default-crop")
        events, submit = self.full_run(Path(self.tmp.name) / "cropped-run", target_file=str(self.target),
                                       hotspots=str(hs))
        self.assertFalse([e.message for e in events if e.status == "error"])
        self.assertEqual(Path(self.registered_target()["target_path"]).read_bytes(),
                         Path(default["prepared_target"]).read_bytes())

    def test_preflight_and_full_run_use_the_same_pairwise_compaction(self):
        self.target.write_text(structure_text(partner=False, distal_x=40.0))
        hs = Path(self.tmp.name) / "wide.json"
        hs.write_text(json.dumps([{"chain": "B", "position": p} for p in (10, 20, 30)]))
        plan = PREFLIGHT.plan(str(self.target), hotspots=hs)
        self.assertEqual(plan["diameter_A_raw"], 40.0)
        self.assertEqual(plan["final_hotspots"], ["B10(ALA)", "B20(GLY)"])
        events, submit = self.full_run(Path(self.tmp.name) / "compact", target_file=str(self.target),
                                       hotspots=str(hs))
        self.assertFalse([e.message for e in events if e.status == "error"])
        self.assertEqual(self.registered_target()["hotspot_residues"], ["B10", "B20"])

    def test_msa_and_validation_handoff_use_the_prepared_target_and_chain(self):
        run_dir = Path(self.tmp.name) / "handoff"

        def extract(rd, *args, **kwargs):
            seqs = rd / "sequences"
            seqs.mkdir(parents=True)
            (seqs / "binders_complexa_native.fasta").write_text(">synthetic\nAGST\n")
            return iter(())

        with patch.object(PREFLIGHT.P, "_complexa_repo", return_value=self.repo), \
             patch.object(PREFLIGHT.P, "submit_complexa", return_value=iter(())), \
             patch.object(PREFLIGHT.P, "extract_complexa_designs", side_effect=extract), \
             patch.object(PREFLIGHT.P, "_run", return_value=subprocess.CompletedProcess([], 0, "", "")) as msa:
            events = list(PREFLIGHT.P.run(mode="full", run_dir=str(run_dir),
                                         target_file=str(self.target), chain="B"))
        self.assertFalse([e.message for e in events if e.status == "error"])
        msa.assert_called_once()
        command = msa.call_args.args[0]
        self.assertEqual(command[command.index("--seq-from-pdb") + 1], run_dir / "target_prepared.pdb")
        self.assertEqual(command[command.index("--chain") + 1], "B")
        handoff = next(e.message for e in events if e.stage == "stage3" and "binders:" in e.message)
        self.assertIn(f"{run_dir / 'target_prepared.pdb'} (chain B)", handoff)

    def test_changing_partner_cannot_reuse_binders_for_the_old_epitope(self):
        self.target.write_text(structure_text(extra_partner=True))
        run_dir = Path(self.tmp.name) / "resumed"
        events, _ = self.full_run(run_dir, target_file=str(self.target), chain="B", partner_chain="A")
        self.assertFalse([e.message for e in events if e.status == "error"])
        (run_dir / "sequences").mkdir()
        (run_dir / "sequences/binders_complexa_native.fasta").write_text(">old\nAGST\n")
        events, submit = self.full_run(run_dir, target_file=str(self.target), chain="B", partner_chain="C")
        self.assertTrue(any("different or unverified" in e.message for e in events if e.status == "error"))
        submit.assert_not_called()

    def test_old_target_registration_cannot_bypass_prepared_geometry(self):
        config = self.repo / "configs/targets/targets_dict.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(yaml.safe_dump({"target_dict_cfg": {"stale": {
            "target_path": str(self.target), "target_input": "A10-10, B10-30",
            "hotspot_residues": [], "binder_length": [64, 155]}}}))
        events, submit = self.full_run(Path(self.tmp.name) / "stale", target_file=str(self.target),
                                       chain="B", target_key="stale")
        self.assertTrue(any("differs from the prepared" in e.message for e in events if e.status == "error"))
        submit.assert_not_called()

    def test_pipeline_cli_reports_invalid_preflight_as_failure(self):
        self.target.write_text(structure_text(partner=False))
        with contextlib.redirect_stdout(io.StringIO()):
            status = PREFLIGHT.P.main(["--mode", "full", "--target-file", str(self.target),
                                       "--run-dir", str(Path(self.tmp.name) / "cli")])
        self.assertEqual(status, 1)

    def test_cli_help_does_not_attempt_target_resolution(self):
        with patch.object(PREFLIGHT.P, "resolve_target_spec", side_effect=AssertionError("network")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as stopped:
                PREFLIGHT.main(["--help"])
        self.assertEqual(stopped.exception.code, 0)
        self.assertIn("--chain", output.getvalue())


if __name__ == "__main__":
    unittest.main()
