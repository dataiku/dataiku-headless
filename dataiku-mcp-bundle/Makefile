# Build the Claude Desktop one-click bundle (.mcpb) from the shared launcher +
# wheel in ../dataiku-mcp. Requires the mcpb CLI (via npx). The resulting
# dist/dataiku-mcp.mcpb is a release artifact (attach it to a GitHub release).
PLUGIN := $(abspath ../dataiku-mcp)
BUILD := build
DIST := dist

.PHONY: help build clean

help:
	@echo "build   Stage the bundle and pack dist/dataiku-mcp.mcpb (needs the mcpb CLI)"
	@echo "clean   Remove build/ and dist/"

build:
	cd .. && uv run python scripts/sync_plugin_metadata.py
	@command -v npx >/dev/null || { echo "node/npx required for the mcpb CLI"; exit 1; }
	@ls $(PLUGIN)/wheels/*.whl >/dev/null 2>&1 || \
	  { echo "no wheel in ../dataiku-mcp/wheels — run 'make bundle' there first"; exit 1; }
	rm -rf $(BUILD) $(DIST)
	mkdir -p $(BUILD)/bin $(BUILD)/wheels $(DIST)
	cp manifest.json $(BUILD)/manifest.json
	cp $(PLUGIN)/bin/dku-mcp-launch.sh $(BUILD)/bin/
	chmod +x $(BUILD)/bin/dku-mcp-launch.sh
	cp "$$(ls -t $(PLUGIN)/wheels/*.whl | head -1)" $(BUILD)/wheels/
	cd $(BUILD) && npx -y @anthropic-ai/mcpb pack . ../$(DIST)/dataiku-mcp.mcpb
	@echo "built $(DIST)/dataiku-mcp.mcpb"

clean:
	rm -rf $(BUILD) $(DIST)
