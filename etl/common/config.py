# Loads config/secrets from .env into these constants - imported by both
# app/ and etl/ code that needs the DB URL or an API key.

import os

from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ["DB_URL"]
TRAVELPAYOUTS_TOKEN = os.environ.get("TRAVELPAYOUTS_TOKEN", "")
TRAVELPAYOUTS_MARKER = os.environ.get("TRAVELPAYOUTS_MARKER", "")
# "off" makes destination views use collected data only, with no call to
# Travelpayouts - for the end-to-end tests (fixed answers) and offline work.
LIVE_FLIGHT_SEARCH = os.environ.get("LIVE_FLIGHT_SEARCH", "on") != "off"
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
