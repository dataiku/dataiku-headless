.PHONY: help plugin desktop-bundle test-plugin clean-plugin clean-desktop audit release

help:
	@echo "plugin          Build the local Claude/Codex plugin assets"
	@echo "desktop-bundle  Build the Claude Desktop .mcpb bundle"
	@echo "test-plugin     Run MCP/plugin packaging tests"
	@echo "clean-plugin    Remove generated plugin assets"
	@echo "clean-desktop   Remove generated Claude Desktop bundle assets"
	@echo "audit           Audit locked runtime dependencies (same gate as CI)"
	@echo "release         Bump version + changelog + tag via python-semantic-release (then push)"

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
	uvx --from python-semantic-release semantic-release --strict version
	uvx --from python-semantic-release semantic-release --strict changelog
	uvx --from python-semantic-release semantic-release --strict publish
