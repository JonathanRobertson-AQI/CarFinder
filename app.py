"""Local web UI for CarFinder.

A simple, non-technical entry point: configure your search, click a button
to log into Facebook (session is saved locally), click a button to run the
search, and view results in a table -- no command line required beyond
starting this app.

Multiple searches can run at the same time (e.g. from separate browser
tabs/windows with different make/model/location settings) -- each "Run
Search Now" click starts its own independent background job using a
snapshot of that tab's form values, rather than sharing one global job.
All jobs write into the same shared listings database, so results from
every search show up together in the results table.

Run with:
    python app.py
Then open http://127.0.0.1:5000 in your browser.
"""
from __future__ import annotations

import logging
import threading
import uuid
import webbrowser
from pathlib import Path
from typing import Optional

from flask import Flask, redirect, render_template, request, url_for, jsonify

from carfinder.config import SearchConfig
from carfinder.db import ListingStore
from carfinder.facebook_auth import DEFAULT_STORAGE_STATE_PATH, login_and_save_session
from carfinder.pipeline import _values_within_filters, run_pipeline
from carfinder.valuation import evaluate_listing
from carfinder.report import ReportRow, dedupe_rows, rank_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("carfinder.app")

app = Flask(__name__)

CONFIG_PATH = SearchConfig.default_path()
ALL_SOURCES = ["facebook", "craigslist", "cars_com", "autotrader", "cargurus", "truecar"]

# In-memory job tracking, keyed by a random job_id so multiple searches can
# run at once (e.g. from separate browser tabs). Each job carries its own
# log/status; the frontend remembers the job_id it started and polls only
# that job. This is a single-user, single-machine local tool, so in-process
# state (rather than a task queue/database) is sufficient. Old finished jobs
# are trimmed so long-running processes don't accumulate memory forever.
_jobs_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_MAX_FINISHED_JOBS = 20

# Facebook login is kept to one-at-a-time: it's a one-off manual action (not
# a parallel search) and two logins racing to write the same session file
# would be confusing.
_facebook_login_lock = threading.Lock()
_facebook_login_running = False


def _load_config() -> SearchConfig:
    if CONFIG_PATH.exists():
        return SearchConfig.from_file(CONFIG_PATH)
    return SearchConfig()


def _config_from_form(form, defaults: Optional[SearchConfig] = None) -> SearchConfig:
    """Build a SearchConfig from submitted form fields.

    Falls back to ``defaults`` (or the built-in dataclass defaults) for any
    field not present, so this can be reused both for saving settings and
    for one-off parallel search runs.
    """
    defaults = defaults or SearchConfig()

    def _float_or_none(value: Optional[str], fallback):
        if value is None:
            return fallback
        return float(value) if value else None

    def _int_or_none(value: Optional[str], fallback):
        if value is None:
            return fallback
        return int(value) if value else None

    # An explicitly rendered-but-unchecked checkbox group means "no sources";
    # only fall back to defaults when the request came from a caller that did
    # not render the source controls.
    sources = form.getlist("sources") if "sources_present" in form else defaults.sources

    return SearchConfig(
        make=form.get("make", defaults.make).strip(),
        model=form.get("model", defaults.model).strip(),
        year_min=int(form.get("year_min", defaults.year_min)),
        year_max=int(form.get("year_max", defaults.year_max)),
        price_min=_float_or_none(form.get("price_min"), defaults.price_min),
        price_max=_float_or_none(form.get("price_max"), defaults.price_max),
        location=form.get("location", defaults.location).strip(),
        radius_miles=int(form.get("radius_miles", defaults.radius_miles)),
        max_mileage=_int_or_none(form.get("max_mileage"), defaults.max_mileage),
        sources=sources,
        min_sample_size_for_valuation=int(
            form.get("min_sample_size_for_valuation", defaults.min_sample_size_for_valuation)
        ),
        good_deal_percentile=float(
            form.get("good_deal_percentile", defaults.good_deal_percentile)
        ),
    )


def _new_job(kind: str) -> str:
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"running": True, "kind": kind, "log": [], "error": None}
        _trim_finished_jobs_locked()
    return job_id


def _trim_finished_jobs_locked() -> None:
    """Drop oldest finished jobs beyond _MAX_FINISHED_JOBS. Caller holds _jobs_lock."""
    finished = [jid for jid, state in _jobs.items() if not state["running"]]
    excess = len(finished) - _MAX_FINISHED_JOBS
    for jid in finished[:max(excess, 0)]:
        _jobs.pop(jid, None)


def _append_log(job_id: str, message: str) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["log"].append(message)


