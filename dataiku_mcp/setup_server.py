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

"""Temporary loopback instance manager for local stdio profiles."""

import hashlib
import hmac
import json
import secrets
import threading
import webbrowser
from dataclasses import dataclass, field
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import get_args
from urllib.parse import parse_qs, urlsplit

import dataikuapi

from .config import stdio
from .config.models import InstanceType, StdioConfig, StdioDSSInstanceConfig
from .instance_policy import SUPPORTED_DSS_INSTANCE_TYPES

SESSION_LIFETIME_SECONDS = 10 * 60
MAX_REQUEST_BYTES = 16 * 1024
_active_session: "SetupSession | None" = None
_session_lock = threading.Lock()
_revision_key = secrets.token_bytes(32)

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
    settings_path: Path
    result: dict | None = None
    validated_connection: tuple | None = field(default=None, repr=False)
    validation_id: str = ""
    expired: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def close(self) -> None:
        self.timer.cancel()
        self.completed.set()
        self.validated_connection = None
        self.validation_id = ""
        self.server.shutdown()
        self.server.server_close()


def _validate_form(
    form: dict[str, list[str]], existing: StdioDSSInstanceConfig | None = None
) -> dict:
    name = form.get("name", [""])[0].strip()
    url = form.get("url", [""])[0].strip()
    api_key = form.get("api_key", [""])[0].strip()
    description = form.get("description", [""])[0].strip()
    instance_type = form.get("instance_type", [""])[0]

    if instance_type not in get_args(InstanceType):
        raise ValueError(
            "Instance type must be one of: " + ", ".join(get_args(InstanceType)) + "."
        )

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
    if not api_key and existing is None:
        raise ValueError("API key is required.")

    return {
        "name": name,
        "url": url,
        "api_key": api_key or (existing.api_key if existing else None),
        "api_ticket": existing.api_ticket if existing and not api_key else None,
        "description": description,
        "instance_type": instance_type,
        "no_check_certificate": "no_check_certificate" in form,
        "set_default": "set_default" in form,
    }


def _snapshot(config: StdioConfig | None = None) -> dict:
    config = config if config is not None else stdio.get_profile_config()
    instances = {
        name: instance.to_instance(name)
        for name, instance in config.dss_instances.items()
    }
    # Environment entries shadow saved profiles and remain read-only.
    instances.update(
        (name, instance)
        for name, instance in stdio.get_instances().items()
        if instance.source != "config"
    )
    current = stdio.get_current_instance()
    return {
        "supported_instance_types": sorted(SUPPORTED_DSS_INSTANCE_TYPES),
        "connections": [
            {
                "name": instance.name,
                "url": instance.url,
                "instance_type": instance.instance_type,
                "description": instance.description,
                "no_check_certificate": instance.no_check_certificate,
                "source": instance.source,
                "revision": (
                    _profile_revision(config.dss_instances[instance.name])
                    if instance.source == "config"
                    else ""
                ),
            }
            for instance in instances.values()
        ],
        "active": current.name if current else None,
        "default": config.default_instance,
        "environment_precedence": any(i.source != "config" for i in instances.values()),
    }


def _profile_revision(instance: StdioDSSInstanceConfig) -> str:
    """Opaque version for stale editor/delete detection, never a raw secret hash."""
    return hmac.new(
        _revision_key, instance.model_dump_json().encode(), hashlib.sha256
    ).hexdigest()


def _page(state: dict | None = None, *, nonce: str = "") -> str:
    template = Path(__file__).with_name("setup_page.html").read_text(encoding="utf-8")
    payload = json.dumps(state or {}, ensure_ascii=True).replace("<", "\\u003c")
    return (
        template.replace("__BIRD__", DATAIKU_BIRD_SVG)
        .replace("__NONCE__", nonce)
        .replace("__STATE__", payload)
    )


