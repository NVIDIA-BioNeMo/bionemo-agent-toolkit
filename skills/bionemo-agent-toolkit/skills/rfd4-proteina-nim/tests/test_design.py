"""Client behavior tests with synthetic responses and a loopback HTTP service."""

import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("design_client", ROOT / "scripts/design.py")
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)


def request_body():
    return json.loads((ROOT / "assets/requests/02_condition_spec_monomer.json").read_text())


def response_body(count=1):
    return {
        "request_id": "synthetic-test", "task": "generation", "duration_ms": 1,
        "model": {"execution_backend": "synthetic", "oracle": []},
        "runtime": {"nim_version": "synthetic"},
        "schedule": {"num_steps": 60, "trunk_passes": 185}, "search": None,
        "warnings": [], "aggregated_metrics": [],
        "designs": [{
            "design_id": f"opaque_{i}", "replicate_index": i, "origin": "sample", "seed": 42 + i,
            "sequence": "AGX", "structure": {"format": "mmcif", "filename": f"out_{i}.cif", "content": "data_synthetic\n#\n"},
            "metrics": {"example.value": None}, "diagnostics": {"all_coordinates_finite": True}
        } for i in range(count)]
    }


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.request = self.root / "input.json"
        self.request.write_text(json.dumps(request_body()))
        self.output = self.root / "run"

    def invoke(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return client.main(["--request", str(self.request), "--output-dir", str(self.output), *extra])

    def extract(self, result, body=None):
        if body is not None:
            self.request.write_text(json.dumps(body))
        path = self.root / "result.json"
        path.write_text(json.dumps(result))
        return self.invoke("--response-json", str(path))

    @contextlib.contextmanager
    def server(self, status=200, raw=None, response_headers=None):
        seen = []
        raw = json.dumps(response_body()).encode() if raw is None else raw

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append({"path": self.path, "headers": self.headers,
                             "body": self.rfile.read(int(self.headers.get("Content-Length", 0)))})
                self.send_response(status)
                for key, value in (response_headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", seen
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_staging_preserves_payload_and_never_sends_environment_credentials(self):
        raw = json.dumps(response_body()).encode()
        with self.server(raw=raw) as (url, seen), patch.object(client, "STAGING_URL", url + "/predict"), \
                patch.dict(os.environ, {"NGC_API_KEY_STAGING": "test-only-secret", "NGC_API_KEY": "another-test-secret"}):
            self.assertEqual(self.invoke("--mode", "staging"), 0)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["body"], self.request.read_bytes())
        self.assertEqual(seen[0]["headers"]["NVCF-POLL-SECONDS"], "300")
        self.assertIsNone(seen[0]["headers"].get("Authorization"))
        self.assertEqual((self.output / "response.raw").read_bytes(), raw)
        self.assertEqual((self.output / "request.json").read_bytes(), self.request.read_bytes())
        self.assertTrue((self.output / "sequences.fasta").is_file())
        self.assertNotIn("test-only-secret", (self.output / "transport.json").read_text())

    def test_local_endpoint_and_no_auth(self):
        with self.server() as (url, seen), patch.dict(os.environ, {"RFD4_NIM_URL": url}):
            self.assertEqual(self.invoke("--mode", "local"), 0)
        self.assertEqual(seen[0]["path"], client.API_PATH)
        self.assertIsNone(seen[0]["headers"].get("Authorization"))
        self.assertIsNone(seen[0]["headers"].get("NVCF-POLL-SECONDS"))

    def test_dry_run_does_not_connect(self):
        with patch.object(client, "post") as post:
            self.assertEqual(self.invoke("--dry-run"), 0)
        post.assert_not_called()
        self.assertEqual(json.loads((self.output / "transport.json").read_text())["status"], "prepared_not_submitted")
        self.assertFalse((self.output / "response.raw").exists())

    def test_existing_output_is_not_overwritten_or_submitted(self):
        self.output.mkdir()
        (self.output / "request.json").write_text("existing work")
        with patch.object(client, "post") as post:
            self.assertEqual(self.invoke(), 1)
        post.assert_not_called()
        self.assertEqual((self.output / "request.json").read_text(), "existing work")

    def test_202_preserves_job_without_reporting_completion_or_reposting(self):
        with self.server(202, b'{"status":"pending"}', {"NVCF-REQID": "test-job"}) as (url, seen):
            self.assertEqual(self.invoke("--mode", "local", "--base-url", url), 3)
        self.assertEqual(len(seen), 1)
        self.assertFalse((self.output / "summary.json").exists())
        meta = json.loads((self.output / "transport.json").read_text())
        self.assertEqual(meta["status"], "pending")
        self.assertEqual(meta["response_headers"]["NVCF-REQID"], "test-job")

    def test_503_is_not_retried(self):
        with self.server(503, b'{"error":{"code":"service_busy"}}') as (url, seen):
            self.assertEqual(self.invoke("--mode", "local", "--base-url", url), 1)
        self.assertEqual(len(seen), 1)
        self.assertIn("service_busy", (self.output / "response.raw").read_text())

    def test_redirect_is_not_followed(self):
        with self.server(302, b"redirect", {"Location": "http://127.0.0.1:1/elsewhere"}) as (url, seen):
            self.assertEqual(self.invoke("--mode", "local", "--base-url", url), 1)
        self.assertEqual(len(seen), 1)
        self.assertEqual(json.loads((self.output / "transport.json").read_text())["http_status"], 302)

    def test_html_200_is_preserved_as_failure(self):
        with self.server(200, b"<html>Not a result</html>") as (url, _):
            self.assertEqual(self.invoke("--mode", "local", "--base-url", url), 1)
        self.assertTrue((self.output / "response.raw").is_file())
        self.assertFalse((self.output / "summary.json").exists())

    def test_timeout_keeps_request_and_failure_metadata(self):
        with patch.object(client, "post", side_effect=TimeoutError("timed out")) as post:
            self.assertEqual(self.invoke(), 1)
        post.assert_called_once()
        self.assertTrue((self.output / "request.json").is_file())
        self.assertEqual(json.loads((self.output / "transport.json").read_text())["status"], "failed")

    def test_filenames_and_fasta_ids_cannot_escape_output_directory(self):
        result = response_body(2)
        for design in result["designs"]:
            design["structure"]["filename"] = "../../escaped.cif"
            design["design_id"] = "opaque\n>injected"
        body = request_body()
        body["sampling"]["num_replicates"] = 2
        self.assertEqual(self.extract(result, body), 0)
        self.assertEqual(len(list(self.output.glob("*.cif"))), 2)
        self.assertFalse((self.root / "escaped.cif").exists())
        self.assertEqual((self.output / "sequences.fasta").read_text().count(">"), 2)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["designs"][0]["design_id"], "opaque\n>injected")
        self.assertEqual(summary["transport_source"], "saved_response")

    def test_nonfinite_diagnostics_fail_but_preserve_artifacts(self):
        result = response_body()
        result["designs"][0]["diagnostics"]["all_coordinates_finite"] = False
        self.assertEqual(self.extract(result), 1)
        self.assertTrue((self.output / "response.json").exists())
        self.assertEqual(json.loads((self.output / "summary.json").read_text())["status"], "failed_validation")

    def test_plain_sampling_count_mismatch_fails(self):
        self.assertEqual(self.extract(response_body(2)), 1)

    def test_search_final_and_intermediate_count_is_not_replicate_count(self):
        body = request_body()
        body["search"] = {"step_checkpoints": [0, 30, 60], "reward_metrics_tags": ["design"],
                          "weights": {"clash_metrics.frac_atoms_clashing_1p5A": -1}}
        result = response_body(3)
        result["search"] = {"rollouts": 10}
        for i, design in enumerate(result["designs"]):
            design.update(origin="search_intermediate" if i == 2 else "search_final", replicate_index=0)
        self.assertEqual(self.extract(result, body), 0)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["origin_counts"], {"search_final": 2, "search_intermediate": 1})

    def test_output_suppression_is_respected(self):
        body = request_body()
        body["output"] = {"structure_format": "none", "include_sequence": False}
        result = response_body()
        result["designs"][0].update(structure=None, sequence=None)
        self.assertEqual(self.extract(result, body), 0)
        self.assertFalse((self.output / "sequences.fasta").exists())
        self.assertEqual(list(self.output.glob("*.cif")), [])

    def test_null_metric_and_aggregate_denominator_preserved(self):
        result = response_body()
        result["aggregated_metrics"] = [{"metric": "example.pass", "value": 1.0, "reduction": "mean", "n": 1}]
        self.assertEqual(self.extract(result), 0)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertIsNone(summary["designs"][0]["metrics"]["example.value"])
        self.assertEqual(summary["aggregated_metrics"], result["aggregated_metrics"])

    def test_empty_requested_metrics_produce_notice(self):
        result = response_body()
        result["designs"][0]["metrics"] = {}
        self.assertEqual(self.extract(result), 0)
        self.assertTrue(json.loads((self.output / "summary.json").read_text())["client_notices"])

    def test_missing_designs_is_not_success(self):
        self.assertEqual(self.extract({"designs": []}), 1)

    def test_malformed_origin_is_saved_as_validation_failure(self):
        result = response_body()
        result["designs"][0]["origin"] = ["sample"]
        self.assertEqual(self.extract(result), 1)
        self.assertEqual(json.loads((self.output / "summary.json").read_text())["status"], "failed_validation")

    def test_old_scaffold_response_is_not_success(self):
        self.assertEqual(self.extract({"designs": [{"name": "design_0", "output_pdb": "ATOM", "score": 0.85}]}), 1)

    def test_preflight_rejects_old_api_and_unattached_spec_and_pdb(self):
        cases = [{"contigs": "100-100"}]
        body = request_body()
        body["input"]["spec"]["input"] = "/server/private.cif"
        cases.append(body)
        body = request_body()
        body["input"]["files"][0]["content"] = "ATOM      1  CA  ALA"
        cases.append(body)
        for body in cases:
            with self.subTest(body=str(body)[:100]), self.assertRaises(client.ClientError):
                client.validate_request(body)

    def test_integer_boolean_and_batched_search_are_rejected(self):
        for value in (True, 0, -1, 1.5):
            body = request_body()
            body["sampling"]["num_replicates"] = value
            with self.subTest(value=value), self.assertRaises(client.ClientError):
                client.validate_request(body)
        body = request_body()
        body["sampling"]["num_replicates"] = 3
        body["search"] = {"step_checkpoints": [0, 30, 60]}
        with self.assertRaises(client.ClientError):
            client.validate_request(body)

    def test_endpoint_rejects_credentials_query_and_full_route(self):
        for url in ("http://user:secret@host", "http://host?token=foo", "http://host" + client.API_PATH):
            with self.subTest(url=url), self.assertRaises(client.ClientError):
                client.endpoint("local", url)

    def test_nonfinite_json_is_rejected(self):
        with self.assertRaises(client.ClientError):
            client.load_json('{"seed": NaN}')

    def test_malformed_task_and_discriminator_fail_before_submission(self):
        for field in ("task", "format"):
            body = request_body()
            if field == "task":
                body["task"] = ["generation"]
            else:
                body["input"]["format"] = ["condition_spec"]
            self.request.write_text(json.dumps(body))
            with patch.object(client, "post") as post:
                self.assertEqual(self.invoke(), 1)
            post.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_bundled_requests_match_upstream_hashes_and_pass_preflight(self):
        manifest = json.loads((ROOT / "assets/source-manifest.json").read_text())
        for item in manifest["files"]:
            with self.subTest(path=item["path"]):
                raw = (ROOT / item["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])
                client.validate_request(json.loads(raw))


if __name__ == "__main__":
    unittest.main()
