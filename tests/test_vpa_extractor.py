from src.ai_pipeline.vpa_extractor import extract_vpa_candidates


def test_extracts_vpa_candidates_from_text_with_source():
    result = extract_vpa_candidates(
        "Send payment to sample.user-7@okaxis now.", source="message_text"
    )

    assert result == [{
        "candidate": "sample.user-7@okaxis",
        "source": "message_text",
        "evidence_type": "vpa_pattern",
    }]


def test_extracts_and_url_decodes_upi_payee_parameter():
    result = extract_vpa_candidates(
        "Pay here: upi://pay?pa=samplemerchant%40okaxis&pn=Sample%20Shop",
        source="decoded_qr_payload",
    )

    assert result == [{
        "candidate": "samplemerchant@okaxis",
        "source": "decoded_qr_payload",
        "evidence_type": "upi_uri_pa",
    }]


def test_upi_uri_candidate_is_not_duplicated_as_generic_match():
    result = extract_vpa_candidates("upi://pay?pa=merchant@ybl&cu=INR")

    assert len(result) == 1
    assert result[0]["candidate"] == "merchant@ybl"
    assert result[0]["evidence_type"] == "upi_uri_pa"


def test_extracts_multiple_candidates_case_insensitively_deduplicated():
    result = extract_vpa_candidates(
        "one@okaxis, ONE@OKAXIS, and two@ybl"
    )

    assert [item["candidate"] for item in result] == ["one@okaxis", "two@ybl"]


def test_rejects_malformed_candidates_but_keeps_provider_agnostic_shape():
    result = extract_vpa_candidates(
        "bad..name@okaxis, trailing-@okaxis, x@y, prefixmerchant@yblsuffix.com"
    )

    # A provider-agnostic parser cannot distinguish an email from a VPA
    # solely by syntax, so this remains a candidate for downstream review.
    assert [item["candidate"] for item in result] == ["prefixmerchant@yblsuffix.com"]


def test_extracts_candidate_from_html_escaped_upi_uri():
    result = extract_vpa_candidates("upi://pay?pa=merchant%40oksbi&amp;cu=INR")

    assert result[0]["candidate"] == "merchant@oksbi"
    assert result[0]["evidence_type"] == "upi_uri_pa"


def test_empty_and_non_string_input_returns_empty_list():
    assert extract_vpa_candidates("") == []
    assert extract_vpa_candidates(None) == []
