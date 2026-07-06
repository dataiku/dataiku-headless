"""Tests for the dku_exec executor logic."""

from __future__ import annotations

import json
import os

from dku_cli.mcp import executor, policy
from dku_cli.mcp.audit import AuditLog, redact_secrets
from dku_cli.mcp.sandbox import SubprocessBackend
from dku_cli.mcp.sessions import SessionStore


def _session(tmp_path):
    return SessionStore(tmp_path).get_or_create("test")


def test_run_exec_echo(tmp_path):
    result = executor.run_exec(
        "echo hi",
        session=_session(tmp_path),
        backend=SubprocessBackend(),
        timeout=10,
    )
    assert result.exit_code == 0
    assert "hi" in result.stdout
    assert result.truncated is False
    assert result.duration_ms >= 0


def test_sanitize_drops_literal_dangerous_flag():
    # Accident prevention only — drops a literal --dangerous token. NOT a
    # security control (DKU_DANGEROUS=1 etc. are out of scope by design).
    assert "--dangerous" not in policy.sanitize(
        "dku project delete X --dangerous --yes"
    )
    # Does not strip lookalikes.
    assert "--dangerousness" in policy.sanitize("echo --dangerousness")


def test_run_exec_strips_dangerous_before_running(tmp_path):
    result = executor.run_exec(
        "echo keep --dangerous end",
        session=_session(tmp_path),
        backend=SubprocessBackend(),
        timeout=10,
    )
    assert "--dangerous" not in result.stdout
    assert "keep" in result.stdout and "end" in result.stdout


