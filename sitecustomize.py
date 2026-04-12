"""Local interpreter bootstrap for repo-relative imports.

Python loads ``sitecustomize`` automatically when it is importable on startup.
This lets the repository support both ``Tools`` and ``tools`` import styles
without duplicating the package on a case-insensitive filesystem.
"""

from importlib import import_module
import sys


canonical_pkg = import_module("Tools")
sys.modules.setdefault("tools", canonical_pkg)

for module_name in getattr(canonical_pkg, "__all__", []):
    sys.modules.setdefault(f"tools.{module_name}", import_module(f"Tools.{module_name}"))
