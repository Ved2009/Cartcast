# CartCast — Real Price Intelligence for Every American

> Food companies have tracked commodity futures for decades to set your prices. Now you can too. Free. No ads. No signup. Powered by USDA + BLS + FRED + EIA + HUD + Census.

**Live site:** [cartcast.vercel.app](https://cartcast.vercel.app)

---

## What It Tracks

| Category | Data Source | Coverage |
|----------|------------|----------|
| 🛒 Groceries | BLS + USDA NASS + FRED | 55+ items, national + by state |
| ⛽ Gas Prices | EIA Weekly | 50 states + 50 cities |
| 💊 Medicine | OpenFDA + NLM RxNorm | 120+ OTC + Rx drugs |
| 🏠 Housing / Rent | HUD FMR + Rentcast | 25 major metros |
| ⚡ Utilities | EIA + state averages | All 50 states |
| 📱 Electronics | Aggregated retail | 60+ products |
| 🏛️ State Taxes | Tax Foundation 2025 | All 50 states |

## How It Works

1. **Government data APIs** (USDA, BLS, EIA, HUD, Census) pull real price data weekly
2. **Commodity signals** from FRED identify price direction 4–8 weeks ahead of retail
3. **State-level adjustment** factors apply regional cost-of-living differences
4. **Static frontend** (single `index.html`) displays everything — no backend server needed

## Data Sources

- **[BLS Average Price Survey](https://www.bls.gov/data/)**
- **[USDA NASS Quick Stats](https://quickstats.nass.usda.gov/)**
- **[FRED — St. Louis Fed](https://fred.stlouisfed.org/)**
- **[EIA — Energy Information Administration](https://www.eia.gov/opendata/)**
- **[HUD Fair Market Rents](https://www.huduser.gov/portal/datasets/fmr.html)**
- **[Census Bureau API](https://api.census.gov/)**
- **[OpenFDA](https://open.fda.gov/)**
- **[Rentcast](https://rentcast.io/)**

## Setup / Run Locally

```bash
# Install dependencies
pip install requests pandas

# Set environment variables (or paste keys directly in fetch_data.py for local use)
export BLS_API_KEY="your-key"
export USDA_API_KEY="your-key"
export FRED_API_KEY="your-key"
export EIA_API_KEY="your-key"

# Fetch data
python fetch_data.py

# Open the site
open index.html
```

## Deploying to Vercel (Free)

1. Push all files to a public GitHub repo
2. Go to [vercel.com](https://vercel.com) → Import → select your repo
3. Click Deploy — live in 60 seconds
4. Add API keys as **GitHub Secrets** (see below)
5. The GitHub Action auto-updates `data.json` every Monday at 9am

### GitHub Secrets to Add

In your repo → **Settings → Secrets and variables → Actions**:

| Secret Name | Value |
|------------|-------|
| `BLS_API_KEY` | Your BLS key |
| `USDA_API_KEY` | Your USDA NASS key |
| `FRED_API_KEY` | Your FRED key |
| `EIA_API_KEY` | Your EIA key |
| `OPENFDA_API_KEY` | Your OpenFDA / api.data.gov key |
| `HUD_API_KEY` | Your HUD JWT token |
| `CENSUS_API_KEY` | Your Census key |
| `RENTCAST_API_KEY` | Your Rentcast key |

## License

MIT — free to use, fork, and deploy. Attribution appreciated.

---

*Built by a frustrated grocery shopper. Powered by public data your tax dollars already fund.*
