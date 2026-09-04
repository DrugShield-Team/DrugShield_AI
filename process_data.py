import json
from pathlib import Path


def process_raw_data():
    raw_file = Path("data/raw/ingested_raw_data.json")
    processed_dir = Path("data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)

    if not raw_file.exists():
        print(f"Error: {raw_file} not found. Run main.py first!")
        return

    print(f"Loading raw data from {raw_file}...")
    with open(raw_file, "r") as f:
        data = json.load(f)

    # Transform / normalize data
    for item in data:
        item["processed"] = True
        item["high_risk"] = item.get("risk_score", 0) > 0.50

    output_file = processed_dir / "processed_data.json"
    with open(output_file, "w") as f:
        json.dump(data, f, indent=4)

    print(f"Data successfully processed and saved to: {output_file}")


if __name__ == "__main__":
    process_raw_data()