def _test_connection(values: dict) -> None:
    if values["instance_type"] not in SUPPORTED_DSS_INSTANCE_TYPES:
        raise ValueError(
            f"Connection testing is unavailable for {values['instance_type']}. Save the profile without testing."
        )
    client = None
    try:
        client = dataikuapi.DSSClient(
            values["url"],
            api_key=values["api_key"],
            internal_ticket=values["api_ticket"],
            no_check_certificate=values["no_check_certificate"],
        )
        client._session.request = partial(client._session.request, timeout=15)
        client.get_auth_info()
    except Exception as exc:
        raise ValueError(f"Could not connect: {exc}") from None
    finally:
        if client is not None:
            client._session.close()


def _candidate(form: dict[str, list[str]]) -> tuple:
    original_name = form.get("original_name", [""])[0] or None
    config = stdio.get_profile_config()
    connections = {i["name"]: i for i in _snapshot(config)["connections"]}
    if original_name:
        instance = connections.get(original_name)
        if not instance or instance["source"] != "config":
            raise ValueError("This saved instance cannot be edited. Refresh the list.")
    existing = config.dss_instances.get(original_name) if original_name else None
    if existing is not None and form.get("revision", [""])[0] != _profile_revision(
        existing
    ):
        raise ValueError("This instance changed. Reopen the manager and test again.")
    values = _validate_form(form, existing)
    if values["name"] != original_name and values["name"] in connections:
        raise ValueError("An instance with this name already exists.")
    instance = StdioDSSInstanceConfig(
        **{k: v for k, v in values.items() if k not in {"name", "set_default"}}
    )
    return original_name, existing, instance, values["name"]


def _connection_identity(candidate: tuple) -> tuple:
    original, existing, instance, _ = candidate
    # Description and name changes do not change the authenticated target.
    return (
        original,
        existing,
        instance.url,
        instance.api_key,
        instance.api_ticket,
        instance.no_check_certificate,
        instance.instance_type,
    )


def _perform_action(session: SetupSession, form: dict[str, list[str]]) -> dict:
    if session.expired or session.completed.is_set():
        raise ValueError(
            "This instance manager has closed. Open it again from your agent."
        )
    if session.settings_path != stdio.get_settings_path():
        raise ValueError("The profile file changed. Open the instance manager again.")
    action = form.get("action", [""])[0]
    name = form.get("name", [""])[0]
    if action == "test":
        session.validated_connection = None
        session.validation_id = ""
        candidate = _candidate(form)
        _test_connection(candidate[2].model_dump())
        if session.expired:
            raise ValueError(
                "This instance manager expired. Open it again from your agent."
            )
        session.validated_connection = _connection_identity(candidate)
        session.validation_id = secrets.token_urlsafe(24)
        return {"validation_id": session.validation_id}
    if action == "save":
        candidate = _candidate(form)
        if candidate[2].instance_type in SUPPORTED_DSS_INSTANCE_TYPES and (
            not session.validation_id
            or form.get("validation_id", [""])[0] != session.validation_id
            or session.validated_connection != _connection_identity(candidate)
        ):
            raise ValueError(
                "Test the connection successfully before saving. Test again after changing its connection settings."
            )
        original, existing, instance, name = candidate
        stdio.save_instance_profile(
            name,
            instance,
            original_name=original,
            expected_instance=existing,
            set_default="set_default" in form,
            activate="activate" in form,
        )
        session.validated_connection = None
        session.validation_id = ""
    elif action == "switch":
        state = _snapshot()
        selected = next((i for i in state["connections"] if i["name"] == name), None)
        if selected is None:
            raise ValueError("This instance no longer exists. Refresh the list.")
        if selected["source"] == "config":
            instance = stdio.get_profile_config().dss_instances[name].to_instance(name)
        else:
            instance = stdio.get_instances()[name]
        stdio.set_current_instance(instance)
    elif action == "default":
        stdio.set_default_instance(name)
    elif action == "delete":
        config = stdio.get_profile_config()
        current = stdio.get_current_instance()
        if name not in config.dss_instances:
            raise ValueError("This saved instance no longer exists. Refresh the list.")
        if form.get("revision", [""])[0] != _profile_revision(
            config.dss_instances[name]
        ):
            raise ValueError(
                "This instance changed. Reopen the manager before deleting."
            )
        needs_replacement = config.default_instance == name or (
            current and current.name == name
        )
        others = [
            i["name"]
            for i in _snapshot(config)["connections"]
            if i["source"] == "config" and i["name"] != name
        ]
        replacement = form.get("replacement", [""])[0] or None
        if needs_replacement and others and replacement not in others:
            raise ValueError("Choose another saved instance as the replacement.")
        stdio.delete_instance_from_config(
            name, replacement=replacement, expected_instance=config.dss_instances[name]
        )
    elif action != "done":
        raise ValueError("Unknown instance management action.")
    state = _snapshot()
    if action == "done":
        session.result = {
            "active_instance": state["active"],
            "connection_count": len(state["connections"]),
        }
        session.timer.cancel()
        session.validated_connection = None
        session.validation_id = ""
        session.completed.set()
    return {"state": state}


