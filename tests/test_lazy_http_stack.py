"""Guard the cold-import contract: `dku --help` must not load the HTTP stack.

Agents probe `dku <cmd> --help` constantly; importing dataikuapi/requests on
that path costs ~200ms per probe. The contract has already been broken twice
by module-level `from dataikuapi.utils import DataikuException` imports in
helper modules — this test makes the third time a CI failure instead of a
silent regression.
"""

from __future__ import annotations

import subprocess
import sys

FORBIDDEN_ROOTS = ("dataikuapi", "requests", "urllib3")

_PROBE = """
import sys
import dku_cli.main
loaded = sorted({m.split(".")[0] for m in sys.modules if m.split(".")[0] in %r})
print(",".join(loaded))
"""


def test_importing_main_does_not_load_http_stack():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE % (FORBIDDEN_ROOTS,)],
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = result.stdout.strip()
    assert loaded == "", (
        f"Importing dku_cli.main eagerly loaded {loaded}. Keep dataikuapi/"
        "requests imports inside function bodies (see client.py) so "
        "`dku --help` stays off the HTTP stack."
    )
