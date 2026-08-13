# CarFinder

A reusable used-car search tool. Originally built to find a 2nd-generation
Honda Pilot (2009–2015), but the search criteria (make, model, year range,
price, location, radius, max mileage) are fully configurable via
`config.json`, so it can be pointed at any vehicle.

## What it does

- Scrapes listings from **Facebook Marketplace**, **Craigslist**, and
  **Cars.com** using [Playwright](https://playwright.dev/python/) browser
  automation.
- Persists listings in a local SQLite database (`carfinder.db`) so repeated
  runs can detect **new listings** and **price drops** since the last run.
- Decodes VINs (when a listing includes one) via the free, official
  [NHTSA vPIC API](https://vpic.nhtsa.dot.gov/api/) — no API key needed.
- Estimates a fair-market price for each listing by comparing it against the
  distribution of prices for comparable listings found in the same run
  (there is no free KBB API, so this is a practical stand-in for "blue book
  value"). Listings priced in the bottom percentile (configurable, default
  25th) are flagged as **good deals**.
- Generates a Markdown report (`reports/YYYY-MM-DD_Make_Model.md`)
  summarizing active listings, new listings, price drops, and good deals.

## Important limitations (read before use)

- **No official listings APIs exist** for Facebook Marketplace, Craigslist,
  or Cars.com/AutoTrader/CarGurus. This tool works by automating a real
  browser against the live sites. That means:
  - Selectors **will** break when these sites change their markup — this is
    expected maintenance, not a bug.
  - Running this in an automated/repeated fashion may violate these sites'
    Terms of Service. **This tool is intended for personal, on-demand,
    rate-limited use only** — run it manually, not on a tight schedule.
- **Facebook Marketplace requires a logged-in session.** This scraper does
  not handle login. Generate a `storage_state.json` once via Playwright's
  `browser_context.storage_state(path=...)` after manually logging in in a
  non-headless browser, then load it in `FacebookMarketplaceScraper` (not
  yet wired up — see TODO below) to reuse the session.
- **No free "blue book" valuation exists.** Value estimates here are derived
  from comparable listings found in the same scrape, not an authoritative
  source like KBB.
- **No vehicle history reports.** Full title/accident history (Carfax,
  AutoCheck) requires paid per-VIN lookups and is out of scope. Only
  NHTSA-decodable VIN data (make/model/year/trim/specs) is available.
- **Notifications are out of scope for phase 1.** The tool only produces a
  report file; no email/SMS/push integration yet.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# Uses config.json in the repo root
python main.py

# Override sources for a quick test of just one scraper
python main.py --sources craigslist

# Also decode VINs found in listings via NHTSA
python main.py --decode-vins

# Watch the browser while it scrapes (useful for debugging selectors)
python main.py --no-headless
```

Edit `config.json` to change make/model/year range/price/location/radius/
mileage cap, or point `--config` at an alternate file to search for a
different vehicle without touching the default config.

## Project layout

```
carfinder/
  config.py      # SearchConfig dataclass, loaded from config.json
  models.py      # Listing dataclass shared by all scrapers
  db.py          # SQLite persistence + comparable-price lookups
  vin.py         # NHTSA vPIC VIN decoding
  valuation.py   # Comparable-listing valuation / good-deal scoring
  report.py      # Markdown report generation
  scrapers/
    base.py      # Shared Playwright scraping scaffolding
    facebook.py
    craigslist.py
    cars_com.py
main.py          # CLI entrypoint wiring it all together
tests/           # Unit tests for the non-network-dependent logic
```

## Testing

```bash
pytest
```

Tests cover the database layer, valuation logic, VIN decoding (mocked HTTP),
and report rendering — not live scraping, since that depends on the current
state of third-party sites.

## Roadmap (not yet implemented)

- AutoTrader / CarGurus scrapers (same aggregator-site family as Cars.com).
- Facebook Marketplace login/session persistence wiring.
- Notifications (email/SMS/Discord) for new deals.
- Scheduled execution (currently designed for manual runs only).
