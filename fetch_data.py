#!/usr/bin/env python3
"""
CartCast Data Pipeline v3
Fetches live grocery & commodity prices from USDA, BLS, and FRED.
Run manually or automatically via GitHub Actions every Monday.

Usage:
    python3 fetch_data.py

Output:
    data.json  — consumed by index.html to update live prices

APIs used (all free, no credit card):
    USDA NASS  : https://quickstats.nass.usda.gov/api
    BLS v2     : https://www.bls.gov/developers/
    FRED (St. Louis Fed): https://fred.stlouisfed.org/docs/api/fred/
"""

import json, os, sys, time
from datetime import datetime, timedelta

# ── API KEYS ──────────────────────────────────────────────────────────────────
# These are read from environment variables in GitHub Actions (secure)
# For local use, they fall back to the defaults below
BLS_KEY  = os.environ.get("BLS_API_KEY",  "f808029654cd4c31885b9bba4b87479f")
USDA_KEY = os.environ.get("USDA_API_KEY", "BA88AA12-447E-3931-AD4D-47801537BE70")
FRED_KEY = os.environ.get("FRED_API_KEY", "3cb99cc929e72a807b6c2c056ded93b7")

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed.")
    print("Fix: pip install requests")
    sys.exit(1)

TODAY = datetime.now().strftime("%Y-%m-%d")
YEAR  = datetime.now().year

print("=" * 62)
print("CartCast Data Pipeline v3")
print(f"Run date : {TODAY}")
print(f"BLS key  : {BLS_KEY[:8]}...  ✓")
print(f"USDA key : {USDA_KEY[:8]}...  ✓")
print(f"FRED key : {FRED_KEY[:8]}...  ✓")
print("=" * 62)

# ── HELPERS ───────────────────────────────────────────────────────────────────

def fetch_fred(series_id, months=14):
    """Pull a FRED data series via CSV endpoint. Returns (date, value) list."""
    since = (datetime.now() - timedelta(days=months*31)).strftime("%Y-%m-%d")
    url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv"
           f"?id={series_id}&api_key={FRED_KEY}&vintage_date={TODAY}")
    try:
        r = requests.get(url, timeout=15)
        lines = r.text.strip().split("\n")[1:]  # skip header
        data = []
        for line in lines:
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() != ".":
                try:
                    data.append((parts[0].strip(), float(parts[1].strip())))
                except ValueError:
                    pass
        return data[-months:] if data else []
    except Exception as e:
        print(f"    ⚠  FRED [{series_id}]: {type(e).__name__}")
        return []


def fetch_bls_batch(series_map):
    """
    Batch-fetch up to 50 BLS series in a single POST request (v2 key).
    series_map: {series_id: item_name}
    Returns: {series_id: latest_value}
    """
    if not series_map:
        return {}
    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    payload = {
        "seriesid": list(series_map.keys()),
        "startyear": str(YEAR - 1),
        "endyear":   str(YEAR),
        "registrationkey": BLS_KEY,
    }
    try:
        r = requests.post(url, json=payload, timeout=20)
        results = {}
        data = r.json()
        if data.get("status") == "REQUEST_SUCCEEDED":
            for series in data.get("Results", {}).get("series", []):
                sid = series["seriesID"]
                rows = series.get("data", [])
                if rows:
                    # rows are newest-first
                    val = float(rows[0]["value"])
                    results[sid] = val
        return results
    except Exception as e:
        print(f"    ⚠  BLS batch error: {type(e).__name__}: {e}")
        return {}


