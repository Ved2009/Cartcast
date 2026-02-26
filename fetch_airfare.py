#!/usr/bin/env python3
"""
CartCast — fetch_airfare.py
Session 5: Amadeus Flight Offers Search API integration
Caches fares to data/airfare_cache.json every 30 minutes.
Falls back gracefully if Amadeus is unavailable.

Setup:
  1. Register free at https://developers.amadeus.com (2,000 free calls/month)
  2. Set environment variables:
       AMADEUS_CLIENT_ID=your_api_key
       AMADEUS_CLIENT_SECRET=your_secret
  3. Run: python fetch_airfare.py
  4. Schedule: crontab -e → */30 * * * * /path/to/python /path/to/fetch_airfare.py

Output: data/airfare_cache.json (read by airfare_v2.html / cartcast_merged.html)
"""

import os
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────
AMADEUS_CLIENT_ID     = os.getenv("AMADEUS_CLIENT_ID", "")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET", "")
BTS_API_KEY           = os.getenv("BTS_API_KEY", "f808029654cd4c31885b9bba4b87479f")

CACHE_FILE   = Path("data/airfare_cache.json")
CACHE_MAX_AGE_HOURS = 2  # Stale if older than this

# Top 50 US domestic + 10 international routes to pre-cache
TOP_ROUTES = [
    # Domestic trunk routes
    ("LAX", "JFK"), ("LAX", "SFO"), ("LAX", "ORD"), ("LAX", "MIA"),
    ("JFK", "ORD"), ("JFK", "MIA"), ("JFK", "BOS"), ("JFK", "LAX"),
    ("SFO", "JFK"), ("SFO", "ORD"), ("SFO", "SEA"), ("SFO", "LAX"),
    ("ORD", "ATL"), ("ORD", "DFW"), ("ORD", "MIA"), ("ORD", "BOS"),
    ("ATL", "DFW"), ("ATL", "MIA"), ("ATL", "BOS"), ("ATL", "LAX"),
    ("DFW", "LAX"), ("DFW", "MIA"), ("DFW", "JFK"), ("DFW", "ORD"),
    ("MIA", "BOS"), ("MIA", "LAX"), ("MIA", "JFK"), ("MIA", "ORD"),
    ("DEN", "LAX"), ("DEN", "JFK"), ("DEN", "ORD"), ("DEN", "SFO"),
    ("SEA", "LAX"), ("SEA", "SFO"), ("SEA", "JFK"), ("SEA", "ORD"),
    ("LAS", "LAX"), ("LAS", "JFK"), ("LAS", "ORD"), ("LAS", "SFO"),
    ("PHX", "LAX"), ("PHX", "JFK"), ("PHX", "ORD"), ("PHX", "DFW"),
    ("BOS", "LAX"), ("BOS", "ORD"), ("BOS", "MIA"), ("BOS", "DFW"),
    ("MSP", "ORD"), ("MSP", "LAX"),
    # International (US gateway → hub)
    ("JFK", "LHR"), ("LAX", "NRT"), ("JFK", "CDG"), ("ORD", "FRA"),
    ("MIA", "MEX"), ("LAX", "SYD"), ("JFK", "DXB"), ("SFO", "ICN"),
    ("ORD", "AMS"), ("LAX", "SIN"),
]

# Look ahead 14 and 30 days for fares
LOOK_AHEAD_DAYS = [14, 30]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fetch_airfare")


# ── Amadeus Auth ────────────────────────────────────────────────────
_amadeus_token = None
_token_expires  = 0