def _make_handler(token: str, expected_host: str, session_state: SetupSession | None):
    class SetupHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def _send(
            self,
            status: int,
            body: str,
            *,
            json_response: bool = False,
            nonce: str = "",
        ) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8"
                if json_response
                else "text/html; charset=utf-8",
            )
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                f"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'nonce-{nonce}'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.send_header("Referrer-Policy", "no-referrer")
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
            if (
                session_state is None
                or session_state.completed.is_set()
                or session_state.settings_path != stdio.get_settings_path()
            ):
                self._send(
                    410,
                    "This instance manager has closed. Open it again from your agent.",
                )
                return
            nonce = secrets.token_urlsafe(24)
            try:
                state = _snapshot()
            except (ValueError, RuntimeError, OSError):
                self._send(
                    500,
                    "Could not read the saved instances. Check your local profile file.",
                )
                return
            self._send(200, _page(state, nonce=nonce), nonce=nonce)

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
                if any(len(values) != 1 for values in form.values()):
                    raise ValueError("Duplicate form fields are not allowed.")
                if session_state is None:
                    raise ValueError("Open the instance manager again.")
                with session_state.lock:
                    result = _perform_action(session_state, form)
            except (UnicodeDecodeError, ValueError, RuntimeError) as error:
                # Validation errors are deliberately authored here. Never return raw
                # Pydantic/settings errors, which can contain profile or secret data.
                if type(error) is ValueError:
                    message = str(error)
                    if message.startswith("Invalid stdio settings"):
                        message = "Could not read the saved instances. Check your local profile file."
                else:
                    message = (
                        "Could not process this request. Reopen the instance manager."
                    )
                self._send(400, json.dumps({"error": message}), json_response=True)
                return
            except OSError:
                self._send(
                    500,
                    json.dumps(
                        {
                            "error": "Could not save the local profile file. Check its permissions and try again."
                        }
                    ),
                    json_response=True,
                )
                return
            self._send(200, json.dumps(result), json_response=True)
            if session_state.completed.is_set():
                threading.Thread(target=session_state.close, daemon=True).start()

    return SetupHandler


def start_setup_server(*, open_browser: bool = True) -> SetupSession:
    """Start a instance manager on a random loopback port and secret URL."""
    global _active_session
    with _session_lock:
        if _active_session:
            _active_session.close()
        token = secrets.token_urlsafe(24)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(token, "", None))
        host = f"127.0.0.1:{server.server_port}"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        completed = threading.Event()

        def expire() -> None:
            session.expired = True
            session.validated_connection = None
            session.validation_id = ""
            session.completed.set()
            server.shutdown()
            server.server_close()

        timer = threading.Timer(SESSION_LIFETIME_SECONDS, expire)
        timer.daemon = True
        session = SetupSession(
            f"http://{host}/{token}",
            server,
            thread,
            timer,
            False,
            completed,
            stdio.get_settings_path(),
        )
        server.RequestHandlerClass = _make_handler(token, host, session)
        thread.start()
        timer.start()
        session.browser_opened = (
            webbrowser.open(session.url, new=2) if open_browser else False
        )
        _active_session = session
        return session
