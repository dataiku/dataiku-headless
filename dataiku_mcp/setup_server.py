# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Loopback-only browser setup for Dataiku instance credentials."""

import secrets
import threading
import webbrowser
from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import dataikuapi

from . import config

SESSION_LIFETIME_SECONDS = 10 * 60
MAX_REQUEST_BYTES = 16 * 1024
_active_session: "SetupSession | None" = None
_session_lock = threading.Lock()

# Keep the setup server single-route: this is the bird from the checked-in lockup.
DATAIKU_BIRD_SVG = """<svg class="bird" viewBox="0 0 200 200" aria-hidden="true" focusable="false">
  <path d="M191.342 139.061H108.562V154.536H191.342V139.061Z" fill="currentColor"/>
  <path d="M183.598 13.1855C179.295 5.34204 170.964 0 161.361 0C147.37 0 136.028 11.3412 136.028 25.3323C136.028 26.6678 136.156 27.9609 136.368 29.2328L134.226 31.8614L0.421086 196.935C-0.23607 197.74 -0.108879 198.927 0.696667 199.585C1.43862 200.178 2.51974 200.136 3.1981 199.457L59.5227 143.196C69.91 132.83 83.9858 127.001 98.6764 127.001H118.285C161.127 127.001 186.884 102.601 182.22 52.4664C180.609 35.2108 181.499 27.9397 187.414 20.6474C190.466 16.8953 196.381 9.56055 196.381 9.56055L189.449 11.5108L183.577 13.1643L183.598 13.1855ZM161.891 28.4485C158.096 28.4485 155.022 25.3747 155.022 21.5801C155.022 17.7856 158.096 14.7118 161.891 14.7118C165.685 14.7118 168.759 17.7856 168.759 21.5801C168.759 25.3747 165.685 28.4485 161.891 28.4485Z" fill="currentColor"/>
</svg>"""


@dataclass
class SetupSession:
    url: str
    server: ThreadingHTTPServer
    thread: threading.Thread
    timer: threading.Timer
    browser_opened: bool
    completed: threading.Event
    result: dict | None = None
    validated_connection: tuple[str, str, bool] | None = None
    expired: bool = False

    def close(self) -> None:
        self.timer.cancel()
        self.completed.set()
        self.server.shutdown()
        self.server.server_close()


def _validate_form(form: dict[str, list[str]]) -> dict:
    name = form.get("name", [""])[0].strip()
    url = form.get("url", [""])[0].strip()
    api_key = form.get("api_key", [""])[0].strip()
    description = form.get("description", [""])[0].strip()

    if not name:
        raise ValueError("Instance name is required.")
    if len(name) > 80 or any(ord(character) < 32 for character in name):
        raise ValueError("Instance name must be 80 characters or fewer.")
    if "\\" in url or any(
        ord(character) < 32 or character.isspace() for character in url
    ):
        raise ValueError("Instance URL contains invalid whitespace or backslashes.")
    try:
        parsed_url = urlsplit(url)
        port = parsed_url.port
        if parsed_url.netloc.endswith(":") or port == 0:
            raise ValueError
    except ValueError:
        raise ValueError(
            "Instance URL is malformed or contains an invalid port."
        ) from None
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise ValueError("Instance URL must be a complete http:// or https:// URL.")
    if parsed_url.username or parsed_url.password:
        raise ValueError("Instance URL cannot contain credentials.")
    url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    if not api_key:
        raise ValueError("API key is required.")

    return {
        "name": name,
        "url": url,
        "api_key": api_key,
        "description": description,
        "no_check_certificate": "no_check_certificate" in form,
        "set_default": "set_default" in form,
    }


