"""Offline transport and artifact checks; no hosted-service calls are made."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location(
    "hosted_search", Path(__file__).resolve().parents[1] / "scripts" / "hosted_search.py"
)
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)


def response(status=200, data=None):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


def alignments():
    return {"alignments": {
        db: {"a3m": {"alignment": ">query\nACDE\n>hit\nAC-E\n", "format": "a3m"}}
        for db in client.DATABASES
    }}


class HostedSearchTests(unittest.TestCase):
    def test_gateway_timeout_retries_once_then_stops(self):
        failures = [response(504), response(504), response(data=alignments())]
        with patch.object(client.requests, "post", side_effect=failures) as post, \
                patch.object(client.time, "sleep"):
            with self.assertRaisesRegex(client.SearchError, "HTTP 504.*Stopped after 2"):
                client.search("ACDE", list(client.DATABASES), "test-credential")
        self.assertEqual(post.call_count, 2)
        for call in post.call_args_list:
            self.assertEqual(call.kwargs["timeout"], (10, 300))
            self.assertFalse(call.kwargs["allow_redirects"])

    def test_transient_error_can_recover_without_changing_the_request(self):
        expected = alignments()
        with patch.object(client.requests, "post", side_effect=[response(503), response(data=expected)]) as post, \
                patch.object(client.time, "sleep"):
            actual = client.search("ACDE", list(client.DATABASES), "test-credential")
        self.assertEqual(actual, expected)
        self.assertEqual(post.call_args_list[0], post.call_args_list[1])

    def test_auth_error_and_redirect_are_not_retried(self):
        for status in [401, 403, 302]:
            with self.subTest(status=status), patch.object(client.requests, "post", return_value=response(status)) as post:
                with self.assertRaisesRegex(client.SearchError, f"HTTP {status}"):
                    client.search("ACDE", list(client.DATABASES), "test-credential")
                self.assertEqual(post.call_count, 1)

    def test_timeout_does_not_expose_exception_text(self):
        with patch.object(client.requests, "post", side_effect=client.requests.ReadTimeout("sensitive request details")) as post, \
                patch.object(client.time, "sleep"):
            with self.assertRaises(client.SearchError) as failure:
                client.search("ACDE", list(client.DATABASES), "test-credential")
        self.assertNotIn("sensitive", str(failure.exception))
        self.assertEqual(post.call_count, 2)

    def test_partial_or_empty_alignment_is_not_success(self):
        partial = alignments()
        del partial["alignments"][client.DATABASES[1]]
        empty = alignments()
        empty["alignments"][client.DATABASES[0]]["a3m"]["alignment"] = ">query\n"
        for result in [None, {}, partial, empty]:
            with self.subTest(result=result), patch.object(client.requests, "post", return_value=response(data=result)):
                with self.assertRaises(client.SearchError):
                    client.search("ACDE", list(client.DATABASES), "test-credential")

    def test_missing_key_and_unknown_database_fail_before_network(self):
        for databases, key in [(list(client.DATABASES), ""), (["../result"], "test-credential")]:
            with self.subTest(databases=databases), patch.object(client.requests, "post") as post:
                with self.assertRaises(client.SearchError):
                    client.search("ACDE", databases, key)
                post.assert_not_called()

    def test_cli_writes_actual_response_and_alignments(self):
        expected = alignments()
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "msa"
            args = ["hosted_search.py", "--sequence", "ACDE", "--output-dir", str(output)]
            with patch.object(client.sys, "argv", args), patch.dict(client.os.environ, {"NGC_API_KEY": "test-credential"}), \
                    patch.object(client.requests, "post", return_value=response(data=expected)), redirect_stdout(io.StringIO()):
                self.assertEqual(client.main(), 0)
            self.assertEqual(json.loads((output / "response.json").read_text()), expected)
            for database in client.DATABASES:
                self.assertEqual((output / f"{database}.a3m").read_text(), expected["alignments"][database]["a3m"]["alignment"])

    def test_cli_failure_leaves_no_success_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "msa"
            args = ["hosted_search.py", "--sequence", "ACDE", "--output-dir", str(output)]
            with patch.object(client.sys, "argv", args), patch.dict(client.os.environ, {"NGC_API_KEY": "test-credential"}), \
                    patch.object(client.requests, "post", return_value=response(504)), \
                    patch.object(client.time, "sleep"), redirect_stderr(io.StringIO()):
                self.assertEqual(client.main(), 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
