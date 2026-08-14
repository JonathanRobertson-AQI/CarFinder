"""Local web UI for CarFinder.

A simple, non-technical entry point: configure your search, click a button
to log into Facebook (session is saved locally), click a button to run the
search, and view results in a table -- no command line required beyond
starting this app.

Run with:
    python app.py
Then open http://127.0.0.1:5000 in your browser.
"""
from __future__ import annotations

import logging
import threading
import webbrowser
from pathlib import Path
from typing import Optional

from flask import Flask, redirect, render_template, request, url_for, jsonify

from carfinder.config import SearchConfig
from carfinder.db import ListingStore
from carfinder.facebook_auth import DEFAULT_STORAGE_STATE_PATH, login_and_save_session
from carfinder.pipeline import run_pipeline
from carfinder.valuation import evaluate_listing
from carfinder.report import ReportRow, dedupe_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("carfinder.app")

app = Flask(__name__)

CONFIG_PATH = SearchConfig.default_path()
ALL_SOURCES = ["facebook", "craigslist", "cars_com"]

# In-memory job state. This is a single-user, single-machine local tool, so
# a simple in-process lock/state object (rather than a task queue/database)
# is sufficient.
_job_lock = threading.Lock()
_job_state: dict = {"running": False, "kind": None, "log": [], "error": None}


def _load_config() -> SearchConfig:
    if CONFIG_PATH.exists():
        return SearchConfig.from_file(CONFIG_PATH)
    return SearchConfig()


def _append_log(message: str) -> None:
    with _job_lock:
        _job_state["log"].append(message)


def _facebook_session_exists() -> bool:
    return Path(DEFAULT_STORAGE_STATE_PATH).exists()


def _get_latest_rows(config: SearchConfig) -> list[ReportRow]:
    """Read current active listings + valuations from the DB without scraping."""
    store = ListingStore()
    active = store.active_listings(make=config.make, model=config.model)
    comparable_prices = store.comparable_prices(
        config.make, config.model, config.year_min, config.year_max
    )
    rows: list[ReportRow] = []
    for record in active:
        others = [
            p for p in comparable_prices
            if record["price"] is None or p != record["price"]
        ]
        valuation = evaluate_listing(
            record["price"],
            others or comparable_prices,
            min_sample_size=config.min_sample_size_for_valuation,
            good_deal_percentile=config.good_deal_percentile,
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
            )
        )
    return dedupe_rows(rows)


@app.route("/")
def index():
    config = _load_config()
    rows = _get_latest_rows(config)
    with _job_lock:
        job_state = dict(_job_state)
    return render_template(
        "index.html",
        config=config,
        all_sources=ALL_SOURCES,
        rows=rows,
        facebook_logged_in=_facebook_session_exists(),
        job=job_state,
    )


@app.route("/config", methods=["POST"])
def update_config():
    form = request.form
    sources = form.getlist("sources") or ["craigslist", "cars_com"]

    def _float_or_none(value: str) -> Optional[float]:
        return float(value) if value else None

    def _int_or_none(value: str) -> Optional[int]:
        return int(value) if value else None

    config = SearchConfig(
        make=form.get("make", "Honda").strip(),
        model=form.get("model", "Pilot").strip(),
        year_min=int(form.get("year_min", 2009)),
        year_max=int(form.get("year_max", 2015)),
        price_min=_float_or_none(form.get("price_min", "")),
        price_max=_float_or_none(form.get("price_max", "")),
        location=form.get("location", "80301").strip(),
        radius_miles=int(form.get("radius_miles", 100)),
        max_mileage=_int_or_none(form.get("max_mileage", "")),
        sources=sources,
        min_sample_size_for_valuation=int(form.get("min_sample_size_for_valuation", 5)),
        good_deal_percentile=float(form.get("good_deal_percentile", 25.0)),
    )
    config.to_file(CONFIG_PATH)
    return redirect(url_for("index"))


@app.route("/login-facebook", methods=["POST"])
def login_facebook():
    with _job_lock:
        if _job_state["running"]:
            return jsonify({"ok": False, "error": "A job is already running."}), 409
        _job_state.update(running=True, kind="facebook_login", log=[], error=None)

    def worker():
        try:
            login_and_save_session(on_progress=_append_log)
        except Exception as exc:  # noqa: BLE001 -- surface any failure to the UI
            logger.exception("Facebook login failed")
            with _job_lock:
                _job_state["error"] = str(exc)
        finally:
            with _job_lock:
                _job_state["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/run", methods=["POST"])
def run_search():
    with _job_lock:
        if _job_state["running"]:
            return jsonify({"ok": False, "error": "A job is already running."}), 409
        _job_state.update(running=True, kind="search", log=[], error=None)

    config = _load_config()

    def worker():
        try:
            run_pipeline(
                config,
                headless=True,
                decode_vins=True,
                storage_state_path=DEFAULT_STORAGE_STATE_PATH,
                on_progress=_append_log,
            )
        except Exception as exc:  # noqa: BLE001 -- surface any failure to the UI
            logger.exception("Search failed")
            with _job_lock:
                _job_state["error"] = str(exc)
        finally:
            with _job_lock:
                _job_state["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/status")
def status():
    with _job_lock:
        return jsonify(dict(_job_state))


def main() -> None:
    url = "http://127.0.0.1:5000"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=5000, threaded=True)


if __name__ == "__main__":
    main()
