"""soul.md stays gated on-demand — it must never become always-loaded.

The only judgment-layer guarantee worth pinning: the router points at ``soul.md``
for multi-stage work *and* tells the agent to skip it for one-shot work. If the
skip clause disappears, soul.md has silently become part of the always-on context
budget. This test deliberately does not police soul.md's wording or register.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "dataiku-skills" / "dataiku-headless"


def test_soul_file_exists():
    assert (SKILL_DIR / "soul.md").is_file()


def test_router_gates_soul_on_demand():
    router = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    # Referenced, so it is discoverable...
    assert "`soul.md`" in router
    # ...and explicitly skippable, so it is not always-loaded.
    assert "Skip it" in router
