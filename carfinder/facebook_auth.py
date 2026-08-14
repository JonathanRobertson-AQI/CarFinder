"""Facebook login helper.

Facebook Marketplace requires a logged-in session. Rather than have this
tool handle credentials directly (which would mean storing your Facebook
password), this opens a real, visible browser window where you log in
yourself -- including any 2FA/captcha challenges -- and once logged in,
saves the resulting session (cookies/local storage) to a local JSON file
so future scrapes can reuse it without logging in again.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("carfinder.facebook_auth")

DEFAULT_STORAGE_STATE_PATH = "facebook_session.json"
LOGIN_URL = "https://www.facebook.com/login"
# Facebook sets this cookie once a session is authenticated.
LOGGED_IN_COOKIE_NAME = "c_user"


def login_and_save_session(
    storage_state_path: str | Path = DEFAULT_STORAGE_STATE_PATH,
    timeout_seconds: float = 300,
    poll_interval_seconds: float = 2.0,
    on_progress: Optional[Callable[[str], None]] = None,
) -> bool:
    """Open a visible browser for the user to log into Facebook manually.

    Polls for the ``c_user`` cookie (set once logged in) and saves the
    session as soon as it appears, then closes the browser automatically.
    Returns True if login was detected and the session was saved, False if
    the timeout elapsed first.
    """
    def notify(message: str) -> None:
        logger.info(message)
        if on_progress:
            on_progress(message)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        notify(
            "Playwright is not installed. Run `pip install playwright` and "
            "`playwright install chromium` first."
        )
        return False

    notify("Opening a browser window -- please log into Facebook...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

            deadline = time.time() + timeout_seconds
            logged_in = False
            while time.time() < deadline:
                cookies = context.cookies()
                if any(c.get("name") == LOGGED_IN_COOKIE_NAME for c in cookies):
                    logged_in = True
                    break
                time.sleep(poll_interval_seconds)

            if logged_in:
                context.storage_state(path=str(storage_state_path))
                notify(f"Logged in! Session saved to {storage_state_path}.")
            else:
                notify("Timed out waiting for login -- session was not saved.")
            return logged_in
        finally:
            browser.close()
