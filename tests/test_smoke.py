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

"""Smoke tests: the package imports cleanly and exposes its public surface.

These intentionally avoid any live Dataiku connection — importing the
package must work without credentials (the configuration package defaults every setting to
an empty value), so CI can run them on a bare runner.
"""

import importlib.metadata
import subprocess
import sys

import dataiku_mcp


def test_public_api():
    assert dataiku_mcp.__all__ == ["mcp", "run_stdio_server", "run_http_server"]
    assert callable(dataiku_mcp.run_stdio_server)
    assert callable(dataiku_mcp.run_http_server)


def test_mcp_server_initialized():
    assert dataiku_mcp.mcp.name == "Dataiku"


def test_distribution_version_is_resolvable():
    # The version is the commitizen / PEP 621 source of truth in pyproject.toml
    # and what the bump workflow keeps in lockstep with the plugin manifests.
    version = importlib.metadata.version("dataiku-headless")
    assert version and version[0].isdigit()


def test_package_import_does_not_read_stdio_config():
    code = """
import dotenv

def fail_if_called(*args, **kwargs):
    raise AssertionError("Package import must not load .env")

dotenv.load_dotenv = fail_if_called

import dataiku_mcp
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
