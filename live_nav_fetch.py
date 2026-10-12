"""
live_nav_fetch.py
Fetch live NAV history from mfapi.in and save each scheme as a raw CSV.

Usage:
    python live_nav_fetch.py
"""
import time
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://api.mfapi.in/mf/{code}"
RAW_DIR = Path(__file__).parent / "data" / "raw"

# Task 4 scheme + Task 5 key schemes (names are the labels given in the task;
# the API's own scheme_name is printed so you can confirm each code).
SCHEMES = {
    125497: "HDFC Top 100 (Direct)",
    119551: "SBI Bluechip",
    120503: "ICICI Bluechip",
    118632: "Nippon Large Cap",
    119092: "Axis Bluechip",
    120841: "Kotak Bluechip",
}


def fetch_scheme(code: int, retries: int = 3, timeout: int = 30) -> dict:
    """GET one scheme from mfapi.in with simple retry/backoff."""
    url = BASE_URL.format(code=code)
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            if not payload.get("data"):
                raise ValueError(f"No NAV data returned for {code}")
            return payload
        except (requests.RequestException, ValueError) as err:
            last_err = err
            print(f"  attempt {attempt}/{retries} failed for {code}: {err}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"Could not fetch scheme {code}") from last_err


def parse_nav(payload: dict) -> pd.DataFrame:
    """Turn the mfapi.in JSON into a tidy DataFrame."""
    meta = payload.get("meta", {})
    df = pd.DataFrame(payload["data"])
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df = df.dropna(subset=["date", "nav"]).sort_values("date").reset_index(drop=True)
    df.insert(0, "scheme_code", meta.get("scheme_code"))
    df.insert(1, "scheme_name", meta.get("scheme_name"))
    df.insert(2, "fund_house", meta.get("fund_house"))
    return df


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for code, label in SCHEMES.items():
        print(f"\nFetching {code} ({label}) ...")
        try:
            payload = fetch_scheme(code)
        except RuntimeError as err:
            print(f"  SKIPPED: {err}")
            continue

        df = parse_nav(payload)
        out = RAW_DIR / f"nav_live_{code}.csv"
        df.to_csv(out, index=False)

        api_name = payload.get("meta", {}).get("scheme_name")
        print(f"  API scheme name : {api_name}")
        print(f"  Rows            : {len(df)}")
        print(f"  Date range      : {df['date'].min().date()} -> {df['date'].max().date()}")
        print(f"  Latest NAV      : {df['nav'].iloc[-1]}")
        print(f"  Saved to        : {out}")
        time.sleep(1)  # be polite to the API


if __name__ == "__main__":
    main()
