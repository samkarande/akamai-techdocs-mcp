"""Repo-level pytest config: make src/ importable in tests.

Python 3.13+ silently skips .pth files whose names start with `_`
(CVE-related security backport). Hatchling's editable installs use
`_editable_impl_<pkg>.pth`, so `import akamai_techdocs_mcp` fails in
the venv despite `uv pip list` reporting the package installed.

This conftest adds src/ to sys.path so tests work regardless of
editable-install state. Published wheels are unaffected — this is a
local-development workaround only.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent
SRC = REPO_ROOT / "src"
if SRC.is_dir():
    sys.path.insert(0, str(SRC))