def _page(
    *,
    error: str = "",
    status: str = "",
    values: dict | None = None,
    connection_validated: bool = False,
) -> str:
    error_markup = (
        f'<div class="error" role="alert">{escape(error)}</div>' if error else ""
    )
    status_markup = (
        f'<div class="status" role="status">{escape(status)}</div>' if status else ""
    )
    is_initial_page = values is None
    values = values or {}
    name = escape(values.get("name", ""))
    description = escape(values.get("description", ""))
    url = escape(values.get("url", ""))
    api_key = escape(values.get("api_key", ""))
    set_default = " checked" if is_initial_page or values.get("set_default") else ""
    no_check_certificate = " checked" if values.get("no_check_certificate") else ""
    save_disabled = "" if connection_validated else " disabled"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Configure Dataiku</title>
  <style>
    :root {{ color-scheme:light; --ink:#1a1a1a; --muted:#606b70; --teal:#00a6a6; --teal-dark:#007b7d; --line:#d9dfdf; --paper:#fffef9; --surface:#fff; --soft:#f3f7f6; --error:#a6242f; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; min-height:100vh; font:15px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--ink); background:var(--paper); border-top:4px solid var(--teal); }}
    main {{ width:min(720px, calc(100% - 32px)); margin:48px auto; }}
    .brand {{ display:flex; align-items:center; gap:12px; margin-bottom:24px; }}
    .bird {{ display:block; width:48px; height:48px; color:var(--ink); }}
    .brand-copy {{ display:grid; gap:1px; line-height:1; }}
    .brand-name {{ font-size:18px; font-weight:750; letter-spacing:-.02em; }}
    .brand-product {{ color:var(--muted); font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }}
    .card {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:32px; box-shadow:0 1px 2px #1a1a1a0d; }}
    h1 {{ margin:0; font-size:clamp(28px, 5vw, 38px); line-height:1.1; letter-spacing:-.035em; }}
    .intro {{ color:var(--muted); font-size:16px; margin:8px 0 24px; max-width:58ch; }}
    .security {{ display:flex; gap:16px; align-items:flex-start; background:var(--soft); border:1px solid #d6e9e5; border-radius:8px; padding:16px; margin-bottom:24px; }}
    .security-label {{ flex:0 0 auto; color:var(--teal-dark); font-size:11px; font-weight:750; letter-spacing:.08em; line-height:20px; text-transform:uppercase; }}
    .security strong {{ display:block; margin-bottom:2px; }}
    .security div {{ color:var(--muted); font-size:13px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
    label {{ display:block; font-size:13px; font-weight:650; margin-bottom:8px; }}
    .full {{ grid-column:1 / -1; }}
    input[type=text], input[type=url], input[type=password] {{ width:100%; border:1px solid var(--line); border-radius:8px; padding:11px 12px; color:var(--ink); background:var(--paper); font:inherit; outline:none; transition:border-color 150ms ease, box-shadow 150ms ease, background-color 150ms ease; }}
    input:hover {{ border-color:#aeb9b9; }}
    input:focus-visible {{ border-color:var(--teal-dark); box-shadow:0 0 0 3px #00a6a626; background:var(--surface); }}
    .hint {{ color:var(--muted); font-size:12px; margin-top:4px; }}
    .checks {{ display:grid; gap:12px; margin:20px 0 24px; }}
    .check {{ display:flex; gap:10px; align-items:flex-start; font-weight:500; margin:0; }}
    .check input {{ margin-top:4px; accent-color:var(--teal); flex:0 0 auto; }}
    details {{ margin-top:16px; }}
    summary {{ color:var(--muted); cursor:pointer; font-size:13px; font-weight:650; }}
    details .check {{ margin-top:12px; }}
    .actions {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
    button {{ width:100%; border:0; border-radius:8px; padding:12px 16px; color:white; background:var(--teal-dark); font:inherit; font-weight:700; line-height:1.2; cursor:pointer; transition:background-color 150ms ease, box-shadow 150ms ease; }}
    button:hover {{ background:#00696c; }}
    button:disabled, button:disabled:hover {{ color:#6f797d; background:#d9dfdf; cursor:not-allowed; }}
    button.secondary {{ color:var(--ink); background:var(--surface); border:1px solid var(--line); }}
    button.secondary:hover {{ background:var(--soft); }}
    button:focus-visible {{ outline:3px solid #00a6a64d; outline-offset:3px; }}
    .error {{ background:#fff4f3; color:var(--error); border:1px solid #f0c7c8; border-radius:8px; padding:12px; margin-bottom:20px; }}
    .status {{ background:#effaf7; color:#245d57; border:1px solid #ccece4; border-radius:8px; padding:12px; margin-bottom:20px; }}
    @media (max-width:600px) {{ main {{ margin:24px auto; }} .brand {{ margin-bottom:20px; }} .bird {{ width:40px; height:40px; }} .card {{ padding:24px; }} .security {{ flex-direction:column; gap:4px; }} .grid {{ grid-template-columns:1fr; }} .full {{ grid-column:auto; }} .actions {{ grid-template-columns:1fr; }} }}
    @media (prefers-reduced-motion:reduce) {{ input, button {{ transition:none; }} }}
  </style>
</head>
<body>
  <main>
    <header class="brand">{DATAIKU_BIRD_SVG}<span class="brand-copy"><span class="brand-name">Dataiku</span><span class="brand-product">Headless</span></span></header>
    <section class="card">
      <h1>Connect to Dataiku</h1>
      <p class="intro">Add or update the instance this agent can use.</p>
      <div class="security"><span class="security-label">Local only</span><div><strong>Your credentials stay on this machine.</strong>The API key is saved with user-only (0600) file permissions. This page runs on 127.0.0.1 and expires after 10 minutes.</div></div>
      {error_markup}
      <form method="post" autocomplete="off">
        <div class="grid">
          <div><label for="name">Instance name</label><input id="name" name="name" type="text" placeholder="production" value="{name}" maxlength="80" required><div class="hint">A short name used when switching instances.</div></div>
          <div><label for="description">Description</label><input id="description" name="description" type="text" placeholder="Production Dataiku" value="{description}"></div>
          <div class="full"><label for="url">Instance URL</label><input id="url" name="url" type="url" placeholder="https://your-instance.dataiku.com" value="{url}" aria-describedby="url-hint" required><div class="hint" id="url-hint">Enter the URL of your Dataiku instance.</div></div>
          <div class="full"><label for="api_key">API key</label><input id="api_key" name="api_key" type="password" value="{api_key}" required><div class="hint">Create one in Dataiku under Profile &amp; Settings → API keys.</div></div>
        </div>
        <div class="checks">
          <label class="check"><input type="checkbox" name="set_default"{set_default}><span>Use this instance by default when Dataiku Headless starts.</span></label>
        </div>
        <details><summary>Advanced options</summary><label class="check"><input type="checkbox" name="no_check_certificate"{no_check_certificate}><span>Skip certificate verification (only for trusted instances with self-signed certificates).</span></label></details>
        {status_markup}
        <div class="actions"><button class="secondary" type="submit" name="action" value="test">Test connection</button><button type="submit" name="action" value="save"{save_disabled}>Save instance</button></div>
      </form>
    </section>
  </main>
</body>
</html>"""


def _success_page(name: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dataiku configured</title>
  <style>
    :root {{ color-scheme:light; --ink:#1a1a1a; --muted:#606b70; --teal:#00a6a6; --paper:#fffef9; --line:#d9dfdf; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; color:var(--ink); background:var(--paper); border-top:4px solid var(--teal); font:16px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ width:min(520px, calc(100% - 32px)); margin:32px auto; padding:32px; background:white; border:1px solid var(--line); border-radius:12px; box-shadow:0 1px 2px #1a1a1a0d; text-align:center; }}
    .bird {{ display:block; width:56px; height:56px; margin:0 auto 24px; color:var(--ink); }}
    .ok {{ width:32px; height:32px; margin:auto; display:grid; place-items:center; border-radius:50%; background:var(--teal); color:white; font-size:18px; font-weight:800; }}
    h1 {{ margin:16px 0 8px; font-size:30px; line-height:1.15; letter-spacing:-.03em; }}
    p {{ margin:0; color:var(--muted); }}
    strong {{ color:var(--ink); }}
    @media (max-width:480px) {{ main {{ padding:24px; }} }}
  </style>
</head>
<body>
  <main>
    {DATAIKU_BIRD_SVG}
    <div class="ok">✓</div>
    <h1>Dataiku is connected</h1>
    <p><strong>{escape(name)}</strong> is now the active instance. You can close this tab and continue in your AI coding tool.</p>
  </main>
</body>
</html>"""


def _test_connection(values: dict) -> None:
    try:
        client = dataikuapi.DSSClient(values["url"], values["api_key"])
        client._session.verify = not values["no_check_certificate"]
        client.get_auth_info()
    except Exception as exc:
        raise ValueError(
            "Could not connect. Check the URL, API key, and certificate settings."
        ) from exc


def _connection_settings(values: dict) -> tuple[str, str, bool]:
    return values["url"], values["api_key"], values["no_check_certificate"]


def _make_handler(token: str, expected_host: str, session_state: SetupSession | None):
    class SetupHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def _send_html(self, status: int, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
            )
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(encoded)

        def _valid_request(self) -> bool:
            return (
                self.path == f"/{token}" and self.headers.get("Host") == expected_host
            )

        def do_GET(self) -> None:
            if not self._valid_request():
                self.send_error(404)
                return
            self._send_html(200, _page())

        def do_POST(self) -> None:
            if not self._valid_request():
                self.send_error(404)
                return
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{expected_host}":
                self.send_error(403)
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                    raise ValueError("The submitted form is empty or too large.")
                form = parse_qs(
                    self.rfile.read(content_length).decode("utf-8"),
                    keep_blank_values=True,
                )
                values = _validate_form(form)
                action = form.get("action", ["save"])[0]
                if action == "test":
                    _test_connection(values)
                    if session_state:
                        session_state.validated_connection = _connection_settings(
                            values
                        )
                    self._send_html(
                        200,
                        _page(
                            status="Connection successful. You can now save this instance.",
                            values=values,
                            connection_validated=True,
                        ),
                    )
                    return
                if action != "save":
                    raise ValueError("Unknown setup action.")
                if (
                    not session_state
                    or session_state.validated_connection
                    != _connection_settings(values)
                ):
                    raise ValueError(
                        "Test the connection successfully before saving. Test again after changing the URL, API key, or certificate setting."
                    )
                result = config.add_instance_to_config(**values)
                config.set_current_instance(result["name"])
            except (UnicodeDecodeError, ValueError, RuntimeError) as exc:
                self._send_html(
                    400, _page(error=str(exc), values=locals().get("values"))
                )
                return

            self._send_html(200, _success_page(result["name"]))
            if session_state:
                session_state.result = result
                session_state.timer.cancel()
                session_state.completed.set()
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    return SetupHandler


def start_setup_server(*, open_browser: bool = True) -> SetupSession:
    """Start one temporary setup page on a random loopback port and URL token."""
    global _active_session

    with _session_lock:
        if _active_session:
            _active_session.close()

        token = secrets.token_urlsafe(24)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(token, "", None))
        host = f"127.0.0.1:{server.server_port}"
        url = f"http://{host}/{token}"
        thread = threading.Thread(target=server.serve_forever, daemon=True)

        completed = threading.Event()

        def expire() -> None:
            session.expired = True
            session.completed.set()
            server.shutdown()

        timer = threading.Timer(SESSION_LIFETIME_SECONDS, expire)
        timer.daemon = True
        session = SetupSession(url, server, thread, timer, False, completed)
        server.RequestHandlerClass = _make_handler(token, host, session)
        thread.start()
        timer.start()
        browser_opened = webbrowser.open(url, new=2) if open_browser else False
        session.browser_opened = browser_opened
        _active_session = session
        return _active_session