def test_run_exec_writes_audit(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    audit = AuditLog(audit_path)
    executor.run_exec(
        "echo audited",
        session=_session(tmp_path),
        backend=SubprocessBackend(),
        timeout=10,
        audit=audit,
    )
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["tool"] == "dku_exec"
    assert event["exit_code"] == 0
    assert event["backend"] == "subprocess"
    assert event["auth_mode"] == "none"  # no dss_auth passed
    assert "api_key" not in json.dumps(event)  # never log the credential


def test_audit_log_uses_private_permissions(tmp_path):
    audit_path = tmp_path / "audit" / "exec.jsonl"
    audit = AuditLog(audit_path)
    audit.record({"tool": "dku_exec"})

    if os.name == "posix":
        assert (audit_path.parent.stat().st_mode & 0o777) == 0o700
        assert (audit_path.stat().st_mode & 0o777) == 0o600


def test_audit_log_tightens_existing_file_permissions(tmp_path):
    audit_path = tmp_path / "audit" / "exec.jsonl"
    audit_path.parent.mkdir()
    audit_path.write_text("old\n", encoding="utf-8")
    if os.name == "posix":
        os.chmod(audit_path, 0o644)

    AuditLog(audit_path).record({"tool": "dku_exec"})

    if os.name == "posix":
        assert (audit_path.stat().st_mode & 0o777) == 0o600


def test_truncate_flags_oversized_output():
    small, flag = executor._truncate("x" * 10)
    assert flag is False and small == "x" * 10
    big, flag = executor._truncate("x" * (executor._MAX_OUTPUT + 100))
    assert flag is True
    assert "truncated" in big


class _FixedBackend:
    """Sandbox backend that returns pre-set stdout/stderr for output tests."""

    name = "fixed"

    def __init__(self, stdout: str, stderr: str, exit_code: int = 0):
        self._out = stdout
        self._err = stderr
        self._code = exit_code

    def run(self, script, *, cwd, env, timeout):
        from dku_cli.mcp.sandbox import RunResult

        return RunResult(exit_code=self._code, stdout=self._out, stderr=self._err)


def test_combined_output_respects_single_budget(tmp_path):
    # Both streams individually exceed the ceiling; combined must stay ~<= budget.
    big = "o" * (executor._MAX_OUTPUT * 2)
    err = "e" * (executor._MAX_OUTPUT * 2)
    result = executor.run_exec(
        "irrelevant",
        session=_session(tmp_path),
        backend=_FixedBackend(big, err),
        timeout=10,
    )
    marker_slack = 256  # room for the two "[...truncated N chars]" markers
    assert (
        len(result.stdout) + len(result.stderr) <= executor._MAX_OUTPUT + marker_slack
    )
    assert result.truncated is True
    assert "truncated" in result.stdout
    # stdout gets the bulk of the budget, but stderr keeps its reserved floor —
    # a huge stdout must not squeeze the diagnostic down to a bare marker.
    assert len(result.stdout) >= executor._MAX_OUTPUT - executor._STDERR_FLOOR
    assert "eee" in result.stderr
    assert "truncated" in result.stderr


def test_stderr_floor_preserves_error_message_when_stdout_caps(tmp_path):
    """A command that dumps >100KB of data and then fails must still return its
    (short) stderr diagnostic intact — the exact prescriptive error the CLI
    works hard to produce."""
    big = "o" * (executor._MAX_OUTPUT * 2)
    diagnostic = "Error: dataset not found. Next: dku dataset list -P PROJ"
    result = executor.run_exec(
        "irrelevant",
        session=_session(tmp_path),
        backend=_FixedBackend(big, diagnostic, exit_code=1),
        timeout=10,
    )
    assert result.stderr == diagnostic
    assert result.exit_code == 1


def test_small_outputs_unchanged(tmp_path):
    result = executor.run_exec(
        "irrelevant",
        session=_session(tmp_path),
        backend=_FixedBackend("hello", "world"),
        timeout=10,
    )
    assert result.stdout == "hello"
    assert result.stderr == "world"
    assert result.truncated is False


def test_audit_redacts_secret_values(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    audit = AuditLog(audit_path)
    executor.run_exec(
        "dku auth login --token sk-abc123DEF_ghi --url https://dss",
        session=_session(tmp_path),
        backend=_FixedBackend("", ""),
        timeout=10,
        audit=audit,
    )
    event = json.loads(audit_path.read_text(encoding="utf-8").strip())
    logged = event["commands"]
    assert "sk-abc123DEF_ghi" not in logged
    assert "--token" in logged  # flag name kept
    assert "***" in logged
    assert "https://dss" in logged  # non-secret flag untouched


# --- secret redaction (audit log) -------------------------------------------


def test_redact_flag_space_forms():
    for flag in ("--password", "--pass", "--token", "--api-key", "--secret", "--key"):
        out = redact_secrets(f"cmd {flag} s3cr3tValue rest")
        assert "s3cr3tValue" not in out
        assert flag in out and "***" in out and "rest" in out


def test_redact_flag_equals_forms():
    out = redact_secrets("cmd --api-key=s3cr3tValue --other keep")
    assert "s3cr3tValue" not in out
    assert "--api-key=***" in out
    assert "keep" in out


def test_redact_short_flag_form():
    out = redact_secrets("cmd -key hunter2")
    assert "hunter2" not in out
    assert "***" in out


def test_redact_bearer_token():
    out = redact_secrets("curl -H 'Authorization: Bearer abc.DEF-123_ghi'")
    assert "abc.DEF-123_ghi" not in out
    assert "Bearer ***" in out


def test_redact_sk_key_anywhere():
    out = redact_secrets("export OPENAI=sk-abcDEF_012-xyz && run")
    assert "sk-abcDEF_012-xyz" not in out
    assert "***" in out and "run" in out


def test_redact_env_assignments():
    for name in ("API_KEY", "api-key", "TOKEN", "SECRET", "PASSWORD", "apikey"):
        out = redact_secrets(f"{name}=topsecret dku run")
        assert "topsecret" not in out
        assert f"{name}=***" in out


def test_redact_prefixed_env_assignments():
    """`\\b` fails on `_` (a word char), so DKU_API_KEY= — the product's own
    env var and the most likely secret shape in dku commands — leaked."""
    for name in ("DKU_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "MY_PASSWORD"):
        out = redact_secrets(f"{name}=topsecret dku dataset list")
        assert "topsecret" not in out
        assert f"{name}=***" in out


def test_redact_json_payload_fields():
    """JSON/heredoc payloads flow through dku_exec verbatim; secret-named
    string fields must mask even though there is no flag or `=` in sight."""
    for key in (
        "api_key",
        "apiKey",
        "token",
        "secret",
        "password",
        "authToken",
        "clientSecret",
        "DKU_API_KEY",
    ):
        out = redact_secrets(f'dku x --payload \'{{"{key}": "supersecret"}}\'')
        assert "supersecret" not in out
        assert key in out  # field name kept for the audit trail
        assert '"***"' in out


def test_redact_json_heredoc_multiline():
    cmd = (
        "dku connection create <<EOF\n"
        '{\n  "name": "pg",\n  "password": "hunter2",\n  "host": "db.internal"\n}\n'
        "EOF"
    )
    out = redact_secrets(cmd)
    assert "hunter2" not in out
    assert '"password": "***"' in out
    assert '"host": "db.internal"' in out


def test_redact_json_escaped_quotes_in_value():
    out = redact_secrets('{"api_key": "sup\\"er\\"secret"}')
    assert "secret" not in out
    assert '"api_key": "***"' in out


def test_redact_json_single_quoted_fields():
    out = redact_secrets("{'api_key': 'supersecret'}")
    assert "supersecret" not in out
    assert "'***'" in out


def test_redact_json_keeps_column_key_fields_visible():
    """Payload fields ending in Key are column references, not secrets —
    same false-positive class as --join-key on the flag side."""
    payload = (
        '{"projectKey": "MYPROJ", "joinKey": "customer_id", "partitionKey": "day"}'
    )
    assert redact_secrets(payload) == payload


def test_redact_json_keeps_nonstring_values():
    payload = '{"tokenBudget": 100, "maxTokens": true}'
    assert redact_secrets(payload) == payload


def test_redact_keeps_column_key_flags_visible():
    """Visual-recipe column flags end in `-key` but are NOT secrets; masking
    them destroys the audit trail for most recipe commands."""
    cmd = (
        "dku recipe join --join-key customer_id --project-key MYPROJ "
        "--group-key region --partition-key day --sort-key ts"
    )
    assert redact_secrets(cmd) == cmd


def test_redact_keeps_sk_substrings_in_ordinary_words():
    cmd = "pip install flask-cors task-runner"
    assert redact_secrets(cmd) == cmd


def test_redact_passthrough_no_secret():
    plain = "dku dataset list -P PROJ --format json | jq '.[].name'"
    assert redact_secrets(plain) == plain


def test_redact_does_not_mangle_ordinary_commands():
    # -P PROJ, --format, filenames, keys-as-jq-paths must survive untouched.
    cmd = "dku recipe run -P MYPROJ --format tsv > /tmp/out.tsv"
    assert redact_secrets(cmd) == cmd


def test_redact_empty_string():
    assert redact_secrets("") == ""


def test_build_env_sets_project_and_noninteractive(monkeypatch):
    monkeypatch.delenv("DKU_PROJECT", raising=False)
    env = executor.build_env(project="MYPROJ")
    assert env["DKU_PROJECT"] == "MYPROJ"
    assert env["NO_COLOR"] == "1"
    assert env["CI"] == "true"


def test_build_env_injects_dss_auth():
    env = executor.build_env(
        dss_auth={"url": "https://dss.example", "api_key": "KEY123"}
    )
    assert env["DKU_URL"] == "https://dss.example"
    assert env["DKU_API_KEY"] == "KEY123"


def test_build_env_scrubs_pod_secrets(monkeypatch):
    # Model A: secrets that live in a Code Studio pod must NOT reach the agent's
    # shell — only an allowlist of operational vars + the per-call DSS key do.
    monkeypatch.setenv("DKU_API_TICKET", "POD-TICKET")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("MY_DB_PASSWORD", "hunter2")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = executor.build_env()
    assert "DKU_API_TICKET" not in env
    assert "OPENAI_API_KEY" not in env
    assert "MY_DB_PASSWORD" not in env
    assert env["PATH"] == "/usr/bin:/bin"  # operational vars survive


def test_run_exec_injects_caller_key_and_scrubs_pod_ticket(tmp_path, monkeypatch):
    monkeypatch.setenv("DKU_API_TICKET", "POD-TICKET")  # the pod owner's secret
    result = executor.run_exec(
        "echo k=$DKU_API_KEY t=$DKU_API_TICKET",
        session=_session(tmp_path),
        backend=SubprocessBackend(),
        timeout=10,
        dss_auth={"api_key": "CALLER-KEY", "mode": "bearer"},
    )
    assert "k=CALLER-KEY" in result.stdout  # caller's own key is what dku sees
    assert "POD-TICKET" not in result.stdout  # pod ticket never exposed to shell


def test_run_exec_hosted_sets_home_to_session_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/home/host-user")
    session = _session(tmp_path)
    result = executor.run_exec(
        "printf '%s' \"$HOME\"",
        session=session,
        backend=SubprocessBackend(),
        timeout=10,
    )
    assert result.stdout == str(session.workdir)


def test_run_exec_hosted_preserves_injected_path(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/custom/bin:/usr/bin:/bin")
    session = _session(tmp_path)
    result = executor.run_exec(
        "printf '%s' \"$PATH\"",
        session=session,
        backend=SubprocessBackend(),
        timeout=10,
    )
    assert result.stdout == "/custom/bin:/usr/bin:/bin"


def test_run_exec_resource_limits_dont_break_commands(tmp_path):
    # The ulimit preamble must not break legitimate bash / python / loops.
    result = executor.run_exec(
        "echo ok; python3 -c 'print(1 + 1)'; for i in 1 2 3; do echo n$i; done",
        session=_session(tmp_path),
        backend=SubprocessBackend(),
        timeout=10,
    )
    assert result.exit_code == 0
    assert "ok" in result.stdout
    assert "2" in result.stdout
    assert "n3" in result.stdout


# --- trust modes: local (permissive) vs hosted (locked) ----------------------


def test_resource_limits_local_has_no_caps_hosted_is_generous():
    assert executor._resource_limits(10, mode="local") == ""
    hosted = executor._resource_limits(10, mode="hosted")
    assert "ulimit -u 16384" in hosted  # raised from 1024 — won't trip busy hosts
    assert "ulimit -u 1024" not in hosted


def test_build_env_local_inherits_full_environment(monkeypatch):
    # Local single-user mode gives the agent the user's real env (their tools,
    # cloud creds, venvs) — it already has all this via the harness's own shell.
    monkeypatch.setenv("MY_DB_PASSWORD", "hunter2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-local")
    env = executor.build_env(mode="local")
    assert env["MY_DB_PASSWORD"] == "hunter2"
    assert env["AWS_ACCESS_KEY_ID"] == "AKIA-local"
    # hosted mode still scrubs the same vars
    hosted = executor.build_env(mode="hosted")
    assert "MY_DB_PASSWORD" not in hosted


def test_run_exec_local_keeps_dangerous_flag(tmp_path):
    # Local mode does not sanitize — it's the user's own instance + supervision.
    result = executor.run_exec(
        "echo keep --dangerous end",
        session=_session(tmp_path),
        backend=SubprocessBackend(),
        mode="local",
        timeout=10,
    )
    assert "--dangerous" in result.stdout


def test_run_exec_local_runs_in_given_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("present", encoding="utf-8")
    result = executor.run_exec(
        "pwd && cat marker.txt",  # relative path resolves in the user's dir
        session=_session(tmp_path / "elsewhere"),  # NOT where the file is
        backend=SubprocessBackend(),
        mode="local",
        cwd=str(tmp_path),
        timeout=10,
    )
    assert result.exit_code == 0
    assert "present" in result.stdout


def test_result_to_text_plain_framing():
    """Tool replies are plain text — header, raw stdout, optional stderr section."""
    out = executor.result_to_text(
        executor.ExecResult(
            exit_code=0,
            stdout='line "one"\nline two\n',
            stderr="",
            duration_ms=5,
            truncated=False,
        )
    )
    assert out == 'exit 0\nline "one"\nline two'


def test_result_to_text_stderr_and_truncation():
    out = executor.result_to_text(
        executor.ExecResult(
            exit_code=1,
            stdout="partial",
            stderr="boom\n",
            duration_ms=5,
            truncated=True,
        )
    )
    assert out == "exit 1 (output truncated)\npartial\n--- stderr ---\nboom"


def test_result_to_text_empty_streams():
    out = executor.result_to_text(
        executor.ExecResult(
            exit_code=0, stdout="", stderr="", duration_ms=1, truncated=False
        )
    )
    assert out == "exit 0"
