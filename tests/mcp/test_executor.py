"""Tests for the dku_exec executor logic."""

from __future__ import annotations

import json
import os

from dku_cli.mcp import executor, policy
from dku_cli.mcp.audit import AuditLog
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
