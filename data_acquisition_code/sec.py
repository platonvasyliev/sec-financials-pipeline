"""Small client for the SEC EDGAR JSON API (data.sec.gov)."""

import os
import time

import requests
from dotenv import load_dotenv

BASE_URL = "https://data.sec.gov"

# SEC fair-access limit is 10 requests per second; stay comfortably under it.
MIN_SECONDS_BETWEEN_CALLS = 0.15


class SecClient:
    def __init__(self, user_agent=None):
        load_dotenv()
        user_agent = user_agent or os.getenv("SEC_USER_AGENT")
        if not user_agent:
            raise RuntimeError("SEC_USER_AGENT is not set. Copy .env.example to .env and fill it in.")

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self._last_call = 0.0

    def get_json(self, url, retries=3):
        """GET a JSON document. Returns None on 404 (e.g. no data for that tag/period)."""
        for attempt in range(retries + 1):
            pause = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - self._last_call)
            if pause > 0:
                time.sleep(pause)
            self._last_call = time.monotonic()

            resp = self.session.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            return resp.json()

    def frame(self, tag, period, unit="USD"):
        """One value per company for a tag and calendar period, e.g. ('Revenues', 'CY2024')."""
        return self.get_json(f"{BASE_URL}/api/xbrl/frames/us-gaap/{tag}/{unit}/{period}.json")

    def submissions(self, cik):
        return self.get_json(f"{BASE_URL}/submissions/CIK{int(cik):010d}.json")

    def company_facts(self, cik):
        return self.get_json(f"{BASE_URL}/api/xbrl/companyfacts/CIK{int(cik):010d}.json")
