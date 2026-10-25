from src.ai_pipeline import message_analyzer


def test_missing_downloaded_slang_dataset_does_not_abort_analysis(monkeypatch):
    class Detector:
        def __init__(self, custom_lexicon=None):
            if custom_lexicon is None:
                raise FileNotFoundError("optional downloaded data is absent")

        def analyze(self, text):
            return {"original_text": text, "risk_score": 0.0}

    class Classifier:
        def analyze(self, text):
            return {
                "status": "predicted",
                "task": "drug_topic_classification",
                "label": "not_drug_related",
                "probability": 0.9,
                "class_probabilities": {"drug_related": 0.1},
            }

    monkeypatch.setattr(message_analyzer, "HinglishSlangDetector", Detector)
    monkeypatch.setattr(message_analyzer, "get_drug_topic_classifier", Classifier)

    result = message_analyzer.analyze_message("hello")

    assert result["text_analysis"]["lexicon_status"] == "missing_reviewed_dataset"
    assert result["message_classification"]["status"] == "predicted"
