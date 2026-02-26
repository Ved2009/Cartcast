#!/usr/bin/env python3
"""
CartCast Data Pipeline — Session 1 Upgrade
Sources: BLS, USDA NASS, FRED, EIA (gas + electricity), HUD (rent), Census, OpenFDA
Generates: data.json used by the CartCast website
"""

import json
import os
import requests
import pandas as pd
from datetime import datetime, date

# ─────────────────────────────────────────
# API KEYS (also read from environment for GitHub Actions)
# ─────────────────────────────────────────
BLS_KEY    = os.environ.get("BLS_API_KEY",    "f808029654cd4c31885b9bba4b87479f")
USDA_KEY   = os.environ.get("USDA_API_KEY",   "BA88AA12-447E-3931-AD4D-47801537BE70")
FRED_KEY   = os.environ.get("FRED_API_KEY",   "3cb99cc929e72a807b6c2c056ded93b7")
EIA_KEY    = os.environ.get("EIA_API_KEY",    "SOvlx2vY4tSWTFCGrevM2ktUKkqcB3JaQwrR3jCa")
FDA_KEY    = os.environ.get("OPENFDA_API_KEY","JIO2cvubrA4lWWvtvBImqsaQh9HAjiXifAIpxnZC")
HUD_TOKEN  = os.environ.get("HUD_API_KEY",   "")   # JWT token from HUD email
CENSUS_KEY = os.environ.get("CENSUS_API_KEY","86635d2b4c48922abb33324d995ce93d54ae3d0b")
RENTCAST_KEY = os.environ.get("RENTCAST_API_KEY","077b6c9be623493aa98c69ec7fe15124")

run_date = str(date.today())
print("=" * 60)
print("CartCast Data Pipeline — Session 1")
print(f"Run date: {run_date}")
print("=" * 60)

output = {
    "generated": run_date,
    "groceries": {},
    "gas": {},
    "electricity": {},
    "medicine": {},
    "housing": {},
    "commodity_signals": {},
    "errors": []
}

# ─────────────────────────────────────────
# 1. GROCERY PRICES — FRED (BLS-mirrored data)
# ─────────────────────────────────────────
FRED_GROCERY_SERIES = {
    "eggs_dozen":        "APU0000708111",   # Eggs, grade A, large
    "milk_gallon":       "APU0000709112",   # Milk, whole, per gallon
    "butter_lb":         "APU0000FS11101",  # Butter, salted
    "ground_beef_lb":    "APU0000703112",   # Ground beef, 100% beef
    "chicken_breast_lb": "APU0000706111",   # Chicken, boneless
    "bread_loaf":        "APU0000702111",   # Bread, white, pan
    "coffee_lb":         "APU0000717311",   # Coffee, 100%, ground roast
    "orange_juice":      "APU0000FL2101",   # Orange juice, frozen
    "sugar_lb":          "APU0000715211",   # Sugar, white, 33-80 oz pk
    "potatoes_lb":       "APU0000FD3101",   # Potatoes, white
    "tomatoes_lb":       "APU0000712311",   # Tomatoes, field grown
    "bananas_lb":        "APU0000711211",   # Bananas
    "bacon_lb":          "APU0000704111",   # Bacon, sliced
    "ice_cream":         "APU0000710212",   # Ice cream, prepackaged
}

print("\n🛒 Fetching grocery prices from FRED (BLS data)...")
for item, series_id in FRED_GROCERY_SERIES.items():
    try:
        url = f"https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": FRED_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 3,
            "observation_start": "2024-01-01"
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        valid = [o for o in obs if o["value"] != "."]
        if valid:
            latest = float(valid[0]["value"])
            prev = float(valid[1]["value"]) if len(valid) > 1 else latest
            pct_change = round(((latest - prev) / prev * 100) if prev else 0, 1)
            output["groceries"][item] = {
                "price": round(latest, 2),
                "prev": round(prev, 2),
                "pct_change_monthly": pct_change,
                "date": valid[0]["date"],
                "source": "FRED/BLS"
            }
            print(f"  ✓ {item}: ${latest:.2f} ({'+' if pct_change>0 else ''}{pct_change}%)")
        else:
            print(f"  ✗ {item}: no data available")
            output["errors"].append(f"FRED: no data for {item}")
    except Exception as e:
        print(f"  ✗ {item}: {e}")
        output["errors"].append(f"FRED {item}: {str(e)}")

