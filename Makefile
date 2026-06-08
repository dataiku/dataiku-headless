.PHONY: help plugin desktop-bundle test-plugin clean-plugin clean-desktop

help:
	@echo "plugin          Build the local Claude/Codex plugin assets"
	@echo "desktop-bundle  Build the Claude Desktop .mcpb bundle"
	@echo "test-plugin     Run MCP/plugin packaging tests"
	@echo "clean-plugin    Remove generated plugin assets"
	@echo "clean-desktop   Remove generated Claude Desktop bundle assets"

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
