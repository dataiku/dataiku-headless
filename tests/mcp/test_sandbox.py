"""Tests for the executor sandbox backends."""

from __future__ import annotations

from dku_cli.mcp import sandbox


def test_probe_bubblewrap_returns_bool():
    # Must never raise, regardless of platform.
    assert isinstance(sandbox.probe_bubblewrap(), bool)


def test_subprocess_backend_runs(tmp_path):
    backend = sandbox.SubprocessBackend()
    result = backend.run(
        "echo hello", cwd=str(tmp_path), env={"PATH": "/usr/bin:/bin"}, timeout=10
    )
    assert result.exit_code == 0
    assert "hello" in result.stdout


def test_subprocess_backend_nonzero_exit(tmp_path):
    backend = sandbox.SubprocessBackend()
    result = backend.run(
        "exit 3", cwd=str(tmp_path), env={"PATH": "/usr/bin:/bin"}, timeout=10
    )
    assert result.exit_code == 3


def test_subprocess_backend_timeout(tmp_path):
    backend = sandbox.SubprocessBackend()
    result = backend.run(
        "sleep 5", cwd=str(tmp_path), env={"PATH": "/usr/bin:/bin"}, timeout=1
    )
    assert result.exit_code == 124
    assert "timed out" in result.stderr


def test_subprocess_backend_timeout_returns_partial_text(tmp_path):
    # TimeoutExpired carries partial stdout as BYTES even with text=True; the
    # backend must decode them to str so json.dumps downstream never crashes.
    backend = sandbox.SubprocessBackend()
    result = backend.run(
        "echo before; sleep 3",
        cwd=str(tmp_path),
        env={"PATH": "/usr/bin:/bin"},
        timeout=1,
    )
    assert result.exit_code == 124
    assert isinstance(result.stdout, str)
    assert isinstance(result.stderr, str)
    assert "before" in result.stdout
    assert "timed out" in result.stderr


def test_decode_partial_handles_bytes_and_str():
    assert sandbox._decode_partial(b"hello") == "hello"
    assert sandbox._decode_partial("hello") == "hello"
    assert sandbox._decode_partial(None) == ""
    # invalid utf-8 is replaced, not raised, and the result is always a str
    decoded = sandbox._decode_partial(b"\xff\xfeok")
    assert isinstance(decoded, str)
    assert "ok" in decoded


def test_select_backend_subprocess_forced():
    backend = sandbox.select_backend("subprocess")
    assert backend.name == "subprocess"


def test_select_backend_auto_returns_runnable():
    backend = sandbox.select_backend("auto")
    assert hasattr(backend, "run")
    assert backend.name in ("bubblewrap", "subprocess")


def test_bubblewrap_backend_does_not_mount_host_root(tmp_path):
    backend = sandbox.BubblewrapBackend()
    args = backend._wrap(str(tmp_path))
    ro_binds = list(zip(args, args[1:], args[2:]))

    assert ("--ro-bind", "/", "/") not in ro_binds
    if "/etc/ssl" in args or "/etc/resolv.conf" in args:
        assert ("--dir", "/etc") in list(zip(args, args[1:]))
    assert str(tmp_path) in args
    assert "/tmp" in args  # fresh tmpfs, not host /tmp
