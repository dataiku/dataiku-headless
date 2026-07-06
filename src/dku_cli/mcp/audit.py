"""Append-only JSONL audit log for the ``dku_exec`` tool.

One line per executor call, written to ``<state_root>/audit/exec.jsonl``.
Thread-safe so concurrent agent sessions don't interleave partial lines.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
from pathlib import Path

# Flag/value pairs whose value must be masked: --password secret / --token=abc.
_FLAG_NAMES = "password|pass|token|api-key|api_key|secret|key"
# --flag <value>  and  --flag=<value>  (also short-form single dash). The
# lookbehind keeps the bare `key` alternative from matching the tail of
# legitimate column flags (--join-key, --project-key, --partition-key, ...),
# which would blank the audit trail for most visual-recipe commands.
_FLAG_SPACE = re.compile(
    rf"(?<![\w-])(--?(?:{_FLAG_NAMES}))(\s+)(\S+)",
    re.IGNORECASE,
)
_FLAG_EQUALS = re.compile(
    rf"(?<![\w-])(--?(?:{_FLAG_NAMES}))(=)(\S+)",
    re.IGNORECASE,
)
# KEY=VALUE / env-var assignments. Secret-ish stems may be embedded anywhere in
# the variable name (DKU_API_KEY=, GITHUB_TOKEN=, AWS_SECRET_ACCESS_KEY=), so
# allow a prefix and suffix — `\b` alone fails on `_`, which is a word char.
_ASSIGN = re.compile(
    r"(?<![\w-])([\w-]*(?:api[_-]?key|token|secret|password)[\w-]*)(=)(\S+)",
    re.IGNORECASE,
)
# JSON / heredoc payload fields: "api_key": "supersecret". Same secret stems
# and prefix/suffix latitude as _ASSIGN ("apiKey", "clientSecret",
# "AUTH_TOKEN"), and same rationale for excluding bare `key`: payload fields
# like "projectKey" / "joinKey" are column references, not secrets. The value
# must be a string — quoted, with escapes allowed — so numeric/boolean config
# stays visible. Single-quoted variant covers hand-written heredocs.
_JSON_FIELD_DQ = re.compile(
    r'("[\w-]*(?:api[_-]?key|token|secret|password)[\w-]*"\s*:\s*)"(?:[^"\\]|\\.)*"',
    re.IGNORECASE,
)
_JSON_FIELD_SQ = re.compile(
    r"('[\w-]*(?:api[_-]?key|token|secret|password)[\w-]*'\s*:\s*)'(?:[^'\\]|\\.)*'",
    re.IGNORECASE,
)
# Bearer <token>.
_BEARER = re.compile(r"(Bearer)(\s+)(\S+)", re.IGNORECASE)
# OpenAI-style secret keys anywhere in the text; the boundary keeps ordinary
# words containing "sk-" (flask-cors, task-runner) intact.
_SK = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]+")

_MASK = "***"


def redact_secrets(text: str) -> str:
    """Mask secret values in a command string before it is persisted.

    Keeps the flag/key NAME so the audit trail stays useful, replaces the VALUE
    with ``***``. Ordinary commands (``dku dataset list -P PROJ``) pass through
    untouched.
    """
    if not text:
        return text
    text = _JSON_FIELD_DQ.sub(rf'\1"{_MASK}"', text)
    text = _JSON_FIELD_SQ.sub(rf"\1'{_MASK}'", text)
    text = _FLAG_EQUALS.sub(rf"\1\2{_MASK}", text)
    text = _FLAG_SPACE.sub(rf"\1\2{_MASK}", text)
    text = _ASSIGN.sub(rf"\1\2{_MASK}", text)
    text = _BEARER.sub(rf"\1\2{_MASK}", text)
    text = _SK.sub(_MASK, text)
    return text


class AuditLog:
    """Thread-safe JSONL appender."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _chmod(self.path.parent, 0o700)
        self._lock = threading.Lock()

    def record(self, event: dict) -> None:
        line = json.dumps(event, default=str)
        with self._lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            _chmod(self.path, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def _chmod(path: Path, mode: int) -> None:
    with contextlib.suppress(OSError):
        os.chmod(path, mode)
