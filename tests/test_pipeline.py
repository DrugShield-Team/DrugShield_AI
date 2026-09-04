import json
from pathlib import Path


def test_raw_data_exists():
    raw_file = Path("data/raw/ingested_raw_data.json")
    assert raw_file.exists(), "Raw ingested data file was not found!"


def test_processed_data_output():
    processed_file = Path("data/processed/processed_data.json")
    assert processed_file.exists(), "Processed data file was not found!"

    with open(processed_file, "r") as f:
        data = json.load(f)

    assert len(data) > 0, "Processed dataset is empty!"
    assert "processed" in data[0], "Data items missing 'processed' key!"