def _finish_job(job_id: str, error: Optional[str] = None) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["running"] = False
            _jobs[job_id]["error"] = error


def _facebook_session_exists() -> bool:
    return Path(DEFAULT_STORAGE_STATE_PATH).exists()


def _get_latest_rows(config: Optional[SearchConfig] = None) -> list[ReportRow]:
    """Read all currently-active listings + valuations from the shared DB.

    Not filtered to a single make/model, since multiple parallel searches
    for different vehicles may be tracked at once; comparable-price
    valuation is still computed per listing's own make/model/year range.
    """
    store = ListingStore()
    config = config or SearchConfig()
    active = [
        record for record in store.active_listings()
        if record["source"] in config.sources
        and record["make"] == config.make
        and record["model"] == config.model
        and _values_within_filters(
            record["year"], record["price"], record["mileage"], config
        )
    ]
    rows: list[ReportRow] = []
    # Cache comparable prices per (make, model, year_min, year_max) combo
    # actually used, computed lazily as needed below.
    comparable_cache: dict[tuple, list[float]] = {}
    default_config = config
    for record in active:
        year = record["year"] or default_config.year_min
        year_min = max(year - 3, 1900)
        year_max = year + 3
        cache_key = (record["make"], record["model"], year_min, year_max)
        if cache_key not in comparable_cache:
            comparable_cache[cache_key] = store.comparable_prices(
                record["make"], record["model"], year_min, year_max
            )
        comparable_prices = comparable_cache[cache_key]
        others = [
            p for p in comparable_prices
            if record["price"] is None or p != record["price"]
        ]
        valuation = evaluate_listing(
            record["price"],
            others or comparable_prices,
            min_sample_size=default_config.min_sample_size_for_valuation,
            good_deal_percentile=default_config.good_deal_percentile,
        )
        rows.append(
            ReportRow(
                title=record["title"],
                url=record["url"],
                source=record["source"],
                price=record["price"],
                year=record["year"],
                mileage=record["mileage"],
                location=record["location"],
                is_new=False,
                previous_price=None,
                valuation=valuation,
                make=record["make"],
                model=record["model"],
                posted_at=record["posted_at"],
            )
        )
    return rank_rows(dedupe_rows(rows))


@app.route("/")
def index():
    config = _load_config()
    rows = _get_latest_rows(config)
    return render_template(
        "index.html",
        config=config,
        all_sources=ALL_SOURCES,
        rows=rows,
        facebook_logged_in=_facebook_session_exists(),
    )


@app.route("/config", methods=["POST"])
def update_config():
    config = _config_from_form(request.form, defaults=_load_config())
    config.to_file(CONFIG_PATH)
    return redirect(url_for("index"))


@app.route("/login-facebook", methods=["POST"])
def login_facebook():
    global _facebook_login_running
    with _facebook_login_lock:
        if _facebook_login_running:
            return jsonify({"ok": False, "error": "A Facebook login is already in progress."}), 409
        _facebook_login_running = True

    job_id = _new_job("facebook_login")

    def worker():
        global _facebook_login_running
        try:
            login_and_save_session(on_progress=lambda msg: _append_log(job_id, msg))
            _finish_job(job_id)
        except Exception as exc:  # noqa: BLE001 -- surface any failure to the UI
            logger.exception("Facebook login failed")
            _finish_job(job_id, error=str(exc))
        finally:
            with _facebook_login_lock:
                _facebook_login_running = False

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/run", methods=["POST"])
def run_search():
    # Each run gets a snapshot of the submitted form (or the saved defaults
    # if no form fields were sent), so multiple tabs with different search
    # settings can run truly in parallel without clobbering one another.
    config = _config_from_form(request.form, defaults=_load_config()) if request.form else _load_config()

    job_id = _new_job("search")

    def worker():
        try:
            run_pipeline(
                config,
                headless=True,
                decode_vins=True,
                storage_state_path=DEFAULT_STORAGE_STATE_PATH,
                on_progress=lambda msg: _append_log(job_id, msg),
            )
            _finish_job(job_id)
        except Exception as exc:  # noqa: BLE001 -- surface any failure to the UI
            logger.exception("Search failed")
            _finish_job(job_id, error=str(exc))

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/status")
def status():
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id is required"}), 400
    with _jobs_lock:
        job_state = _jobs.get(job_id)
        if job_state is None:
            return jsonify({"error": "unknown job_id"}), 404
        return jsonify(dict(job_state))


def main() -> None:
    url = "http://127.0.0.1:5000"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=5000, threaded=True)


if __name__ == "__main__":
    main()
