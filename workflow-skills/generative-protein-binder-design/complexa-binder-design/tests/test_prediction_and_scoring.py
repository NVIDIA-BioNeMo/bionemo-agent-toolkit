"""Exercise prediction failures and real geometry calculations without inference."""
import argparse
import contextlib
import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import boltz2_endpoint as endpoint
import boltz2_refold as refold
import complexa_design as design
import execution
import validate_binders as validator


@pytest.mark.parametrize("kind", ["holo", "apo"])
@pytest.mark.parametrize("failure", [429, 503, "connection"])
def test_transient_failure_retries_with_bounded_delay_and_preserves_payload(kind, failure):
    error = (urllib.error.URLError("synthetic outage") if failure == "connection" else
             urllib.error.HTTPError(endpoint.HOSTED_URL, failure, "try later", {"Retry-After": "500"}, None))
    module = refold if kind == "holo" else validator
    with mock.patch.object(module, "open_prediction", side_effect=[error, io.BytesIO(b'{"structures":[]}')]) as post, \
         mock.patch.object(module.time, "sleep") as sleep:
        if kind == "holo":
            response = refold.boltz2_holo("AG", "ST", endpoint.HOSTED_URL, "synthetic-key", 1,
                                          target_chain="X", binder_chain="Y")
        else:
            response = validator.boltz2_predict_apo("ST", endpoint.HOSTED_URL, "synthetic-key", max_retries=1)
    assert response == {"structures": []}
    assert post.call_count == 2
    assert 0 < sleep.call_args.args[0] <= 120
    request = post.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer synthetic-key"
    body = json.loads(request.data)
    assert [p["sequence"] for p in body["polymers"]] == (["AG", "ST"] if kind == "holo" else ["ST"])


@pytest.mark.parametrize("kind", ["holo", "apo"])
@pytest.mark.parametrize("code,attempts", [(401, 1), (429, 3), (None, 3)])
def test_permanent_errors_and_retry_exhaustion_stop(kind, code, attempts):
    error = (TimeoutError("synthetic timeout") if code is None else
             urllib.error.HTTPError(endpoint.LOCAL_URL, code, "failed", {}, None))
    module = refold if kind == "holo" else validator
    with mock.patch.object(module, "open_prediction", side_effect=error) as post, \
         mock.patch.object(module.time, "sleep"):
        with pytest.raises(type(error)):
            if kind == "holo":
                refold.post_with_retry(endpoint.LOCAL_URL, {}, {}, max_retries=2)
            else:
                validator.boltz2_predict_apo("ST", endpoint.LOCAL_URL, None, max_retries=2)
    assert post.call_count == attempts


def test_opener_sends_only_validated_requests_and_installs_redirect_block():
    request = urllib.request.Request(endpoint.HOSTED_URL, data=b"{}", headers={"Authorization": "Bearer synthetic"})
    with mock.patch.object(endpoint.urllib.request, "build_opener") as builder:
        endpoint.open_prediction(request, timeout=5)
    assert isinstance(builder.call_args.args[0], endpoint._NoRedirect)
    builder.return_value.open.assert_called_once_with(request, timeout=5)
    with mock.patch.object(endpoint.urllib.request, "build_opener") as builder:
        with pytest.raises(ValueError):
            endpoint.open_prediction(urllib.request.Request("http://other.invalid", headers={"Authorization": "Bearer synthetic"}), timeout=5)
    builder.assert_not_called()


def cif_text():
    columns = "group_PDB label_asym_id label_seq_id label_comp_id label_atom_id Cartn_x Cartn_y Cartn_z B_iso_or_equiv".split()
    return "data_example\nloop_\n" + "\n".join("_atom_site." + c for c in columns) + "\n" + "\n".join([
        "ATOM X 2 GLY CA 20 0 0 70", "ATOM X 1 ALA CA 0 0 0 90",
        "ATOM X 1 ALA CB 0 1 0 90", "ATOM Y 1 SER CA 0 5 0 80",
        "ATOM Y 1 SER CB 0 4 0 80", "HETATM X . LIG C 0 0 0 0",
        "ATOM incomplete", "loop_", "_other.value 1",
    ])


def test_cif_chains_plddt_and_hotspot_distances_keep_residue_identity():
    atoms = validator.parse_cif_atoms(cif_text())
    assert len(atoms) == 5
    assert validator.chain_sequence(atoms, "X") == "AG"
    assert validator.chain_mean_ca_plddt(atoms, "X") == pytest.approx(0.8)
    assert np.isnan(validator.chain_mean_ca_plddt(atoms, "absent"))
    contacts = validator.hotspot_contacts(atoms, "X", "Y", [{"position": 1}, {"position": 2}, {"position": 999}], cutoff=13)
    assert contacts["n_contacted"] == 1
    assert contacts["contact_frac"] == pytest.approx(1 / 3)
    assert contacts["per_hotspot"][0]["min_cb_dist"] == pytest.approx(3)
    assert contacts["per_hotspot"][2]["min_cb_dist"] is None
    assert validator.hotspot_contacts(atoms, "X", "Y", [])["contact_frac"] is None


