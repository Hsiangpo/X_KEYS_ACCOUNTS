"""Cookie session lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Callable

from src.config import DEFAULT_LOGIN_BROWSER_CHANNELS, DEFAULT_LOGIN_TIMEOUT_SECONDS


ProbeFn = Callable[[list[dict]], bool]
STEALTH_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
IGNORE_DEFAULT_AUTOMATION_ARGS = ["--enable-automation"]


@dataclass
class SessionManager:
    """Manage cookie storage and manual login refresh."""

    cookies_path: Path
    login_timeout_seconds: int = DEFAULT_LOGIN_TIMEOUT_SECONDS
    browser_channels: tuple[str, ...] = DEFAULT_LOGIN_BROWSER_CHANNELS

    def load_cookies(self) -> list[dict] | None:
        if not self.cookies_path.exists():
            return None
        content = json.loads(self.cookies_path.read_text(encoding="utf-8"))
        if isinstance(content, list):
            return content
        return None

    def save_cookies(self, cookies: list[dict]) -> None:
        self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
        self.cookies_path.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def ensure_cookies(self, probe: ProbeFn) -> list[dict]:
        existing = self.load_cookies()
        if existing:
            probe_ok = False
            try:
                probe_ok = probe(existing)
            except Exception as exc:
                print(f"[登录] 现有 cookie 探测异常: {exc}")
            if probe_ok:
                return existing
            if self._has_core_auth_cookies(existing):
                print(
                    "[登录] 现有 cookie 探测未通过，但检测到 auth_token+ct0。"
                    "先复用会话，若请求鉴权失败再自动重登。"
                )
                return existing
        return self.refresh_cookies(probe)

    def refresh_cookies(self, probe: ProbeFn) -> list[dict]:
        cookies = self._interactive_login()
        probe_ok = False
        probe_error: Exception | None = None
        try:
            probe_ok = probe(cookies)
        except Exception as exc:
            probe_error = exc
            print(f"[登录] 凭据探测异常: {exc}")

        if not probe_ok:
            if self._has_core_auth_cookies(cookies):
                print(
                    "[登录] 登录后探测失败，但已捕获 auth_token+ct0，继续使用当前会话。"
                )
            else:
                detail = f": {probe_error}" if probe_error else ""
                raise RuntimeError(f"Login completed but credential probe failed{detail}.")
        self.save_cookies(cookies)
        return cookies

    def _interactive_login(self) -> list[dict]:
        # Lazy import keeps unit tests independent from Playwright runtime.
        from playwright.sync_api import sync_playwright

        print("\n[登录] 正在打开 X 官方登录页...")
        print("[登录] 请在浏览器中完成登录，系统会自动捕获 cookie。")

        with sync_playwright() as playwright:
            browser = self._launch_browser(playwright)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = context.new_page()
            page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=120000)

            deadline = time.time() + self.login_timeout_seconds
            warned_google_oauth = False
            while time.time() < deadline:
                cookies = context.cookies()
                has_auth = any(c.get("name") == "auth_token" and c.get("value") for c in cookies)
                has_ct0 = any(c.get("name") == "ct0" and c.get("value") for c in cookies)
                if has_auth and has_ct0:
                    print("[登录] 检测到登录成功，cookie 已捕获。")
                    browser.close()
                    return cookies

                if (
                    not warned_google_oauth
                    and "accounts.google.com/v3/signin/rejected" in page.url
                ):
                    warned_google_oauth = True
                    print(
                        "[登录] Google OAuth 拒绝当前浏览器上下文。"
                        "请改用账号密码登录，或安装桌面版 Chrome 后重试。"
                    )
                time.sleep(2)

            browser.close()
            raise TimeoutError(
                f"登录超时（{self.login_timeout_seconds}s）。请重试并尽快完成登录。"
            )

    def _launch_browser(self, playwright):
        common_launch_kwargs = {
            "headless": False,
            "args": STEALTH_LAUNCH_ARGS,
            "ignore_default_args": IGNORE_DEFAULT_AUTOMATION_ARGS,
        }
        last_error: Exception | None = None
        for channel in self.browser_channels:
            try:
                print(f"[登录] 尝试启动浏览器通道 '{channel}'...")
                return playwright.chromium.launch(
                    channel=channel,
                    **common_launch_kwargs,
                )
            except Exception as exc:
                print(f"[登录] 通道 '{channel}' 启动失败: {exc}")
                last_error = exc

        print(
            "[登录] 回退到内置 Chromium。"
            "注意：Google OAuth 可能拒绝此浏览器上下文。"
        )
        try:
            return playwright.chromium.launch(
                **common_launch_kwargs,
            )
        except Exception as exc:
            if last_error is not None:
                raise RuntimeError(
                    "Unable to launch any browser for login flow."
                ) from exc
            raise

    @staticmethod
    def _has_core_auth_cookies(cookies: list[dict]) -> bool:
        cookie_names = {
            str(cookie.get("name", ""))
            for cookie in cookies
            if cookie.get("value")
        }
        return "auth_token" in cookie_names and "ct0" in cookie_names
