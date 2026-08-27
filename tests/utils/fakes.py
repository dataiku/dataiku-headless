"""Shared fakes for tool unit tests.

Tool tests must run without a live Dataiku connection (same constraint as
``test_smoke.py``), so tests monkeypatch ``get_dss_client`` in the module under
test with a ``FakeDSSClient`` built here and drive the tool functions directly.
"""

import json


class FakeContext:
    """Stands in for the FastMCP ``Context`` argument of tool functions."""

    async def info(self, message: str) -> None:
        pass


class FakeProject:
    def __init__(self, variables: dict | None = None):
        self.variables = (
            variables if variables is not None else {"standard": {}, "local": {}}
        )
        self.set_calls: list[dict] = []

    def get_variables(self) -> dict:
        return json.loads(json.dumps(self.variables))

    def set_variables(self, obj: dict) -> None:
        self.set_calls.append(obj)
        self.variables = json.loads(json.dumps(obj))


class FakeDSSClient:
    def __init__(self, projects: dict[str, FakeProject] | None = None):
        self.projects = projects or {}

    def get_project(self, project_key: str) -> FakeProject:
        if project_key not in self.projects:
            raise KeyError(f"Unknown fake project: {project_key}")
        return self.projects[project_key]


def incrementing_monotonic(step=1000.0):
    """A ``time.monotonic()`` stand-in that jumps ``step`` seconds on every call.

    Every "remaining" check therefore lands well past the deadline computed on the
    preceding call, so any bounded wait loop times out on its first iteration —
    deterministic and with no real sleeping, regardless of call count.
    """
    state = {"t": 0.0}

    def _next():
        value = state["t"]
        state["t"] += step
        return value

    return _next
