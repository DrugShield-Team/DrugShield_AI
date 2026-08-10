# config/settings.py
import os

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
except ImportError:
    def load_dotenv():
        return False

load_dotenv()

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "drugshield_session")

# Local directories
RAW_DATA_DIR = os.path.join("data", "raw")
RAW_IMAGES_DIR = os.path.join(RAW_DATA_DIR, "images")

# Ensure required storage folders exist
os.makedirs(RAW_IMAGES_DIR, exist_ok=True)