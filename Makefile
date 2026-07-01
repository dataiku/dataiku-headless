.PHONY: help plugin desktop-bundle test-plugin clean-plugin clean-desktop audit release release-preview release-pr

help:
	@echo "plugin          Build the local Claude/Codex plugin assets"
	@echo "desktop-bundle  Build the Claude Desktop .mcpb bundle"
	@echo "test-plugin     Run MCP/plugin packaging tests"
	@echo "clean-plugin    Remove generated plugin assets"
	@echo "clean-desktop   Remove generated Claude Desktop bundle assets"
	@echo "audit           Audit locked runtime dependencies (same gate as CI)"
	@echo "release         Prepare a release commit for a PR (no tag, no push)"
	@echo "release-preview Prepare a local-only release commit preview"
	@echo "release-pr      Prepare, push, and open the release PR"

audit:
	uv export --locked --no-emit-project --no-dev --output-file requirements-audit.txt
	uvx pip-audit --strict --no-deps --disable-pip --requirement requirements-audit.txt

plugin:
	$(MAKE) -C dataiku-mcp bundle

desktop-bundle:
	$(MAKE) -C dataiku-mcp-bundle build

test-plugin:
	uv run pytest tests/mcp/test_cli.py tests/mcp/test_http.py tests/mcp/test_server_integration.py tests/plugin/test_dataiku_mcp_plugin.py -q

clean-plugin:
	$(MAKE) -C dataiku-mcp clean

clean-desktop:
	$(MAKE) -C dataiku-mcp-bundle clean

release:
	@version="$$(uv run python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')" && \
	git fetch --tags origin && \
	git rev-parse -q --verify "refs/tags/v$$version" >/dev/null || { \
		echo "missing baseline tag v$$version; create it before preparing the next release" >&2; \
		exit 1; \
	}
	uvx --from python-semantic-release semantic-release --strict version --no-tag --no-push --no-vcs-release

release-pr:
	@command -v gh >/dev/null || { echo "gh is required to open the release PR" >&2; exit 1; }
	@test -z "$$(git status --porcelain)" || { echo "working tree must be clean before release-pr" >&2; exit 1; }
	git fetch origin main --tags
	git checkout main
	git pull --ff-only origin main
	@version="$$(uv run python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')" && \
	git rev-parse -q --verify "refs/tags/v$$version" >/dev/null || { \
		echo "missing baseline tag v$$version; create it before preparing the next release" >&2; \
		exit 1; \
	}
	@next_version="$$(uvx --from python-semantic-release semantic-release --strict version --print | tail -n 1)" && \
		test -n "$$next_version" && \
		branch="release/v$$next_version" && \
		git checkout -B "$$branch" && \
		git push -u origin "$$branch" && \
		make release && \
		git push && \
		gh pr create \
		--base main \
		--head "$$branch" \
		--title "chore(release): $$next_version" \
		--body "Release $$next_version."

release-preview:
	@test -z "$$(git status --porcelain)" || { echo "working tree must be clean before release-preview" >&2; exit 1; }
	git fetch origin main --tags
	git checkout main
	git pull --ff-only origin main
	@version="$$(uv run python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')" && \
	git rev-parse -q --verify "refs/tags/v$$version" >/dev/null || { \
		echo "missing baseline tag v$$version; create it before preparing the next release" >&2; \
		exit 1; \
	}
	@next_version="$$(uvx --from python-semantic-release semantic-release --strict version --print | tail -n 1)" && \
		test -n "$$next_version" && \
		branch="release/v$$next_version-preview" && \
		git checkout -B "$$branch" && \
		uvx --from python-semantic-release semantic-release version --no-tag --no-push --no-vcs-release && \
		git --no-pager show --stat --oneline HEAD && \
		echo "Preview branch $$branch is local only. Delete it with: git checkout main && git branch -D $$branch"
