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
import sys
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("carfinder.facebook_auth")

DEFAULT_STORAGE_STATE_PATH = "facebook_session.json"
LOGIN_URL = "https://www.facebook.com/login"
# Facebook sets this cookie once a session is authenticated.
LOGGED_IN_COOKIE_NAME = "c_user"


def _bring_window_to_front(title_substring: str, attempts: int = 5, delay_seconds: float = 1.0) -> bool:
    """Best-effort: bring a top-level window whose title contains
    ``title_substring`` to the foreground (Windows only).

    The login browser opens as its own OS window, separate from this app's
    UI, so it can easily open behind other windows and go unnoticed --
    especially since a freshly launched Chromium window doesn't reliably
    steal focus. This makes a few short attempts (the window's title only
    becomes "Facebook - ..." once the page finishes loading) and silently
    gives up if anything goes wrong; it's a convenience, not a requirement.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        GetWindowTextLengthW = user32.GetWindowTextLengthW
        GetWindowTextW = user32.GetWindowTextW
        IsWindowVisible = user32.IsWindowVisible

        for _ in range(attempts):
            found_hwnd = None

            def _callback(hwnd, _lparam):
                nonlocal found_hwnd
                if not IsWindowVisible(hwnd):
                    return True
                length = GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True
                buffer = ctypes.create_unicode_buffer(length + 1)
                GetWindowTextW(hwnd, buffer, length + 1)
                if title_substring.lower() in buffer.value.lower():
                    found_hwnd = hwnd
                    return False
                return True

            EnumWindows(EnumWindowsProc(_callback), 0)
            if found_hwnd:
                user32.ShowWindow(found_hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(found_hwnd)
                return True
            time.sleep(delay_seconds)
    except Exception:
        logger.debug("Could not bring the Facebook login window to front", exc_info=True)
    return False


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

    notify(
        "Opening a browser window -- please log into Facebook there. "
        "(A new browser window should appear -- check your taskbar if you "
        "don't see it right away, it can open behind other windows.)"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        try:
            context = browser.new_context(no_viewport=True)
            page = context.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            if _bring_window_to_front("Facebook"):
                notify("Brought the Facebook login window to the front.")

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