def get_amadeus_token():
    global _amadeus_token, _token_expires
    if _amadeus_token and time.time() < _token_expires - 60:
        return _amadeus_token
    if not AMADEUS_CLIENT_ID or not AMADEUS_CLIENT_SECRET:
        raise ValueError("AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET env vars not set.")
    r = requests.post(
        "https://test.api.amadeus.com/v1/security/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": AMADEUS_CLIENT_ID,
            "client_secret": AMADEUS_CLIENT_SECRET,
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    _amadeus_token = data["access_token"]
    _token_expires = time.time() + data.get("expires_in", 1799)
    log.info("Amadeus token obtained (expires in %ds)", data.get("expires_in", 1799))
    return _amadeus_token


# ── Amadeus Flight Offers ───────────────────────────────────────────
def fetch_offers(orig, dest, dep_date, pax=1, cabin="ECONOMY", non_stop=False):
    """
    Calls Amadeus Flight Offers Search.
    Returns list of parsed offer dicts or [] on error.
    """
    token = get_amadeus_token()
    params = {
        "originLocationCode":      orig,
        "destinationLocationCode": dest,
        "departureDate":           dep_date,
        "adults":                  pax,
        "travelClass":             cabin,
        "max":                     15,  # up to 15 offers
        "currencyCode":            "USD",
    }
    if non_stop:
        params["nonStop"] = "true"
    try:
        r = requests.get(
            "https://test.api.amadeus.com/v2/shopping/flight-offers",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=15,
        )
        r.raise_for_status()
    except requests.HTTPError as e:
        log.warning("Amadeus HTTP error %s for %s→%s on %s", e.response.status_code, orig, dest, dep_date)
        return []
    except requests.RequestException as e:
        log.warning("Amadeus request failed: %s", e)
        return []

    parsed = []
    for offer in r.json().get("data", []):
        try:
            price   = float(offer["price"]["grandTotal"])
            itin    = offer["itineraries"][0]
            seg0    = itin["segments"][0]
            dep_dt  = seg0["departure"]["at"]
            dep_time= dep_dt[11:16]  # HH:MM
            airline = seg0["carrierCode"]
            stops   = len(itin["segments"]) - 1
            dur     = itin["duration"]  # e.g. PT5H20M
            parsed.append({
                "airline":   airline,
                "price":     round(price, 2),
                "depTime":   dep_time,
                "stops":     stops,
                "duration":  dur,
                "date":      dep_date,
                "source":    "amadeus",
            })
        except (KeyError, ValueError, IndexError):
            continue
    return parsed


# ── BTS DB1B Historical Trend ───────────────────────────────────────
def fetch_bts_trend(orig, dest):
    """
    Pulls 30-day historical fare baseline from BTS DB1B.
    Returns dict with avg_fare, trend_pct or None on failure.
    Owner API key: f808029654cd4c31885b9bba4b87479f
    """
    try:
        url = (
            f"https://api.bts.gov/v1/fares/trend"
            f"?origin={orig}&destination={dest}"
            f"&key={BTS_API_KEY}&format=json"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        # BTS returns quarterly data; compute simple trend
        records = data.get("data", [])
        if len(records) >= 2:
            latest  = float(records[-1].get("fare", 0))
            prior   = float(records[-2].get("fare", latest))
            trend   = round(((latest - prior) / prior) * 100, 1) if prior else 0
            return {"avg_fare": latest, "trend_pct": trend}
    except Exception as e:
        log.debug("BTS trend fetch failed for %s→%s: %s", orig, dest, e)
    return None


# ── Cache ────────────────────────────────────────────────────────────
def load_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}

def save_cache(data):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)
    log.info("Cache saved: %d routes · %s", len(data.get("routes", {})), CACHE_FILE)

def cache_is_stale(cache):
    ts = cache.get("updated_at")
    if not ts:
        return True
    updated = datetime.fromisoformat(ts)
    return datetime.utcnow() - updated > timedelta(hours=CACHE_MAX_AGE_HOURS)


# ── Main fetch loop ──────────────────────────────────────────────────
def run():
    log.info("CartCast fetch_airfare.py — Session 5 build")
    cache = load_cache()

    if not cache_is_stale(cache):
        log.info("Cache is fresh (updated %s) — skipping fetch.", cache.get("updated_at"))
        return

    if not AMADEUS_CLIENT_ID:
        log.warning(
            "AMADEUS_CLIENT_ID not set. Register free at https://developers.amadeus.com\n"
            "Set env vars: AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET\n"
            "Falling back to stale cache (or simulation in HTML)."
        )
        return

    routes_data = {}
    today = datetime.utcnow().date()

    for orig, dest in TOP_ROUTES:
        route_key = f"{orig}-{dest}"
        route_entry = {"orig": orig, "dest": dest, "fares": {}, "trend": None}

        # Fetch BTS historical trend
        trend = fetch_bts_trend(orig, dest)
        if trend:
            route_entry["trend"] = trend
            log.debug("BTS trend %s→%s: avg $%.0f, %+.1f%%", orig, dest, trend["avg_fare"], trend["trend_pct"])

        # Fetch Amadeus fares for each look-ahead date
        for days in LOOK_AHEAD_DAYS:
            dep_date = (today + timedelta(days=days)).strftime("%Y-%m-%d")
            offers = fetch_offers(orig, dest, dep_date)
            if offers:
                route_entry["fares"][dep_date] = offers
                log.info("  %s→%s on %s: %d offers (cheapest $%.0f)",
                    orig, dest, dep_date, len(offers), min(o["price"] for o in offers))
            time.sleep(0.3)  # Respect rate limits (2k calls/month free tier)

        if route_entry["fares"]:
            routes_data[route_key] = route_entry
        time.sleep(0.5)

    new_cache = {
        "updated_at": datetime.utcnow().isoformat(),
        "routes":     routes_data,
        "route_count": len(routes_data),
        "source":     "amadeus_flight_offers_v2",
        "bts_key":    BTS_API_KEY[:8] + "...",  # Partial key for reference
    }
    save_cache(new_cache)
    log.info("Done. %d routes cached.", len(routes_data))


if __name__ == "__main__":
    run()
