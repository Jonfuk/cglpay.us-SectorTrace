from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from pipeline.transports.powerbi import PowerBICapture, parse_querydata


def test_parse_querydata_extracts_cells_and_keeps_context():
    body = {
        "results": [
            {
                "result": {
                    "data": {
                        "dsr": {
                            "DS": [
                                {
                                    "N": "DS0",
                                    "PH": [
                                        {
                                            "DM0": [
                                                {
                                                    "C": [
                                                        {"V": "Manchester"},
                                                        {"V": 42, "N": "Number in treatment"},
                                                    ]
                                                }
                                            ]
                                        }
                                    ],
                                }
                            ],
                        },
                    },
                },
            }
        ],
    }
    rows = parse_querydata(json.dumps(body))
    assert len(rows) == 2
    assert rows[0]["value_text"] == "Manchester"
    assert rows[0]["value"] is None
    assert rows[1]["metric_raw"] == "Number in treatment"
    assert rows[1]["value"] == 42
    assert "DM0" in rows[0]["cell_path"]


def test_parse_querydata_rejects_unknown_shape():
    with pytest.raises(ValueError, match="no recognised cell arrays"):
        parse_querydata('{"results": []}')


def test_parse_querydata_preserves_disclosure_text_as_null():
    rows = parse_querydata('{"results":[{"C":[{"V":"c"},{"V":"1,234"}]}]}')
    assert rows[0]["value"] is None
    assert rows[0]["value_text"] == "c"
    assert rows[1]["value"] == 1234


def test_parse_querydata_resolves_value_dictionary_labels():
    body = {
        "results": [
            {
                "result": {
                    "data": {
                        "descriptor": {
                            "Select": [
                                {"Value": "G0", "Name": "Indicator name"},
                                {"Value": "G1", "Name": "Indicator definition"},
                            ]
                        },
                        "dsr": {
                            "DS": [
                                {
                                    "PH": [
                                        {
                                            "DM0": [
                                                {
                                                    "S": [
                                                        {"N": "G0", "DN": "D0"},
                                                        {"N": "G1", "DN": "D1"},
                                                    ],
                                                    "C": [0, 0],
                                                }
                                            ]
                                        }
                                    ],
                                    "ValueDicts": {
                                        "D0": ["Total"],
                                        "D1": ["People in treatment"],
                                    },
                                }
                            ]
                        },
                    }
                }
            }
        ]
    }
    rows = parse_querydata(json.dumps(body))
    assert rows[0]["metric_raw"] == "Indicator name"
    assert rows[0]["value"] is None
    assert rows[0]["value_text"] == "Total"
    assert rows[1]["metric_raw"] == "Indicator definition"
    assert rows[1]["value_text"] == "People in treatment"


def test_capture_redacts_volatile_query_parameters():
    body = b'{"C":[{"V":1}]}'
    capture = PowerBICapture(
        dashboard_url="https://www.ndtms.net/ViewIt/Adult",
        response_url=("https://wabi.example/querydata?uid=secret&foo=bar&activityId=also-secret"),
        method="POST",
        status_code=200,
        content_type="application/json",
        body=body,
        request_body_sha256=hashlib.sha256(b"request").hexdigest(),
        retrieved_at=datetime.now(timezone.utc),
        sequence=0,
    )
    assert capture.canonical_response_url == "https://wabi.example/querydata?foo=bar"
    assert capture.payload_sha256 == hashlib.sha256(body).hexdigest()
