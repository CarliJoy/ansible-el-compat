# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "ansible-core==2.15.*",
# ]
# ///
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 Carli* Freudenberg <kound@posteo.de>
#
# Bundles ansible-core 2.15.* — the last ansible-core release with full EL8
# support. Starting from ansible-core 2.17, the dnf module uses
# `from __future__ import annotations` which requires Python 3.10+ and breaks
# on the EL8 system Python (3.6/3.9) where python3-dnf lives.
#
# The bundled module code is unmodified. Original authors:
#   Copyright 2015 Cristian van Ee <cristian at cvee.org>
#   Copyright 2015 Igor Gnatenko <i.gnatenko.brain@gmail.com>
#   Copyright 2018 Adam Miller <admiller@redhat.com>
# Source: https://github.com/ansible/ansible/blob/v2.15.0/lib/ansible/modules/dnf.py
"""
build_dnf_bundle.py
===================
Builds a self-executing zip bundle of the ansible-core 2.15 dnf module
that runs under /usr/libexec/platform-python (the EL8 system Python with
python3-dnf available).

The resulting file is placed at:
  src/ansible_collections/carlijoy/compat/plugins/modules/dnf

It has a #!/usr/libexec/platform-python shebang and is executable, so
Ansible treats it as a binary module — copying and executing it directly
without wrapping it in an ansiballz. It therefore runs under the system
Python that has access to python3-dnf.

Usage
-----
    uv run build_scripts/build_dnf_bundle.py
"""

from __future__ import annotations

import ast
import importlib.util
import io
import stat
import sys
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SHEBANG = "#!/usr/libexec/platform-python\n"

REPO_ROOT = Path(__file__).parent.parent
OUTPUT_MODULE = REPO_ROOT / "src/ansible_collections/carlijoy/compat/plugins/modules/dnf"
MAIN_TEMPLATE = Path(__file__).parent / "main-template.py"


# ---------------------------------------------------------------------------
# Locate ansible installed by uv into this script's environment
# ---------------------------------------------------------------------------


def find_ansible_lib() -> Path:
    """Return the path to the ansible package in the current environment."""
    spec = importlib.util.find_spec("ansible")
    if spec is None or spec.origin is None:
        print("ERROR: ansible not found in current environment", file=sys.stderr)
        sys.exit(1)
    ansible_lib = Path(spec.origin).parent  # .../site-packages/ansible
    print(f"    ansible lib: {ansible_lib}")
    return ansible_lib


# ---------------------------------------------------------------------------
# Recursively collect all ansible.module_utils.* imports via AST
# ---------------------------------------------------------------------------


def _resolve_dotted(dotted: str, ansible_lib: Path) -> Path | None:
    """Return the Path for *dotted* module, or None if it cannot be resolved."""
    parts = dotted.split(".")
    candidate_file = ansible_lib.parent.joinpath(*parts).with_suffix(".py")
    candidate_pkg = ansible_lib.parent.joinpath(*parts, "__init__.py")
    if candidate_file.exists():
        return candidate_file
    if candidate_pkg.exists():
        return candidate_pkg
    return None


def _collect_one(
    dotted: str,
    ansible_lib: Path,
    seen: set[str],
    collected: dict[str, Path],
) -> None:
    """Resolve and recursively collect a single dotted module name."""
    if dotted in seen:
        return
    seen.add(dotted)
    resolved = _resolve_dotted(dotted, ansible_lib)
    if resolved is None:
        return
    collected[dotted] = resolved
    print(f"    + {dotted}")
    collect_module_utils_imports(resolved, ansible_lib, seen=seen, collected=collected)