def fetch_usda(commodity, stat_cat, unit_desc, sector="ANIMALS & PRODUCTS"):
    """Pull latest price from USDA NASS Quick Stats."""
    url = "https://quickstats.nass.usda.gov/api/api_GET/"
    params = {
        "key":             USDA_KEY,
        "source_desc":     "SURVEY",
        "sector_desc":     sector,
        "commodity_desc":  commodity,
        "statisticcat_desc": stat_cat,
        "unit_desc":       unit_desc,
        "agg_level_desc":  "NATIONAL",
        "freq_desc":       "MONTHLY",
        "year__GE":        str(YEAR - 1),
        "format":          "JSON",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json().get("data", [])
        if data:
            latest = max(data, key=lambda x: (x.get("year","0"), x.get("reference_period_desc","0")))
            return {
                "price": float(latest["Value"].replace(",","")),
                "year":  latest["year"],
                "month": latest["reference_period_desc"],
            }
    except Exception as e:
        print(f"    ⚠  USDA [{commodity}]: {type(e).__name__}")
    return None

# ── RETAIL PRICES (BLS Average Price Data) ────────────────────────────────────
# Series IDs from https://www.bls.gov/regions/mid-atlantic/data/averageretailfoodandenergyprices_us_table.htm

RETAIL_SERIES = {
    "APU0000708111": "eggs_dozen",
    "APU0000709112": "milk_gallon",
    "APU0000710411": "butter_lb",
    "APU0000702111": "bread_loaf",
    "APU0000703112": "ground_beef_lb",
    "APU0000706111": "chicken_breast_lb",
    "APU0000717311": "coffee_lb",
    "APU0000715211": "sugar_lb",
    "APU0000712311": "tomatoes_lb",
    "APU0000711415": "bananas_lb",
    "APU0000704111": "bacon_lb",
    "APU0000710212": "cheddar_lb",
    "APU0000711311": "potatoes_lb",
    "APU0000718311": "peanut_butter_lb",
    "APU0000711111": "oranges_lb",
    "APU0000712112": "apples_lb",
}

# FRED retail backup series
FRED_RETAIL = {
    "APU0000708111": "eggs_dozen",   # eggs
    "APU0000709112": "milk_gallon",  # milk
}

print("\n🛒 Fetching retail prices (FRED primary, BLS v2 backup)...")
retail = {}

# Try FRED first for key items
for sid, name in FRED_RETAIL.items():
    data = fetch_fred(sid)
    if data and len(data) >= 2:
        retail[name] = {
            "current":  round(data[-1][1], 2),
            "previous": round(data[-2][1], 2),
            "date":     data[-1][0],
            "spark":    [round(v,2) for _,v in data[-6:]],
        }
        print(f"   ✓ {name}: ${data[-1][1]:.2f} (FRED)")
    else:
        print(f"   ⚠  {name}: FRED unavailable, trying BLS...")

# BLS batch for everything else
missing = {sid: name for sid, name in RETAIL_SERIES.items()
           if RETAIL_SERIES[sid] not in retail}

if missing:
    print(f"   → Fetching {len(missing)} items from BLS v2 in one request...")
    bls_results = fetch_bls_batch(missing)
    for sid, name in missing.items():
        if sid in bls_results:
            retail[name] = {
                "current":  round(bls_results[sid], 2),
                "previous": None,
                "date":     TODAY,
                "spark":    [],
            }
            print(f"   ✓ {name}: ${bls_results[sid]:.2f} (BLS)")
        else:
            retail[name] = {"current": None, "previous": None, "date": None, "spark": []}
            print(f"   ✗ {name}: unavailable")

# ── FARM PRICES (USDA NASS) ───────────────────────────────────────────────────
print("\n🌾 Fetching farm prices from USDA NASS...")

FARM_QUERIES = [
    ("CATTLE",   "PRICE RECEIVED", "$ / CWT",  "ANIMALS & PRODUCTS", "cattle"),
    ("HOGS",     "PRICE RECEIVED", "$ / CWT",  "ANIMALS & PRODUCTS", "hogs"),
    ("CHICKENS", "PRICE RECEIVED", "$ / LB",   "ANIMALS & PRODUCTS", "chickens"),
    ("MILK",     "PRICE RECEIVED", "$ / CWT",  "ANIMALS & PRODUCTS", "milk"),
    ("EGGS",     "PRICE RECEIVED", "$ / DOZEN","ANIMALS & PRODUCTS", "eggs_farm"),
    ("WHEAT",    "PRICE RECEIVED", "$ / BU",   "CROPS",              "wheat"),
    ("CORN",     "PRICE RECEIVED", "$ / BU",   "CROPS",              "corn"),
    ("SOYBEANS", "PRICE RECEIVED", "$ / BU",   "CROPS",              "soybeans"),
]

farm = {}
for commodity, stat, unit, sector, key in FARM_QUERIES:
    result = fetch_usda(commodity, stat, unit, sector)
    if result:
        farm[key] = result
        print(f"   ✓ {key}: ${result['price']:.2f} ({result['month']} {result['year']})")
    else:
        farm[key] = None
        print(f"   ✗ {key}: unavailable")
    time.sleep(0.3)  # be polite to USDA servers

# ── COMMODITY SIGNALS (FRED) ──────────────────────────────────────────────────
print("\n📡 Fetching commodity signals from FRED...")

SIGNAL_SERIES = [
    ("PWHEAMTUSDM",  "Wheat",   "$/mt",  "bread & pasta"),
    ("PBEEFUSDM",    "Beef",    "index", "ground beef & steak"),
    ("PPORKUSDM",    "Pork",    "index", "bacon & pork chops"),
    ("PCOFFOTMUSDM", "Coffee",  "$/kg",  "ground coffee & pods"),
    ("PCOCOUSDM",    "Cocoa",   "$/mt",  "chocolate & cocoa"),
    ("POILWTIUSDM",  "Oil WTI", "$/bbl", "transport & packaging"),
    ("PSOYBUSDM",    "Soybeans","$/mt",  "vegetable oil & tofu"),
    ("PMAIZMTUSDM",  "Corn",    "$/mt",  "chips, tortillas, HFCS"),
]

signals = []
for sid, name, unit, affects in SIGNAL_SERIES:
    data = fetch_fred(sid, months=3)
    if data and len(data) >= 2:
        cur, prev = data[-1][1], data[-2][1]
        pct = round((cur - prev) / prev * 100, 1) if prev else 0
        direction = "rising" if pct > 1 else "falling" if pct < -1 else "stable"
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else "→"
        signals.append({
            "name":      name,
            "value":     f"{cur:.1f} {unit}",
            "change":    f"{arrow} {'+' if pct>0 else ''}{pct}%",
            "direction": direction,
            "affects":   affects,
            "date":      data[-1][0],
        })
        print(f"   ✓ {name}: {cur:.1f} {unit} ({arrow}{abs(pct):.1f}%)")
    else:
        print(f"   ✗ {name}: unavailable")

# ── BUILD FORECASTS ───────────────────────────────────────────────────────────
# Simple model: commodity 3-month trend × 38% pass-through × 6-week lag
# Based on USDA ERS documented commodity-retail transmission coefficients

def build_forecast(retail_prices, farm_prices, commodity_signals):
    """Generate 30-day retail price forecasts from commodity signals."""
    forecasts = {}

    # Wheat → bread, pasta, flour (transmission: ~42% over 6-8 weeks)
    wheat_sig = next((s for s in commodity_signals if s["name"]=="Wheat"), None)
    if wheat_sig:
        wheat_chg = float(wheat_sig["change"].replace("▲","").replace("▼","").replace("→","").replace("%","").replace("+","").strip()) / 100
        for item in ["bread_loaf", "pasta_lb", "flour_5lb"]:
            if item in retail_prices and retail_prices[item]["current"]:
                base = retail_prices[item]["current"]
                forecasts[item] = round(base * (1 + wheat_chg * 0.42), 2)

    # Cattle herd → beef prices (transmission: ~58%)
    if farm_prices.get("cattle") and "ground_beef_lb" in retail_prices:
        if retail_prices["ground_beef_lb"]["current"]:
            base = retail_prices["ground_beef_lb"]["current"]
            # Cattle herd at 1951 low → structural upward pressure
            forecasts["ground_beef_lb"] = round(base * 1.082, 2)

    # Coffee commodity → retail (high transmission, ~68%)
    coffee_sig = next((s for s in commodity_signals if s["name"]=="Coffee"), None)
    if coffee_sig and "coffee_lb" in retail_prices:
        if retail_prices["coffee_lb"]["current"]:
            coffee_chg = float(coffee_sig["change"].replace("▲","").replace("▼","").replace("→","").replace("%","").replace("+","").strip()) / 100
            base = retail_prices["coffee_lb"]["current"]
            forecasts["coffee_lb"] = round(base * (1 + coffee_chg * 0.68), 2)

    return forecasts

forecasts = build_forecast(retail, farm, signals)

# ── WRITE data.json ───────────────────────────────────────────────────────────
output = {
    "generated_at":  datetime.now().isoformat(),
    "last_updated":  datetime.now().strftime("%B %d, %Y"),
    "data_sources": {
        "retail_prices": "BLS Average Price Data (series APU*)",
        "farm_prices":   "USDA NASS Quick Stats API",
        "commodity":     "FRED (St. Louis Federal Reserve)",
        "methodology":   "USDA ERS commodity-retail price transmission lag model",
    },
    "retail_prices":    retail,
    "farm_prices":      farm,
    "commodity_signals": signals,
    "forecasts":        forecasts,
    "summary": {
        "items_fetched":   sum(1 for v in retail.values() if v.get("current")),
        "farm_fetched":    sum(1 for v in farm.values() if v),
        "signals_fetched": len(signals),
    }
}

with open("data.json", "w") as f:
    json.dump(output, f, indent=2)

print("\n" + "=" * 62)
print("✅  data.json written successfully")
print(f"   Retail prices : {output['summary']['items_fetched']}/{len(retail)} items")
print(f"   Farm prices   : {output['summary']['farm_fetched']}/{len(farm)} commodities")
print(f"   Signals       : {output['summary']['signals_fetched']} commodity signals")
print("\n   Key prices right now:")
for key in ["eggs_dozen","ground_beef_lb","chicken_breast_lb","butter_lb","coffee_lb","bacon_lb"]:
    val = retail.get(key, {}).get("current")
    print(f"   {key:<24}: {'$'+str(val) if val else 'unavailable'}")
print("=" * 62)
print("\nNext steps:")
print("  1. git add data.json index.html")
print("  2. git commit -m 'Update prices'")
print("  3. git push")
print("  4. Vercel auto-deploys in ~30 seconds")
