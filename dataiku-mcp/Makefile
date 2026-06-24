REPO_ROOT := $(abspath ..)

.PHONY: help bundle clean

help:
	@echo "bundle         Build the Dataiku Headless wheel"
	@echo "clean          Remove vendored wheels"

bundle:
	cd $(REPO_ROOT) && uv run python scripts/sync_plugin_metadata.py
	@mkdir -p wheels
	@rm -f wheels/*.whl
	cd $(REPO_ROOT) && uv build --wheel -o dataiku-mcp/wheels
	@# keep only the newest wheel; drop uv's generated .gitignore
	@ls -t wheels/*.whl 2>/dev/null | tail -n +2 | xargs -r rm -f
	@rm -f wheels/.gitignore
	@echo "bundled $$(ls wheels/*.whl)"

clean:
	rm -rf wheels/*.whl wheels/.gitignore