# ─────────────────────────────────────────
# 2. COMMODITY SIGNALS — FRED Futures Prices
# ─────────────────────────────────────────
FRED_COMMODITY_SERIES = {
    "wheat_futures_usd_bu":     "PWHEAMTUSDM",
    "corn_futures_usd_bu":      "PMAIZMTUSDM",
    "soybean_futures_usd_mt":   "PSOYBUSDM",
    "coffee_futures_usd_lb":    "PCOFFOTMUSDM",
    "cocoa_futures_usd_mt":     "PCOCOUSDM",
    "crude_oil_wti_bbl":        "DCOILWTICO",
    "natural_gas_mmbtu":        "DHHNGSP",
    "beef_usda_cwt":            "WPSFD49502",
}

print("\n📡 Fetching commodity signals from FRED...")
for name, series_id in FRED_COMMODITY_SERIES.items():
    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": FRED_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 3
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
        if obs:
            val = float(obs[0]["value"])
            prev = float(obs[1]["value"]) if len(obs) > 1 else val
            pct = round(((val - prev) / prev * 100) if prev else 0, 1)
            output["commodity_signals"][name] = {"value": val, "pct_change": pct, "date": obs[0]["date"]}
            print(f"  ✓ {name}: {val:.2f} ({'+' if pct>0 else ''}{pct}%)")
    except Exception as e:
        print(f"  ✗ {name}: {e}")
        output["errors"].append(f"FRED signal {name}: {str(e)}")

# ─────────────────────────────────────────
# 3. GAS PRICES BY STATE — EIA API
# ─────────────────────────────────────────
print("\n⛽ Fetching gas prices from EIA...")
EIA_GAS_SERIES = {
    # Weekly retail gasoline prices by region/state
    # EIA Series IDs for weekly motor gasoline retail prices
    "national_regular":  "EMM_EPMR_PTE_NUS_DPG",
    "east_coast":        "EMM_EPMR_PTE_R1X_DPG",
    "midwest":           "EMM_EPMR_PTE_R20_DPG",
    "gulf_coast":        "EMM_EPMR_PTE_R30_DPG",
    "rocky_mountain":    "EMM_EPMR_PTE_R40_DPG",
    "west_coast":        "EMM_EPMR_PTE_R50_DPG",
    "california":        "EMM_EPMR_PTE_SCA_DPG",
    "new_york":          "EMM_EPMR_PTE_SNY_DPG",
    "florida":           "EMM_EPMR_PTE_SFL_DPG",
    "texas":             "EMM_EPMR_PTE_STX_DPG",
    "ohio":              "EMM_EPMR_PTE_SOH_DPG",
    "minnesota":         "EMM_EPMR_PTE_SMN_DPG",
}

