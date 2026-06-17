"""
Import-boundary tripwires.

1. The framework core (core/, agent/, analysis/, store/) AND the host integrations
   (integrations/, e.g. the Apache-2.0 Quad sidecar) must not import a concrete
   pack at module load — the dependency arrow points packs -> core, and an
   integration is license-clean only if it imports core, never packs. The
   registry's pack imports are deliberately function-local (lazy) and so are
   allowed; only MODULE-LEVEL imports are forbidden.

2. No Classiq dependency may creep into core or the packs (the quantum/Classiq
   code is removed in 1d; this tripwire keeps it from coming back).
"""

from __future__ import annotations

import ast
import os

_APP = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "app"))

# integrations/ must import core only (never packs) — same rule as core itself.
_CORE_DIRS = ["core", "agent", "analysis", "store", "integrations"]
_SCAN_DIRS = ["core", "agent", "analysis", "store", "packs", "integrations"]


def _py_files(*subdirs):
    for sub in subdirs:
        root = os.path.join(_APP, sub)
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f.endswith(".py"):
                    yield os.path.join(dirpath, f)


def _module_level_imports(path):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    mods = []
    for node in tree.body:  # top-level only — function-local imports excluded
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.append(node.module)
    return mods


def test_core_has_no_module_level_pack_imports():
    offenders = []
    for path in _py_files(*_CORE_DIRS):
        for mod in _module_level_imports(path):
            if mod.split(".")[0] == "packs" or ".packs" in mod or mod.startswith("packs"):
                offenders.append((os.path.relpath(path, _APP), mod))
    assert not offenders, f"core modules import packs at module level: {offenders}"


def test_no_classiq_imports_in_core_or_packs():
    offenders = []
    for path in _py_files(*_SCAN_DIRS):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if "classiq" in text.lower():
            offenders.append(os.path.relpath(path, _APP))
    assert not offenders, f"Classiq reference found in core/packs: {offenders}"


def test_core_does_not_import_quantum():
    """Quantum is a pack like any other; core must not import it at module level."""
    offenders = []
    for path in _py_files(*_CORE_DIRS):
        for mod in _module_level_imports(path):
            if mod.split(".")[0] == "quantum" or ".quantum" in mod:
                offenders.append((os.path.relpath(path, _APP), mod))
    assert not offenders, f"core modules import quantum at module level: {offenders}"


def test_integrations_import_core_only():
    """The Quad sidecar (and any host integration) is Apache-2.0-clean: it imports
    framework CORE only, never a pack."""
    offenders = []
    for path in _py_files("integrations"):
        for mod in _module_level_imports(path):
            parts = mod.split(".")
            if "packs" in parts or "quantum" in parts:
                offenders.append((os.path.relpath(path, _APP), mod))
    assert not offenders, f"integration modules import a pack/quantum: {offenders}"
