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

"""Exercise application TLS activation in fresh processes, without patching pytest."""

import os
import subprocess
import sys
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _run(code, *args, env=None):
    result = subprocess.run(
        [sys.executable, "-c", code, *map(str, args)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("transport", ["stdio", "http"])
def test_launcher_activates_system_trust_before_server_import(transport):
    _run(
        """
import runpy
import ssl
import sys
import types
import truststore

assert ssl.SSLContext is not truststore.SSLContext
calls = []

class Server(types.ModuleType):
    def __getattr__(self, name):
        assert ssl.SSLContext is truststore.SSLContext
        if name not in ("run_http_server", "run_stdio_server"):
            raise AttributeError(name)
        return lambda path: calls.append((name, path))

sys.modules["dataiku_mcp"] = Server("dataiku_mcp")
transport = sys.argv[1]
sys.argv = ["runtime/run_mcp.py", "--transport", transport]
runpy.run_path("runtime/run_mcp.py", run_name="__main__")
assert calls == [("run_" + transport + "_server", None)]
""",
        transport,
    )


def test_package_import_does_not_patch_ssl():
    _run(
        """
import ssl
original_context = ssl.SSLContext
import dataiku_mcp
assert ssl.SSLContext is original_context
"""
    )


@pytest.mark.parametrize("entry", ["setup", "client"])
@pytest.mark.parametrize(
    "mode", ["trusted", "system_trusted", "untrusted", "wrong_hostname", "disabled"]
)
def test_injected_trust_preserves_https_verification(
    localhost_certificate, entry, mode
):
    if mode == "system_trusted" and sys.platform != "linux":
        pytest.skip("Isolated system CA file uses the Linux/OpenSSL backend")
    _, cert_path, key_path = localhost_certificate

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_path), str(key_path))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {
        key: value
        for key, value in os.environ.items()
        if key.lower()
        not in {
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "requests_ca_bundle",
            "curl_ca_bundle",
            "ssl_cert_file",
            "ssl_cert_dir",
        }
    }
    if mode in ("trusted", "wrong_hostname"):
        env["REQUESTS_CA_BUNDLE"] = str(cert_path)
    if mode == "system_trusted":
        env["SSL_CERT_FILE"] = str(cert_path)
    hostname = "127.0.0.1" if mode == "wrong_hostname" else "localhost"
    try:
        _run(
            """
import sys
import truststore
truststore.inject_into_ssl()

import requests
from dataiku_mcp import auth, setup_server
from dataiku_mcp.config import request
from dataiku_mcp.config.models import DSSInstance

url, entry, mode = sys.argv[1:]
instance = DSSInstance(
    name="test", url=url, api_key="test-key", source="config",
    instance_type="design", no_check_certificate=mode == "disabled",
)
request.get_pinned_instance = lambda: instance
request.is_http_request = lambda: False
try:
    if entry == "setup":
        setup_server._test_connection({
            "url": url, "api_key": "test-key", "api_ticket": None,
            "instance_type": "design",
            "no_check_certificate": mode == "disabled",
        })
    else:
        with auth.get_dss_client()._session as session:
            session.get(url, timeout=3).raise_for_status()
except (requests.exceptions.SSLError, ValueError) as exc:
    assert mode in ("untrusted", "wrong_hostname"), repr(exc)
else:
    assert mode in ("trusted", "system_trusted", "disabled"), "Invalid certificate was accepted"
""",
            f"https://{hostname}:{server.server_port}",
            entry,
            mode,
            env=env,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