def collect_module_utils_imports(
    source_file: Path,
    ansible_lib: Path,
    seen: set[str] | None = None,
    collected: dict[str, Path] | None = None,
) -> dict[str, Path]:
    """
    Parse *source_file* with ast, find all ``from ansible.module_utils.*``
    and ``import ansible.module_utils.*`` statements, resolve them to actual
    files inside *ansible_lib*, and recurse into each for transitive deps.

    Handles submodule imports of the form
    ``from ansible.module_utils.pkg import submod`` by also probing
    ``ansible.module_utils.pkg.submod`` as a candidate file.

    Returns a dict mapping dotted module name -> absolute Path.
    """
    if seen is None:
        seen = set()
    if collected is None:
        collected = {}

    tree = ast.parse(source_file.read_text())

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if not node.module or not node.module.startswith("ansible.module_utils"):
                continue
            _collect_one(node.module, ansible_lib, seen, collected)
            # Each imported name may be a submodule (e.g. `from pkg import submod`)
            for alias in node.names:
                if alias.name == "*":
                    continue
                _collect_one(f"{node.module}.{alias.name}", ansible_lib, seen, collected)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("ansible.module_utils"):
                    _collect_one(alias.name, ansible_lib, seen, collected)

    return collected


# ---------------------------------------------------------------------------
# Build the zip
# ---------------------------------------------------------------------------


def build_zip(
    dnf_module: Path,
    module_utils: dict[str, Path],
    ansible_lib: Path,
) -> bytes:
    """
    Assemble a zip containing:
      __main__.py                  — bootstrap entry point
      ansible/modules/dnf.py      — original dnf module
      ansible/module_utils/**     — all collected dependencies
      ansible/**/__init__.py      — package stubs
    """
    print("[3/4] Building zip ...")
    buf = io.BytesIO()
    added: set[str] = set()

    def write_file(zf: zipfile.ZipFile, arcname: str, path: Path) -> None:
        if arcname not in added:
            zf.write(path, arcname)
            added.add(arcname)

    def write_str(zf: zipfile.ZipFile, arcname: str, content: str) -> None:
        if arcname not in added:
            zf.writestr(arcname, content)
            added.add(arcname)

    def ensure_inits(zf: zipfile.ZipFile, dotted: str) -> None:
        parts = dotted.split(".")
        for i in range(1, len(parts)):
            arc = "/".join(parts[:i]) + "/__init__.py"
            if arc in added:
                continue
            real = ansible_lib.parent.joinpath(*parts[:i], "__init__.py")
            if real.exists():
                write_file(zf, arc, real)
            else:
                write_str(zf, arc, "")

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for stub in ("ansible/__init__.py", "ansible/modules/__init__.py"):
            write_str(zf, stub, "")

        write_file(zf, "ansible/modules/dnf.py", dnf_module)

        for dotted, path in module_utils.items():
            ensure_inits(zf, dotted)
            parts = dotted.split(".")
            arcname = (
                "/".join(parts) + "/__init__.py"
                if path.name == "__init__.py"
                else "/".join(parts) + ".py"
            )
            write_file(zf, arcname, path)

        write_str(zf, "__main__.py", MAIN_TEMPLATE.read_text())

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Write the executable bundle
# ---------------------------------------------------------------------------


def write_bundle(zip_bytes: bytes, output: Path) -> None:
    print(f"[4/4] Writing bundle to {output} ...")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as f:
        f.write(SHEBANG.encode())
        f.write(zip_bytes)
    output.chmod(output.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"    done — {output.stat().st_size // 1024} KB")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("[1/4] Locating ansible-core 2.15 ...")
    ansible_lib = find_ansible_lib()

    dnf_module = ansible_lib / "modules" / "dnf.py"
    if not dnf_module.exists():
        print(f"ERROR: dnf.py not found at {dnf_module}", file=sys.stderr)
        sys.exit(1)

    print("[2/4] Collecting module_utils imports ...")
    module_utils = collect_module_utils_imports(dnf_module, ansible_lib)
    print(f"    collected {len(module_utils)} module_utils files")

    zip_bytes = build_zip(dnf_module, module_utils, ansible_lib)
    write_bundle(zip_bytes, OUTPUT_MODULE)

    print(f"\nBuild complete: {OUTPUT_MODULE}")
    print("Use as       : carlijoy.compat.dnf")


if __name__ == "__main__":
    main()
