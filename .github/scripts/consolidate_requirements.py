#!/usr/bin/env python3
"""
Consolidate requirements.txt by resolving conflicts and selecting highest versions.
"""

import re
import sys
import argparse
from collections import defaultdict
from packaging import version


def parse_requirements(file_path):
    """Parse requirements file and group by package name."""
    packages = defaultdict(list)

    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"❌ Requirements file not found: {file_path}")
        return {}

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Parse package name and version
        # Handle various formats: package==version, package>=version, etc.
        match = re.match(
            r"^([a-zA-Z0-9_.-]+)(==|>=|<=|>|<|!=|~=)(.+?)(?:\s*;.*)?$", line
        )
        if match:
            pkg_name, operator, pkg_version = match.groups()
            # Normalize package name (lowercase, replace underscores/hyphens)
            normalized_name = pkg_name.lower().replace("_", "-").replace(".", "-")
            packages[normalized_name].append(
                (line, pkg_name, operator, pkg_version, line_num)
            )
        else:
            # Handle packages without version constraints or with conditions
            if ";" in line:
                pkg_part = line.split(";")[0].strip()
            else:
                pkg_part = line

            if pkg_part:
                normalized_name = pkg_part.lower().replace("_", "-").replace(".", "-")
                packages[normalized_name].append((line, pkg_part, None, None, line_num))

    return packages


def resolve_conflicts(packages):
    """Resolve conflicts by selecting the latest version for each package."""
    resolved = []
    conflicts_found = []

    for pkg_name, versions in packages.items():
        if len(versions) == 1:
            # No conflict
            resolved.append(versions[0][0])
        else:
            # Multiple versions found - resolve conflict
            print(f"🔍 Resolving conflict for {pkg_name}:")
            for req_line, orig_name, op, ver, line_num in versions:
                print(f"  Line {line_num}: {req_line}")

            conflicts_found.append((pkg_name, versions))

            # Try to find the latest version with == operator
            exact_versions = [
                (req_line, orig_name, ver, line_num)
                for req_line, orig_name, op, ver, line_num in versions
                if op == "=="
            ]

            if exact_versions:
                # Sort by version and take the latest
                try:
                    latest = max(exact_versions, key=lambda x: version.parse(x[2]))
                    resolved.append(latest[0])
                    print(f"  ✅ Selected: {latest[0]} (highest version)")
                except Exception as e:
                    print(
                        f"  ⚠️  Error parsing versions, using first: {exact_versions[0][0]}"
                    )
                    resolved.append(exact_versions[0][0])
            else:
                # No exact versions, take the first one
                resolved.append(versions[0][0])
                print(f"  ⚠️  No exact versions found, using: {versions[0][0]}")

    return sorted(resolved), conflicts_found


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Consolidate requirements.txt by resolving conflicts"
    )
    parser.add_argument(
        "input_file",
        default="all_requirements_raw.txt",
        nargs="?",
        help="Input requirements file (default: all_requirements_raw.txt)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="requirements.txt",
        help="Output requirements file (default: requirements.txt)",
    )
    parser.add_argument(
        "--conflicts-output",
        default="requirements_conflicts.txt",
        help="Conflicts report file (default: requirements_conflicts.txt)",
    )

    args = parser.parse_args()

    print("🔄 Generating clean requirements.txt...")

    # Parse requirements
    packages = parse_requirements(args.input_file)
    if not packages:
        print("❌ No packages found!")
        return 1

    print(f"📦 Found {len(packages)} unique packages")

    # Resolve conflicts
    clean_requirements, conflicts = resolve_conflicts(packages)

    # Write clean requirements
    with open(args.output, "w") as f:
        for req in clean_requirements:
            f.write(req + "\n")

    print(f"✅ Generated {args.output} with {len(clean_requirements)} packages")

    if conflicts:
        print(f"⚠️  Resolved {len(conflicts)} package conflicts")
        with open(args.conflicts_output, "w") as f:
            f.write("# Package conflicts resolved:\n")
            for pkg_name, versions in conflicts:
                f.write(f"\n# {pkg_name}:\n")
                for req_line, orig_name, op, ver, line_num in versions:
                    f.write(f"#   Line {line_num}: {req_line}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
