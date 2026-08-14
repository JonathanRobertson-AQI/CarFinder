"""Standalone Facebook login helper.

Opens a real browser window for you to log into Facebook, and saves the
resulting session to `facebook_session.json` so future scrapes of
Facebook Marketplace can reuse it. You can also trigger this from the web
UI's "Log into Facebook" button instead of running this directly.

Usage:
    python facebook_login.py
"""
import logging

from carfinder.facebook_auth import login_and_save_session

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    success = login_and_save_session(on_progress=print)
    raise SystemExit(0 if success else 1)
