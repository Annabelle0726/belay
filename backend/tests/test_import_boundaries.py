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

3. The Apache-2.0 CONTRACT (core/domain/) is the base of the dependency graph: it
   imports nothing app-internal — only stdlib + typing + its own intra-contract
   modules. This keeps core/domain a single-license (Apache) surface; the registry
   that SELECTS and loads implementations lives in core/registry (AGPL). The arrow
   is impl -> contract, never the reverse. See LICENSING.md.
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


# ── boundary 3: the Apache contract imports nothing app-internal ──────────────

_CONTRACT_PKG = ("app", "core", "domain")  # the single-license (Apache) surface


def _package_of(path):
    """Dotted package of the MODULE at `path`, rooted at `app` (e.g.
    app/core/domain/pack.py -> ('app','core','domain'))."""
    rel = os.path.relpath(path, os.path.dirname(_APP))  # rel to backend/
    parts = rel[:-3].split(os.sep) if rel.endswith(".py") else rel.split(os.sep)
    return tuple(parts[:-1])  # drop the module filename -> its containing package


def _resolved_targets(path):
    """Yield each module-level import as an absolute dotted name, resolving relative
    imports against the file's package (so `from .types` in core/domain/pack.py
    resolves to app.core.domain.types, and `from ..registry` to app.core.registry)."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    pkg = _package_of(path)
    for node in tree.body:  # top-level only
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative: drop (level-1) trailing pkg components, then append
                base = pkg[: len(pkg) - (node.level - 1)]
                yield ".".join((*base, node.module)) if node.module else ".".join(base)
            elif node.module:
                yield node.module


def test_contract_imports_nothing_app_internal():
    """core/domain is the Apache contract: every module-level import must be stdlib /
    third-party / intra-contract. An import that resolves into `app.*` but OUTSIDE
    `app.core.domain` (e.g. app.core.registry, app.packs.*, app.agent.*) means an
    implementation leaked into the contract — the wrong dependency direction."""
    prefix = ".".join(_CONTRACT_PKG)
    offenders = []
    for path in _py_files(os.path.join("core", "domain")):
        for target in _resolved_targets(path):
            if target.split(".")[0] == "app" and not (
                target == prefix or target.startswith(prefix + ".")
            ):
                offenders.append((os.path.relpath(path, _APP), target))
    assert (
        not offenders
    ), f"the Apache contract (core/domain) imports app implementations: {offenders}"