for region, series_id in EIA_GAS_SERIES.items():
    try:
        url = "https://api.eia.gov/v2/seriesid/" + series_id
        params = {"api_key": EIA_KEY, "data[0]": "value", "length": 2, "sort[0][column]": "period", "sort[0][direction]": "desc"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("response", {}).get("data", [])
        if data:
            val = float(data[0]["value"])
            output["gas"][region] = {"price_per_gallon": round(val / 100, 3), "period": data[0]["period"]}  # EIA stores in cents
            print(f"  ✓ {region}: ${val/100:.3f}/gal")
        else:
            # Try alternate endpoint format
            url2 = f"https://api.eia.gov/series/?api_key={EIA_KEY}&series_id={series_id}"
            r2 = requests.get(url2, timeout=10)
            r2.raise_for_status()
            series_data = r2.json().get("series", [])
            if series_data and series_data[0].get("data"):
                val = float(series_data[0]["data"][0][1])
                output["gas"][region] = {"price_per_gallon": round(val / 100, 3), "period": series_data[0]["data"][0][0]}
                print(f"  ✓ {region}: ${val/100:.3f}/gal (alt endpoint)")
    except Exception as e:
        print(f"  ✗ gas/{region}: {e}")
        output["errors"].append(f"EIA gas {region}: {str(e)}")

# ─────────────────────────────────────────
# 4. ELECTRICITY RATES BY STATE — EIA API
# ─────────────────────────────────────────
print("\n⚡ Fetching electricity rates from EIA...")
try:
    url = "https://api.eia.gov/v2/electricity/retail-sales/data/"
    params = {
        "api_key": EIA_KEY,
        "data[0]": "price",
        "facets[sectorName][]": "residential",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 60,
        "frequency": "monthly"
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    records = r.json().get("response", {}).get("data", [])
    if records:
        for rec in records[:20]:
            state = rec.get("stateid", "")
            if state and state not in output["electricity"]:
                output["electricity"][state] = {
                    "cents_per_kwh": float(rec.get("price", 0)),
                    "period": rec.get("period", "")
                }
        print(f"  ✓ Retrieved electricity rates for {len(output['electricity'])} states")
    else:
        print("  ✗ No electricity data returned")
except Exception as e:
    print(f"  ✗ EIA electricity: {e}")
    output["errors"].append(f"EIA electricity: {str(e)}")

# ─────────────────────────────────────────
# 5. RENT / HOUSING — HUD Fair Market Rents
# ─────────────────────────────────────────
print("\n🏠 Fetching housing data from HUD...")
HUD_METROS = [
    ("METRO47900M47900", "Washington DC Metro"),
    ("METRO35620M35620", "New York Metro"),
    ("METRO31080M31080", "Los Angeles Metro"),
    ("METRO16980M16980", "Chicago Metro"),
    ("METRO19100M19100", "Dallas Metro"),
    ("METRO26420M26420", "Houston Metro"),
    ("METRO33460M33460", "Minneapolis Metro"),
    ("METRO38060M38060", "Phoenix Metro"),
    ("METRO37980M37980", "Philadelphia Metro"),
    ("METRO12060M12060", "Atlanta Metro"),
]
for entityid, name in HUD_METROS:
    try:
        url = f"https://www.huduser.gov/hudapi/public/fmr/listCounties/{entityid}"
        headers = {"Authorization": f"Bearer {HUD_TOKEN}"} if HUD_TOKEN else {}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                d = data[0]
                output["housing"][name] = {
                    "efficiency": d.get("Efficiency", 0),
                    "one_br": d.get("One-Bedroom", 0),
                    "two_br": d.get("Two-Bedroom", 0),
                    "three_br": d.get("Three-Bedroom", 0),
                    "source": "HUD FMR"
                }
                print(f"  ✓ {name}: 1BR ${d.get('One-Bedroom','N/A')}")
        else:
            print(f"  ✗ HUD {name}: {r.status_code} (token may need refresh)")
    except Exception as e:
        print(f"  ✗ HUD {name}: {e}")
        output["errors"].append(f"HUD {name}: {str(e)}")

# ─────────────────────────────────────────
# 6. FARM PRICES — USDA NASS
# ─────────────────────────────────────────
USDA_ITEMS = [
    ("CATTLE", "PRICE RECEIVED", "$ / CWT", "cattle_cwt"),
    ("HOGS",   "PRICE RECEIVED", "$ / CWT", "hogs_cwt"),
    ("CHICKENS, BROILERS", "PRICE RECEIVED", "$ / LB", "broilers_lb"),
    ("MILK",   "PRICE RECEIVED", "$ / CWT", "milk_cwt"),
    ("WHEAT",  "PRICE RECEIVED", "$ / BU",  "wheat_bu"),
    ("CORN",   "PRICE RECEIVED", "$ / BU",  "corn_bu"),
    ("SOYBEANS", "PRICE RECEIVED", "$ / BU", "soybeans_bu"),
    ("POTATOES", "PRICE RECEIVED", "$ / CWT", "potatoes_cwt"),
]

print("\n🌾 Fetching farm prices from USDA NASS...")
for commodity, statcat, unit, key in USDA_ITEMS:
    try:
        url = "https://quickstats.nass.usda.gov/api/api_GET/"
        params = {
            "key": USDA_KEY,
            "source_desc": "SURVEY",
            "sector_desc": "CROPS" if commodity in ["WHEAT","CORN","SOYBEANS","POTATOES"] else "ANIMALS & PRODUCTS",
            "commodity_desc": commodity,
            "statisticcat_desc": statcat,
            "unit_desc": unit,
            "agg_level_desc": "NATIONAL",
            "freq_desc": "MONTHLY",
            "year__GE": "2024",
            "format": "JSON"
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", [])
        if data:
            data_sorted = sorted(data, key=lambda x: (x.get("year",""), x.get("reference_period_desc","")), reverse=True)
            latest = data_sorted[0]
            output["groceries"][key] = {
                "price": float(latest.get("Value","0").replace(",","")),
                "unit": unit,
                "period": f"{latest.get('year','')} {latest.get('reference_period_desc','')}",
                "source": "USDA NASS"
            }
            print(f"  ✓ {commodity}: {latest.get('Value','N/A')} {unit}")
        else:
            print(f"  ✗ USDA no data: {commodity}")
    except Exception as e:
        print(f"  ✗ USDA {commodity}: {e}")
        output["errors"].append(f"USDA {commodity}: {str(e)}")

# ─────────────────────────────────────────
# 7. MEDICINE — OpenFDA Drug Shortages
# ─────────────────────────────────────────
print("\n💊 Fetching drug shortage data from OpenFDA...")
try:
    url = "https://api.fda.gov/drug/shortages.json"
    params = {
        "api_key": FDA_KEY,
        "search": "status:\"Current\"",
        "limit": 50
    }
    r = requests.get(url, params=params, timeout=15)
    if r.status_code == 200:
        drugs = r.json().get("results", [])
        shortages = [
            {
                "name": d.get("generic_name", ""),
                "status": d.get("status", ""),
                "shortage_reason": d.get("shortage_reason", "")
            }
            for d in drugs[:20] if d.get("generic_name")
        ]
        output["medicine"]["current_shortages"] = shortages
        print(f"  ✓ {len(shortages)} drugs in current shortage")
    else:
        print(f"  ✗ OpenFDA shortages: {r.status_code}")
        output["errors"].append(f"OpenFDA shortages: {r.status_code}")
except Exception as e:
    print(f"  ✗ OpenFDA: {e}")
    output["errors"].append(f"OpenFDA: {str(e)}")

# ─────────────────────────────────────────
# WRITE OUTPUT
# ─────────────────────────────────────────
with open("data.json", "w") as f:
    json.dump(output, f, indent=2)

print("\n" + "=" * 60)
print("✅  data.json written successfully")
print(f"  Grocery prices:      {len(output['groceries'])} items")
print(f"  Commodity signals:   {len(output['commodity_signals'])} signals")
print(f"  Gas regions:         {len(output['gas'])} regions")
print(f"  Electricity states:  {len(output['electricity'])} states")
print(f"  Housing metros:      {len(output['housing'])} metros")
print(f"  Errors:              {len(output['errors'])}")
print("=" * 60)
print("Next: upload data.json to GitHub → Vercel auto-deploys")
