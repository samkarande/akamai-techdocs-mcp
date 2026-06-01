"""Custom hatch build hook: bundle dist/index.sqlite into the wheel when present.

Replaces the previous static `[tool.hatch.build.targets.wheel.force-include]`
rule (which required the file to exist at build time and broke any
`uv tool install git+https://...` or `uvx --from git+...` invocation
on a user's machine).

With this hook:
- CI runs the crawler first, dist/index.sqlite exists, the file gets
  baked into the wheel — installs are offline-ready out of the box.
- Source installs on machines without the crawler artifact (`uv tool
  install git+...`, `uvx --from git+...`) build a wheel without the
  bundled index. The server's auto-updater fetches the latest index
  from GitHub Releases on first run.
"""

from __future__ import annotations

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

BUNDLED_PATH_IN_WHEEL = "akamai_techdocs_mcp/data/index.sqlite"


class BundleIndexHook(BuildHookInterface):
    PLUGIN_NAME = "bundle-index"

    def initialize(self, version: str, build_data: dict) -> None:
        index_path = Path(self.root) / "dist" / "index.sqlite"
        if not index_path.exists():
            self.app.display_info(
                "bundle-index hook: dist/index.sqlite not found — "
                "building wheel without bundled index "
                "(auto-updater will fetch from GitHub Releases on first run)"
            )
            return
        force_include = build_data.setdefault("force_include", {})
        force_include[str(index_path)] = BUNDLED_PATH_IN_WHEEL
        self.app.display_info(
            f"bundle-index hook: including {index_path} "
            f"({index_path.stat().st_size:,} bytes) at {BUNDLED_PATH_IN_WHEEL}"
        )
