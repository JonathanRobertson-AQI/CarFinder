# CarFinder

A reusable used-car search tool. Originally built to find a 2nd-generation
Honda Pilot (2009–2015), but the search criteria (make, model, year range,
price, location, radius, max mileage) are fully configurable via
`config.json`, so it can be pointed at any vehicle.

## What it does

- Scrapes listings from **Facebook Marketplace**, **Craigslist**, **Cars.com**,
  **AutoTrader**, **CarGurus**, and **TrueCar** using
  [Playwright](https://playwright.dev/python/) browser automation.
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
  Cars.com, AutoTrader, CarGurus, or TrueCar. This tool works by automating a real
  browser against the live sites. That means:
  - Selectors **will** break when these sites change their markup — this is
    expected maintenance, not a bug.
  - Running this in an automated/repeated fashion may violate these sites'
    Terms of Service. **This tool is intended for personal, on-demand,
    rate-limited use only** — run it manually, not on a tight schedule.
- **Facebook Marketplace may require a logged-in session.** In testing,
  logged-out public searches worked, but Facebook can show a login wall for
  some searches/locations/accounts. If you see zero Facebook results, use the
  "Log into Facebook" button in the web UI (or `python facebook_login.py`),
  which opens a real browser window for you to log in yourself — the tool
  never sees your password, and only stores the resulting session cookies
  locally in `facebook_session.json`.
- **No free "blue book" valuation exists.** Value estimates here are derived
  from comparable listings found in the same scrape, not an authoritative
  source like KBB.
- **No vehicle history reports.** Full title/accident history (Carfax,
  AutoCheck) requires paid per-VIN lookups and is out of scope. Only
  NHTSA-decodable VIN data (make/model/year/trim/specs) is available.
- **Notifications are out of scope for phase 1.** The tool only produces a
  report file; no email/SMS/push integration yet.

## Getting started (web UI — recommended, no command line needed after setup)

```powershell
pip install -r requirements.txt
playwright install chromium
python app.py
```

This opens `http://127.0.0.1:5000` in your browser automatically. From there:

1. **Search Settings** — set make/model/year range/price/location/radius/
   mileage and which sources to search, then click **Save Settings**.
2. **Facebook Login** — click **Log into Facebook** once. A real browser
   window opens; log in there (including any 2FA). The app detects when
   you're logged in, saves the session, and closes the window automatically.
3. **Run Search Now** — click to scrape all selected sources. Progress is
   shown live; when done, the results table refreshes with new listings and
   good deals highlighted.

Re-run the search any time by clicking the button again — it's meant for
manual, on-demand use.

**Running multiple searches at once:** open `http://127.0.0.1:5000` in
another browser tab or window, change the Search Settings there (e.g. a
different make/model, location, or price range), and click **Run Search
Now** — each tab starts its own independent background job, so several
searches can run in parallel. All results land in the same shared results
table/database, tagged with their vehicle in the **Vehicle** column. The
one exception is **Facebook Login**, which only runs one at a time since
it's a one-off manual step, not a parallel search.

## Command-line usage (alternative / advanced)

```bash
# Uses config.json in the repo root
python main.py

# Override sources for a quick test of just one scraper
python main.py --sources craigslist

# Also decode VINs found in listings via NHTSA
python main.py --decode-vins

# Watch the browser while it scrapes (useful for debugging selectors)
python main.py --no-headless

# Log into Facebook from the command line instead of the web UI
python facebook_login.py
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
  pipeline.py    # Shared scrape -> persist -> valuate -> report flow
  facebook_auth.py  # Manual Facebook login helper (used by the web UI)
  scrapers/
    base.py      # Shared Playwright scraping scaffolding
    facebook.py
    craigslist.py
    cars_com.py  # Uses Cars.com's embedded structured vehicle-data JSON
    aggregator.py  # Shared JSON-LD/card parsing for dealer aggregators
    autotrader.py
    cargurus.py
    truecar.py
app.py           # Web UI (Flask) -- recommended way to run this tool
main.py          # CLI entrypoint (same pipeline, no browser UI)
facebook_login.py  # Standalone CLI alternative to the web UI's login button
templates/       # HTML template for the web UI
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

- Improve source-specific selectors as AutoTrader, CarGurus, and TrueCar markup
  changes or bot protection varies by network.
- Verifying the Facebook Marketplace scraper against a real, logged-in
  session (the login flow is implemented and the scraper works logged-out,
  but a logged-in run hasn't been exercised end-to-end).
- Notifications (email/SMS/Discord) for new deals.
- Scheduled execution (currently designed for manual runs only).
- De-duplicating near-identical repost listings (e.g. dealers who repost
  the same vehicle many times on Craigslist currently show up as separate
  rows).
