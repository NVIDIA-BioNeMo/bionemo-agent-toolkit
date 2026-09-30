"""ProteinMPNN client contracts using synthetic data; no GPU or API key required."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import requests


SCRIPT = Path(__file__).resolve().parents[1] / "nim-skills" / "proteinmpnn-nim" / "scripts" / "design.py"
spec = importlib.util.spec_from_file_location("proteinmpnn_design", SCRIPT)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


def response_data(native=True):
    prefix = ">input, score=9.1, fixed_chains=[], designed_chains=['A']\nAAA\n" if native else ""
    return {"mfasta": prefix + ">T=0.1, sample=1, score=1.2\nAC\nD\n"
            ">T=0.1, sample=2, score=0.8\nEFG\n", "scores": [1.2, 0.8]}


def response(data=None, status=200):
    value = requests.Response()
    value.status_code = status
    value._content = json.dumps(response_data() if data is None else data).encode()
    return value


class ResultTests(unittest.TestCase):
    def test_native_is_excluded_without_shifting_design_scores(self):
        summary = client.design_results(response_data(), 2)
        self.assertEqual((summary["generated_count"], summary["native_count"]), (2, 1))
        self.assertEqual([(row["sequence"], row["score"]) for row in summary["sequences"]],
                         [("ACD", 1.2), ("EFG", 0.8)])

    def test_score_array_can_include_the_native_record(self):
        data = response_data()
        data["scores"] = [9.1, 1.2, 0.8]
        summary = client.design_results(data, 2)
        self.assertEqual(summary["scores"], [1.2, 0.8])

    def test_native_only_response_cannot_count_as_one_design(self):
        data = {"mfasta": ">input, score=9.1, fixed_chains=[], designed_chains=['A']\nAAA\n", "scores": [9.1]}
        with self.assertRaises(ValueError):
            client.design_results(data, 1)

    def test_no_native_record_keeps_every_design_and_chain_separator(self):
        data = response_data(native=False)
        data["mfasta"] = data["mfasta"].replace("EFG", "EFG/ACD")
        summary = client.design_results(data, 2)
        self.assertEqual(summary["native_count"], 0)
        self.assertEqual(summary["sequences"][1]["sequence"], "EFG/ACD")
        self.assertEqual(summary["scores"], [1.2, 0.8])

    def test_header_fallback_uses_design_score_not_global_or_native_score(self):
        data = response_data()
        del data["scores"]
        data["mfasta"] = data["mfasta"].replace("sample=1, score=1.2", "sample=1, global_score=7.3, score=1.2")
        summary = client.design_results(data, 2)
        self.assertEqual(summary["scores"], [1.2, 0.8])
        self.assertEqual(summary["score_source"], "mfasta.header.score")

    def test_invalid_responses_never_invent_or_silently_truncate_results(self):
        bad = [{}, [], {"mfasta": ""}, {"mfasta": "ACD"},
               {"mfasta": ">design\nACD\n", "scores": [1, 2]},
               {**response_data(), "scores": [1]},
               {**response_data(), "scores": [1, 2, 3, 4]},
               {**response_data(), "scores": [True, 0.8]},
               {**response_data(), "scores": [float("nan"), 0.8]},
               {**response_data(), "scores": "1.2,0.8"},
               {"mfasta": ">sample=1\nACD\n>sample=2\nEFG\n"},
               {"mfasta": ">sample=1\nAC?\n>sample=2\nEFG\n", "scores": [1, 2]},
               {"mfasta": ">sample=1\n\n>sample=2\nEFG\n", "scores": [1, 2]},
               {"mfasta": ">sample=1\nACD\n>sample=2\nEFG\n>sample=3\nHIK\n", "scores": [1, 2, 3]}]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(ValueError):
                client.design_results(data, 2)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "run"
        self.pdb = self.root / "user-backbone.pdb"
        self.pdb.write_text("HEADER    synthetic test fixture\nATOM      1  CA  ALA A   1       0.000   0.000   0.000\nEND\n")
        self.args = argparse.Namespace(pdb=self.pdb, mode="hosted", num_sequences=2,
                                       temperature=0.1, chains=None, omit_aas=None, soluble=False,
                                       ca_only=False, seed=None, timeout=30, output_dir=self.output)

    def test_hosted_execution_saves_and_prints_real_results_without_key(self):
        self.args.chains = ["A"]
        self.args.omit_aas = ["C"]
        self.args.seed = 7
        stdout = io.StringIO()
        with patch.dict(os.environ, {"NGC_API_KEY": "test-secret", "NIM_API_MODE": "local"}, clear=True), \
                patch.object(client.requests, "post", return_value=response()) as post, redirect_stdout(stdout):
            summary = client.design(self.args)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], client.HOSTED_URL)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-secret")
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 30))
        saved = json.loads((self.output / "request.json").read_text())
        self.assertEqual(saved, post.call_args.kwargs["json"])
        self.assertEqual(saved["input_pdb"], self.pdb.read_text())
        self.assertEqual((saved["num_seq_per_target"], saved["sampling_temp"], saved["random_seed"]), (2, [0.1], 7))
        self.assertEqual((saved["input_pdb_chains"], saved["omit_AAs"]), (["A"], ["C"]))
        self.assertEqual((self.output / "designed_sequences.fa").read_text(), response_data()["mfasta"])
        self.assertEqual(json.loads((self.output / "response.json").read_text()), response_data())
        self.assertEqual(json.loads((self.output / "summary.json").read_text()), summary)
        self.assertIn(json.dumps(summary, indent=2), stdout.getvalue())
        self.assertNotIn(self.pdb.read_text(), stdout.getvalue())
        self.assertNotIn("test-secret", stdout.getvalue())
        for path in self.output.iterdir():
            self.assertNotIn(b"test-secret", path.read_bytes())

    def test_failure_keeps_exact_body_without_success_artifacts(self):
        cases = [response(status=code) for code in (202, 302, 401, 503)]
        malformed = response()
        malformed._content = b'{"mfasta":'
        cases.extend([malformed, response({**response_data(), "scores": [float("nan"), 0.8]}),
                      response({**response_data(), "scores": [1]})])
        for index, result in enumerate(cases):
            with self.subTest(index=index):
                self.args.output_dir = self.root / str(index)
                stdout = io.StringIO()
                with patch.dict(os.environ, {"NGC_API_KEY": "test-secret"}, clear=True), \
                        patch.object(client.requests, "post", return_value=result) as post, redirect_stdout(stdout), \
                        self.assertRaises((ValueError, RuntimeError)):
                    client.design(self.args)
                self.assertEqual(post.call_count, 1)
                self.assertEqual((self.args.output_dir / "response.raw").read_bytes(), result.content)
                self.assertFalse((self.args.output_dir / "designed_sequences.fa").exists())
                self.assertFalse((self.args.output_dir / "summary.json").exists())
                self.assertNotIn('"status": "completed"', stdout.getvalue())

    def test_crlf_fasta_is_preserved_exactly(self):
        data = response_data()
        data["mfasta"] = data["mfasta"].replace("\n", "\r\n")
        with patch.dict(os.environ, {"NGC_API_KEY": "test-key"}), \
                patch.object(client.requests, "post", return_value=response(data)), redirect_stdout(io.StringIO()):
            summary = client.design(self.args)
        self.assertEqual(summary["scores"], [1.2, 0.8])
        self.assertEqual((self.output / "designed_sequences.fa").read_bytes(), data["mfasta"].encode())

    def test_requires_mode_and_hosted_key_before_request(self):
        for mode in [None, "hosted"]:
            self.args.mode = mode
            with self.subTest(mode=mode), patch.dict(os.environ, {}, clear=True), \
                    patch.object(client.requests, "post") as post, self.assertRaises(ValueError):
                client.design(self.args)
            post.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_existing_directory_is_not_overwritten_or_resubmitted(self):
        self.output.mkdir()
        for existing_file in [False, True]:
            if existing_file:
                (self.output / "summary.json").write_text("existing")
            with self.subTest(existing_file=existing_file), patch.dict(os.environ, {"NGC_API_KEY": "test-key"}), \
                    patch.object(client.requests, "post") as post, self.assertRaises(FileExistsError):
                client.design(self.args)
            post.assert_not_called()
        self.assertEqual((self.output / "summary.json").read_text(), "existing")

    def test_concurrent_runs_make_only_one_request(self):
        ready = threading.Barrier(2)
        mkdir = Path.mkdir

        def synchronized_mkdir(path, *args, **kwargs):
            if path == self.output:
                ready.wait(timeout=5)
            return mkdir(path, *args, **kwargs)

        def run(seed):
            try:
                return client.design(argparse.Namespace(**{**vars(self.args), "seed": seed}))
            except FileExistsError:
                return None

        with patch.dict(os.environ, {"NGC_API_KEY": "test-key"}), patch.object(Path, "mkdir", synchronized_mkdir), \
                patch.object(client.requests, "post", return_value=response()) as post, redirect_stdout(io.StringIO()):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(run, [10, 20]))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(json.loads((self.output / "request.json").read_text()), post.call_args.kwargs["json"])

    def test_cli_local_execution_preserves_actual_scores_and_omits_credentials(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                received.append((self.path, dict(self.headers), json.loads(body)))
                data = json.dumps(response_data()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {"PROTEINMPNN_NIM_URL": f"http://127.0.0.1:{server.server_port}", "NGC_API_KEY": "must-not-send"}
            completed = subprocess.run([sys.executable, str(SCRIPT), "--mode", "local", "--pdb", str(self.pdb),
                                        "--num-sequences", "2", "--output-dir", str(self.output)],
                                       env=env, capture_output=True, text=True, timeout=15)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], "/biology/ipd/proteinmpnn/predict")
        self.assertNotIn("Authorization", received[0][1])
        self.assertEqual(received[0][2]["input_pdb"], self.pdb.read_text())
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["scores"], [1.2, 0.8])
        self.assertEqual(summary["generated_count"], 2)
        self.assertIn('"sequence": "ACD"', completed.stdout)
        self.assertIn(str(self.output / "designed_sequences.fa"), completed.stdout)


if __name__ == "__main__":
    unittest.main()
