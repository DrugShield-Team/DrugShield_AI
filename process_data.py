import json
from src.ai_pipeline.nlp_classifier import HinglishSlangDetector

def process_ingested_messages():
    # Initialize the slang detector
    detector = HinglishSlangDetector()
    
    # Example: Loading ingested raw data
    raw_data_path = "data/raw/ingested_raw_data.json"
    processed_output_path = "data/processed/processed_data.json"

    try:
        with open(raw_data_path, "r", encoding="utf-8") as f:
            messages = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        messages = []

    processed_results = []

    for item in messages:
        # Extract text payload from message
        text = item.get("text") or item.get("message") or ""
        
        # 🔍 Run Hinglish Slang Analysis
        analysis = detector.analyze(text)
        
        # Attach analysis results to the payload
        item["nlp_analysis"] = {
            "normalized_text": analysis["normalized_text"],
            "detected_slangs": analysis["detected_slangs"],
            "risk_score": analysis["risk_score"],
            "is_suspicious": analysis["is_suspicious"]
        }
        
        processed_results.append(item)

    # Save enriched data
    with open(processed_output_path, "w", encoding="utf-8") as f:
        json.dump(processed_results, f, indent=4)

    print(f"✅ Processed {len(processed_results)} messages through Hinglish NLP Classifier.")

if __name__ == "__main__":
    process_ingested_messages()