import os
import pathlib
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB = os.getenv("MONGO_DB", "Scrapper_data")
COLLECTIONS = {"energy": "energy",
               "agriculture": "agriculture",
               "nature": "nature",
               "adaptation": "adaptation",
               "infrastructure": "infrastructure",
               "mining": "mining",
               "cfcm": "cfcm"}

POSTGRES_DSN = os.getenv("POSTGRES_DSN")

START_YEAR = 2015
CURRENT_YEAR = datetime.now().year
YEARS = [str(y) for y in range(START_YEAR, CURRENT_YEAR + 1)]


REPORTS_DIR = pathlib.Path(os.getenv("REPORTS_DIR", "reports"))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "180"))