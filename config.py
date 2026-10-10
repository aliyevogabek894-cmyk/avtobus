import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Load .env if present
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "smart-school-bus-secure-jwt-key-2026-very-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "school_bus.db"))
DATABASE_URL = os.getenv("DATABASE_URL", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEFAULT_TELEGRAM_CHAT_ID = os.getenv("DEFAULT_TELEGRAM_CHAT_ID", "")

# Geofence default in meters
DEFAULT_GEOFENCE_RADIUS = int(os.getenv("DEFAULT_GEOFENCE_RADIUS", "100"))

# GPS staleness threshold in seconds (if no update for 120s, bus is considered offline)
GPS_STALE_THRESHOLD_SECONDS = int(os.getenv("GPS_STALE_THRESHOLD_SECONDS", "120"))
