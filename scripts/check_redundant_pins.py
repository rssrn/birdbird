#!/usr/bin/env python3
"""
Check whether CVE-motivated minimum-version pins in pyproject.toml are still necessary.

For each dependency annotated with a CVE comment, inspects the installed metadata of all
other direct dependencies to see whether they collectively mandate >= the pinned version.
If every direct dep that pulls in the package already requires at least our minimum, our
pin adds no constraint and can safely be removed.

Usage:
    python scripts/check_redundant_pins.py

Exit codes:
    0  all pins still add a constraint (or no CVE pins found)
    1  one or more pins are redundant

Note: direct deps must be installed (--no-deps is fine) before running this script so
their package metadata is available via importlib.metadata.

# @author Claude Sonnet 4.6 Anthropic
"""

import importlib.metadata
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


@dataclass
class CvePin:
    package: str  # normalised package name
    min_version: Version
    comment: str  # original comment line (for display)


def normalise(name: str) -> str:
    """Normalise a package name per PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_cve_pins(text: str) -> list[CvePin]:
    """Find dependencies immediately preceded by a line containing 'CVE-'."""
    pins: list[CvePin] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("#") or "CVE-" not in stripped:
            continue
        # Look ahead up to 2 lines for the pinned requirement
        for j in range(i + 1, min(i + 3, len(lines))):
            m = re.search(r'"([A-Za-z0-9_.+-]+)>=([\d.]+)"', lines[j])
            if m:
                pins.append(
                    CvePin(
                        package=normalise(m.group(1)),
                        min_version=Version(m.group(2)),
                        comment=stripped,
                    )
                )
                break
    return pins


def parse_direct_deps(text: str) -> list[str]:
    """Extract normalised package names from [project] dependencies."""
    m = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not m:
        return []
    names: list[str] = []
    for req_str in re.findall(r'"([^"]+)"', m.group(1)):
        try:
            names.append(normalise(Requirement(req_str).name))
        except Exception:
            pass
    return names


def min_lower_bound(requires_dist: list[str], target: str) -> Version | None:
    """
    Return the lowest >= / ~= / == bound that a package places on `target`,
    or None if it doesn't require `target` at all.
    """
    lowest: Version | None = None
    for req_str in requires_dist:
        try:
            req = Requirement(req_str)
        except Exception:
            continue
        if normalise(req.name) != target:
            continue
        for spec in req.specifier:
            if spec.operator in (">=", "~=", "=="):
                v = Version(spec.version)
                if lowest is None or v < lowest:
                    lowest = v
    return lowest


def check_pin(pin: CvePin, direct_deps: list[str]) -> tuple[bool, dict[str, Version | None]]:
    """
    Return (is_redundant, requirers) where requirers maps dep name -> its lower bound.
    is_redundant is True when every requirer already mandates >= pin.min_version.
    """
    requirers: dict[str, Version | None] = {}
    for dep in direct_deps:
        if dep == pin.package:
            continue
        try:
            requires = importlib.metadata.requires(dep) or []
        except importlib.metadata.PackageNotFoundError:
            continue
        bound = min_lower_bound(requires, pin.package)
        if bound is not None:
            requirers[dep] = bound

    if not requirers:
        return False, requirers

    redundant = all(bound is not None and bound >= pin.min_version for bound in requirers.values())
    return redundant, requirers


def main() -> int:
    text = PYPROJECT.read_text()
    pins = parse_cve_pins(text)
    direct_deps = parse_direct_deps(text)

    if not pins:
        print("No CVE-annotated pins found in pyproject.toml.")
        return 0

    print(f"Checking {len(pins)} CVE pin(s) against {len(direct_deps)} direct dep(s)...\n")

    any_redundant = False

    for pin in pins:
        is_redundant, requirers = check_pin(pin, direct_deps)
        status = "REDUNDANT - can be removed" if is_redundant else "still needed"
        print(f"  {pin.package}>={pin.min_version}  [{status}]")
        print(f"    CVE     : {pin.comment}")
        if requirers:
            for dep, bound in sorted(requirers.items()):
                marker = " ✓" if bound is not None and bound >= pin.min_version else " ✗"
                print(f"    Required by: {dep}>={bound}{marker}")
        else:
            print("    Required by: (no installed direct dep requires this package — pin may be vestigial)")
        print()
        if is_redundant:
            any_redundant = True

    if any_redundant:
        print("ACTION REQUIRED: one or more pins in pyproject.toml are now redundant.")
        print("Remove the pinned entry and its CVE comment, then verify with pip-audit.")
        return 1

    print("All pins still add a constraint. Nothing to remove.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
