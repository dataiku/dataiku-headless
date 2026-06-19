.PHONY: help plugin desktop-bundle test-plugin clean-plugin clean-desktop release

help:
	@echo "plugin          Build the local Claude/Codex plugin assets"
	@echo "desktop-bundle  Build the Claude Desktop .mcpb bundle"
	@echo "test-plugin     Run MCP/plugin packaging tests"
	@echo "clean-plugin    Remove generated plugin assets"
	@echo "clean-desktop   Remove generated Claude Desktop bundle assets"
	@echo "release         Bump version + changelog + tag via commitizen (then 'git push --follow-tags')"

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

# Cut a release locally with commitizen: bumps the version (src/dku_cli/__init__.py
# + pyproject [tool.commitizen]), updates CHANGELOG.md, commits, and creates the
# matching `vX.Y.Z` git tag — all from the conventional-commit history.
#
# Release flow:
#   1. make release                # bump version, update changelog, commit, tag
#   2. git push --follow-tags      # push the commit AND the tag
#   3. pushing the `v*` tag triggers .github/workflows/release.yml
#      (build + GitHub Release). PyPI publish stays a separate manual dispatch.
release:
	uvx --from commitizen cz bump
