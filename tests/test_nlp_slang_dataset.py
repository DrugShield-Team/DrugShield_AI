from src.ai_pipeline.nlp_classifier import HinglishSlangDetector, _load_reviewed_slang_lexicon


def test_loads_reviewed_english_and_hindi_terms_from_project_csv():
    lexicon = _load_reviewed_slang_lexicon()

    assert len(lexicon) > 100
    assert lexicon["maal"] == "cannabis"
    assert lexicon["ganja"] == "cannabis"


def test_detects_single_and_multiword_dataset_terms_in_messages():
    detector = HinglishSlangDetector()

    result = detector.analyze("Maal chahiye; the ganja is ready.")

    assert "maal" in result["detected_slangs"]
    assert "ganja" in result["detected_slangs"]
    assert "cannabis" in result["mapped_categories"]
    assert result["is_suspicious"] is True


def test_matching_respects_word_boundaries():
    detector = HinglishSlangDetector()

    result = detector.analyze("The seaweed is in the flowerpot.")

    assert result["detected_slangs"] == []
    assert result["is_suspicious"] is False


def test_normalization_maps_reviewed_phrases_to_category():
    detector = HinglishSlangDetector()

    normalized = detector.normalize_text("wee wee and GANJA")

    assert "cannabis" in normalized
