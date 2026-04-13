"""Pytest bootstrap for repository-local imports."""

from importlib import import_module
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


canonical_pkg = import_module("Tools")
sys.modules.setdefault("tools", canonical_pkg)

for module_name in getattr(canonical_pkg, "__all__", []):
    sys.modules.setdefault(f"tools.{module_name}", import_module(f"Tools.{module_name}"))
