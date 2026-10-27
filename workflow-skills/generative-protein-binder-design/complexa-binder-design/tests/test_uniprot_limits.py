"""Budget regressions for the vendored UniProt HTTP adapter (no network)."""
import gzip
import importlib.util
import io
import json
from pathlib import Path
from unittest import mock

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "vendor/science-skills/uniprot_database/scripts/uniprot_tools.py"
SPEC = importlib.util.spec_from_file_location("bounded_uniprot", SOURCE)
U = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(U)


def page(records, next_page=False):
    headers = {"Link": '<https://rest.uniprot.org/uniprotkb/search?cursor=next>; rel="next"'} if next_page else {}
    return U._HttpResponse(headers, json.dumps({"results": records}).encode())


@pytest.mark.parametrize("limit", [0, -1, 10001, True])
def test_invalid_budget_makes_no_requests(limit):
    with mock.patch.object(U.CLIENT, "fetch") as fetch:
        with pytest.raises(ValueError):
            list(U.search_proteins("query", limit=limit))
    fetch.assert_not_called()


def test_default_limit_trims_server_overproduction():
    with mock.patch.object(U.CLIENT, "fetch", return_value=page(list(range(500)), True)) as fetch:
        result = list(U.search_proteins("query"))
    assert len(result[0]["results"]) == 100
    assert fetch.call_count == 1


def test_pagination_stops_at_exact_explicit_record_budget():
    with mock.patch.object(U.CLIENT, "fetch", side_effect=[page(list(range(500)), True), page(list(range(500)), True)]) as fetch:
        result = list(U.search_proteins("query", limit=501))
    assert [len(p["results"]) for p in result] == [500, 1]
    assert fetch.call_count == 2


def test_repeated_short_pages_cannot_run_forever():
    with mock.patch.object(U.CLIENT, "fetch", return_value=page(["record"], True)) as fetch:
        with pytest.raises(U.UniProtError, match="page budget"):
            list(U.search_proteins("query", limit=1000))
    assert fetch.call_count == 2


def test_stream_limits_fasta_entries_without_truncating_sequences():
    response = U._HttpResponse({}, b">first\nAAAA\nAAAA\n>second\nGGGG\n")
    with mock.patch.object(U.CLIENT, "fetch", return_value=response):
        result = list(U.stream_results("query", output_format="fasta", limit=1))
    assert result == [">first", "AAAA", "AAAA"]


def test_response_and_decompressed_bytes_are_bounded():
    with mock.patch.object(U, "MAX_RESPONSE_BYTES", 16):
        with pytest.raises(ValueError):
            U._read_bounded(io.BytesIO(b"x" * 17))
        with pytest.raises(ValueError):
            U._decode_bytes(gzip.compress(b"x" * 1000))
        assert U._decode_bytes(gzip.compress(b"ok")) == b"ok"


def test_mapping_poll_budget_stops_pending_jobs():
    with mock.patch.object(U, "MAX_MAPPING_POLLS", 2), \
         mock.patch.object(U, "_fetch", side_effect=[{"jobId": "test"}, {"jobStatus": "RUNNING"}, {"jobStatus": "RUNNING"}]) as fetch, \
         mock.patch.object(U.time, "sleep"):
        with pytest.raises(U.UniProtError, match="poll budget"):
            U.run_id_mapping(["P04637"], "UniProtKB_AC-ID", "UniRef90")
    assert fetch.call_count == 3


def test_client_honors_rate_limit_and_checks_next_url_host():
    client = U._HttpClient(U.BASE_URL)
    response = mock.MagicMock()
    response.__enter__.return_value.headers.get_content_charset.return_value = "utf-8"
    response.__enter__.return_value.read.return_value = b"{}"
    with mock.patch.object(U.urllib.request, "urlopen", return_value=response), \
         mock.patch.object(U.time, "monotonic", side_effect=[0.0, 0.2, 1.0]), \
         mock.patch.object(U.time, "sleep") as sleep:
        client.fetch(U.BASE_URL + "/uniprotkb/P04637")
        client.fetch(U.BASE_URL + "/uniprotkb/P04637")
    sleep.assert_called_once_with(0.8)
    with pytest.raises(ValueError):
        client._request("https://other.invalid/search")