def test_kabsch_removes_rotation_translation_but_not_structural_change():
    coordinates = np.array([[0., 0., 0.], [1., 0., 0.], [0., 2., 0.], [0., 0., 3.]])
    rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
    transformed = coordinates @ rotation + [10., 20., 30.]
    assert validator.kabsch_rmsd(coordinates, transformed) == pytest.approx(0., abs=1e-12)
    transformed[-1] += [2., 3., 4.]
    assert validator.kabsch_rmsd(coordinates, transformed) > 0.5
    assert np.isnan(validator.kabsch_rmsd(coordinates, transformed[:2]))


def test_credential_lookup_uses_only_documented_keys_and_environment_precedence(tmp_path):
    config = tmp_path / "prediction-config"
    config.write_text('# test\nUNRELATED_TOKEN=ignore\ninvalid line\nNVIDIA_API_KEY="file-key"\n')
    with mock.patch.dict("os.environ", {}, clear=True):
        assert validator.load_api_key([tmp_path / "absent", config]) == "file-key"
        assert validator.load_api_key([]) is None
    with mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "env-key"}, clear=True):
        assert validator.load_api_key([config]) == "env-key"


def test_ipsae_parses_both_interface_directions_and_ignores_headers(tmp_path):
    script = tmp_path / "vendor/ipsae/ipsae.py"
    script.parent.mkdir(parents=True)
    script.write_text("# synthetic dependency\n")
    work = tmp_path / "work"
    work.mkdir()
    def score(command, **kwargs):
        np.testing.assert_array_equal(np.load(work / "pae_model.npz")["pae"], [[0., 1.], [2., 0.]])
        (work / "model_10_10.txt").write_text("Chn1 Chn2 0 0 asym score\nX Y 0 0 asym 0.6 0 0 0.8\nY X 0 0 asym 0.7\n")
        return argparse.Namespace(returncode=0, stdout="", stderr="")
    with mock.patch.object(validator, "__file__", str(tmp_path / "scripts/validate_binders.py")), \
         mock.patch.object(validator, "IPSAE_SHA256", hashlib.sha256(script.read_bytes()).hexdigest()), \
         mock.patch.object(validator.subprocess, "run", side_effect=score):
        result = validator.run_ipsae(script, "cif", np.array([[0., 1.], [2., 0.]]), {"X": {"Y": 0.8}}, work)
    assert result["ipsae_min"] == 0.6
    assert result["ipsae_max"] == 0.7
    assert result["ipsae_asym"] == {"X->Y": 0.6, "Y->X": 0.7}


def test_cli_rejects_untrusted_binary_and_extracts_existing_pdb(tmp_path):
    (tmp_path / "configs").mkdir()
    (tmp_path / design.DEFAULT_CONFIG).write_text("{}")
    with mock.patch.dict("os.environ", {"COMPLEXA_REPO": str(tmp_path)}), \
         mock.patch.object(sys, "argv", ["complexa_design.py", "run", "--cli-bin", "/bin/sh"]), \
         mock.patch.object(design.subprocess, "run") as run:
        with pytest.raises(SystemExit) as error:
            design.main()
    assert error.value.code == 1
    run.assert_not_called()
    pdb = tmp_path / "complex.pdb"
    pdb.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 80.00           C\n")
    with mock.patch.object(sys, "argv", ["complexa_design.py", "extract", str(pdb)]), \
         contextlib.redirect_stdout(io.StringIO()) as output:
        design.main()
    result = json.loads(output.getvalue())
    assert result[0]["chains"] == {"A": {"len": 1, "seq": "A"}}


def test_repo_and_path_resolved_executable_need_an_installation(tmp_path):
    with mock.patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError):
            execution.complexa_repo()
    with mock.patch.dict("os.environ", {"COMPLEXA_REPO": str(tmp_path)}):
        with pytest.raises(ValueError):
            execution.complexa_repo()
        (tmp_path / "configs").mkdir()
        assert execution.complexa_repo() == tmp_path
    with mock.patch.object(execution.shutil, "which", return_value=None):
        with pytest.raises(ValueError):
            execution.complexa_executable("complexa", tmp_path)
    with pytest.raises(ValueError):
        execution.complexa_executable("relative/bin/complexa", tmp_path)
