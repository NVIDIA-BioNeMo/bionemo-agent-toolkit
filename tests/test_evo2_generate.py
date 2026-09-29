"""Client contract tests with synthetic responses; no model or API credentials required."""

import argparse
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


SCRIPT = Path(__file__).resolve().parents[1] / "nim-skills" / "evo2-nim" / "scripts" / "generate.py"
spec = importlib.util.spec_from_file_location("evo2_generate", SCRIPT)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


def response_data():
    return {"sequence": "ACGTACGT", "sampled_probs": [0.5] * 8,
            "elapsed_ms": 125, "elapsed_ms_per_token": [1.0] * 8}


def response(data=None, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(response_data() if data is None else data).encode()
    return result


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "run"
        self.args = argparse.Namespace(sequence=" acgt\nacgt ", mode="hosted", num_tokens=8,
                                       temperature=0.7, top_k=3, top_p=0.0, seed=42,
                                       timeout=30, output_dir=self.output)

    def test_hosted_request_saves_actual_data_and_never_saves_key(self):
        log = io.StringIO()
        with patch.dict(os.environ, {"NGC_API_KEY": "test-credential"}, clear=True), \
                patch.object(client.requests, "post", return_value=response()) as post, redirect_stdout(log):
            summary = client.generate(self.args)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], client.HOSTED_URL)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-credential")
        request = json.loads((self.output / "request.json").read_text())
        self.assertEqual(request, post.call_args.kwargs["json"])
        self.assertEqual((request["sequence"], request["random_seed"], request["num_tokens"]), ("ACGTACGT", 42, 8))
        self.assertTrue(request["enable_sampled_probs"])
        self.assertEqual(json.loads((self.output / "response.json").read_text()), response_data())
        self.assertEqual((self.output / "generated.fasta").read_text().splitlines()[1], "ACGTACGT")
        self.assertEqual(summary["elapsed_ms"], 125)
        self.assertEqual(summary["sampled_probs"]["count"], 8)
        self.assertEqual(summary["gc_fraction"], 0.5)
        self.assertEqual(summary["status"], "completed")
        self.assertNotIn("test-credential", log.getvalue())
        for path in self.output.iterdir():
            self.assertNotIn("test-credential", path.read_text())

    def test_invalid_input_or_missing_key_never_calls_api(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(client.requests, "post") as post:
            with self.assertRaisesRegex(ValueError, "NGC_API_KEY"):
                client.generate(self.args)
            for sequence in ["", "NNNN", "ACGT>header"]:
                self.args.sequence = sequence
                with self.assertRaisesRegex(ValueError, "A/C/G/T"):
                    client.generate(self.args)
            post.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_invalid_responses_cannot_produce_success_artifacts(self):
        bad_values = [("sequence", ""), ("sequence", "ACGTACGN"), ("sequence", "ACGT"),
                      ("sampled_probs", None), ("sampled_probs", [0.5]),
                      ("sampled_probs", [1.1] * 8), ("sampled_probs", [True] * 8),
                      ("elapsed_ms", -1), ("elapsed_ms_per_token", [1.0])]
        for index, (field, value) in enumerate(bad_values):
            with self.subTest(field=field, value=value):
                self.args.output_dir = self.output / str(index)
                data = response_data()
                data[field] = value
                with patch.dict(os.environ, {"NGC_API_KEY": "test-key"}, clear=True), \
                        patch.object(client.requests, "post", return_value=response(data)), \
                        redirect_stdout(io.StringIO()):
                    with self.assertRaises(ValueError):
                        client.generate(self.args)
                self.assertTrue((self.args.output_dir / "response.json").is_file())
                self.assertFalse((self.args.output_dir / "generated.fasta").exists())
                self.assertFalse((self.args.output_dir / "metrics.json").exists())

    def test_http_failure_and_pending_response_are_not_success(self):
        for status in [202, 302, 401, 503]:
            with self.subTest(status=status):
                self.args.output_dir = self.output / str(status)
                with patch.dict(os.environ, {"NGC_API_KEY": "test-key"}, clear=True), \
                        patch.object(client.requests, "post", return_value=response(status=status)) as post, \
                        redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, f"HTTP {status}"):
                        client.generate(self.args)
                self.assertEqual(post.call_count, 1)
                self.assertFalse((self.args.output_dir / "generated.fasta").exists())

    def test_existing_outputs_are_not_overwritten_or_resubmitted(self):
        self.output.mkdir()
        existing = self.output / "response.json"
        existing.write_text('{"existing": true}\n')
        with patch.dict(os.environ, {"NGC_API_KEY": "test-key"}, clear=True), patch.object(client.requests, "post") as post:
            with self.assertRaises(FileExistsError):
                client.generate(self.args)
            post.assert_not_called()
        self.assertEqual(existing.read_text(), '{"existing": true}\n')

    def test_cli_executes_local_request_and_reports_persisted_results(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, dict(self.headers), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                body = json.dumps(response_data()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {"EVO2_NIM_URL": f"http://127.0.0.1:{server.server_port}", "NGC_API_KEY": "must-not-be-sent"}
            result = subprocess.run([sys.executable, str(SCRIPT), "--mode", "local", "--sequence", "ACGT",
                                     "--num-tokens", "8", "--output-dir", str(self.output)],
                                    env=env, capture_output=True, text=True, timeout=15)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], "/biology/arc/evo2/generate")
        self.assertNotIn("Authorization", received[0][1])
        self.assertEqual(received[0][2]["sequence"], "ACGT")
        self.assertIn('"sequence": "ACGTACGT"', result.stdout)
        self.assertIn('"elapsed_ms": 125', result.stdout)
        self.assertEqual(json.loads((self.output / "metrics.json").read_text())["generated_bases"], 8)


if __name__ == "__main__":
    unittest.main()
