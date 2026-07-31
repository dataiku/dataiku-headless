"""Loopback-only browser setup for Dataiku instance credentials."""

import secrets
import threading
import webbrowser
from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import config

SESSION_LIFETIME_SECONDS = 10 * 60
MAX_REQUEST_BYTES = 16 * 1024
_active_session: "SetupSession | None" = None
_session_lock = threading.Lock()


@dataclass
class SetupSession:
    url: str
    server: ThreadingHTTPServer
    thread: threading.Thread
    timer: threading.Timer
    browser_opened: bool
    completed: threading.Event
    result: dict | None = None
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


def _page(*, error: str = "") -> str:
    error_markup = (
        f'<div class="error" role="alert">{escape(error)}</div>' if error else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Configure Dataiku</title>
  <style>
    :root {{ color-scheme: light; --ink:#152536; --muted:#667585; --teal:#00a6a6; --deep:#123b46; --line:#dbe5e8; --bg:#edf6f5; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; min-height:100vh; font:15px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--ink); background:radial-gradient(circle at 8% 8%, #d4f5ef 0, transparent 34%), linear-gradient(135deg, var(--bg), #f7fafb 70%); }}
    main {{ width:min(720px, calc(100% - 32px)); margin:48px auto; }}
    .brand {{ display:flex; align-items:center; gap:12px; margin-bottom:20px; color:var(--deep); font-weight:750; letter-spacing:.01em; }}
    .mark {{ width:34px; height:34px; border-radius:10px; display:grid; place-items:center; color:white; background:var(--teal); box-shadow:0 8px 20px #00a6a63d; }}
    .card {{ background:#fff; border:1px solid #ffffffcc; border-radius:22px; padding:34px; box-shadow:0 24px 70px #17424c1a; }}
    h1 {{ margin:0; font-size:clamp(28px, 5vw, 42px); line-height:1.08; letter-spacing:-.035em; }}
    .intro {{ color:var(--muted); font-size:16px; margin:12px 0 28px; max-width:58ch; }}
    .security {{ display:flex; gap:11px; align-items:flex-start; background:#effaf7; color:#245d57; border:1px solid #ccece4; border-radius:13px; padding:13px 15px; margin-bottom:25px; }}
    .security strong {{ display:block; color:#184a45; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
    label {{ display:block; font-weight:650; margin-bottom:7px; }}
    .full {{ grid-column:1 / -1; }}
    input[type=text], input[type=url], input[type=password] {{ width:100%; border:1px solid var(--line); border-radius:11px; padding:12px 13px; color:var(--ink); background:#fbfdfd; font:inherit; outline:none; transition:.15s; }}
    input:focus {{ border-color:var(--teal); box-shadow:0 0 0 3px #00a6a61f; background:white; }}
    .hint {{ color:var(--muted); font-size:12.5px; margin-top:5px; }}
    .checks {{ display:grid; gap:10px; margin:16px 0 22px; }}
    .check {{ display:flex; gap:10px; align-items:flex-start; font-weight:500; margin:0; }}
    .check input {{ margin-top:4px; accent-color:var(--teal); flex:0 0 auto; }}
    button {{ width:100%; border:0; border-radius:12px; padding:13px 18px; color:white; background:linear-gradient(135deg, var(--teal), #007f87); font:700 15px/1 inherit; cursor:pointer; box-shadow:0 10px 25px #008b9240; }}
    button:hover {{ filter:brightness(.97); transform:translateY(-1px); }}
    .error {{ background:#fff1f1; color:#9b2d30; border:1px solid #f0c7c8; border-radius:11px; padding:11px 13px; margin-bottom:18px; }}
    footer {{ text-align:center; color:var(--muted); font-size:12.5px; margin-top:18px; }}
    @media (max-width:600px) {{ main {{ margin:22px auto; }} .card {{ padding:24px; }} .grid {{ grid-template-columns:1fr; }} .full {{ grid-column:auto; }} }}
  </style>
</head>
<body>
  <main>
    <div class="brand"><span class="mark">D</span> Dataiku Headless</div>
    <section class="card">
      <h1>Configure Dataiku</h1>
      <p class="intro">Add or update a Dataiku instance.</p>
      <div class="security"><span>🔒</span><div><strong>Stored locally on this machine.</strong>The API key is saved to the resolved Dataiku configuration file with user-only (0600) file permissions. This setup page is served only on 127.0.0.1 and expires after 10 minutes.</div></div>
      {error_markup}
      <form method="post" autocomplete="off">
        <div class="grid">
          <div><label for="name">Instance name</label><input id="name" name="name" type="text" placeholder="production" maxlength="80" required><div class="hint">A short name used when switching instances.</div></div>
          <div><label for="description">Description</label><input id="description" name="description" type="text" placeholder="Production DSS"></div>
          <div class="full"><label for="url">Instance URL</label><input id="url" name="url" type="url" placeholder="https://your-instance.dataiku.com" title="Enter an http:// or https:// URL from your Dataiku instance." aria-describedby="url-hint" required><div class="hint" id="url-hint">Paste any page URL from your Dataiku instance. Only its base address will be saved.</div></div>
          <div class="full"><label for="api_key">API key</label><input id="api_key" name="api_key" type="password" required><div class="hint">Create one in Dataiku under Profile &amp; Settings → API keys.</div></div>
        </div>
        <div class="checks">
          <label class="check"><input type="checkbox" name="set_default" checked><span>Use this instance by default when Dataiku Headless starts.</span></label>
          <label class="check"><input type="checkbox" name="no_check_certificate"><span>Skip certificate verification (only for trusted instances with self-signed certificates).</span></label>
        </div>
        <button type="submit">Save instance</button>
      </form>
    </section>
    <footer>This page is served only on 127.0.0.1 and cannot be reached from another computer.</footer>
  </main>
</body>
</html>"""


def _success_page(name: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Dataiku configured</title><style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#edf6f5;color:#152536;font:16px/1.5 system-ui,sans-serif}}main{{max-width:560px;margin:24px;padding:42px;background:white;border-radius:22px;box-shadow:0 24px 70px #17424c1a;text-align:center}}.ok{{width:54px;height:54px;margin:auto;display:grid;place-items:center;border-radius:50%;background:#00a6a6;color:white;font-size:28px}}h1{{margin:18px 0 8px}}p{{color:#667585}}</style></head><body><main><div class="ok">✓</div><h1>Dataiku is configured</h1><p><strong>{escape(name)}</strong> is now the active instance. You can close this tab and continue in your AI coding tool.</p></main></body></html>"""


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
                values = _validate_form(
                    parse_qs(
                        self.rfile.read(content_length).decode("utf-8"),
                        keep_blank_values=True,
                    )
                )
                result = config.add_instance_to_config(**values)
                config.set_current_instance(result["name"])
            except (UnicodeDecodeError, ValueError, RuntimeError) as exc:
                self._send_html(400, _page(error=str(exc)))
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
