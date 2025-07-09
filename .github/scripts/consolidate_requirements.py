#!/usr/bin/env python3
"""
Consolidate requirements from pyproject.toml into a clean requirements.txt file.
"""

import re
import sys
from collections import defaultdict
from packaging import version
import toml


def parse_dependency(dep_string):
    """Parse a dependency string to extract package name, operator, and version."""
    # Handle platform/environment markers
    if ";" in dep_string:
        dep_part = dep_string.split(";")[0].strip()
        marker = dep_string.split(";")[1].strip()
    else:
        dep_part = dep_string.strip()
        marker = None

    # Match package name with version specifier
    match = re.match(r"^([a-zA-Z0-9_.-]+)(==|>=|<=|>|<|!=|~=)(.+)$", dep_part)
    if match:
        pkg_name, operator, pkg_version = match.groups()
        return (
            pkg_name.lower().replace("_", "-").replace(".", "-"),
            operator,
            pkg_version.strip(),
            marker,
        )
    else:
        # No version specified
        pkg_name = dep_part.lower().replace("_", "-").replace(".", "-")
        return pkg_name, None, None, marker


def extract_all_dependencies(pyproject_file):
    """Extract all dependencies from pyproject.toml."""
    with open(pyproject_file, "r", encoding="utf-8") as f:
        data = toml.load(f)

    all_deps = []

    # Define development-related profile names to skip
    dev_profile_names = {
        "dev",
        "development",
        "develop",
        "test",
        "testing",
        "tests",
        "lint",
        "linting",
        "format",
        "formatting",
        "docs",
        "documentation",
        "build",
        "ci",
        "cd",
        "debug",
        "local",
    }

    # Main dependencies
    if "project" in data and "dependencies" in data["project"]:
        all_deps.extend(data["project"]["dependencies"])

    # Optional dependencies (profiles) - skip dev-related profiles
    if "project" in data and "optional-dependencies" in data["project"]:
        for profile_name, deps in data["project"]["optional-dependencies"].items():
            # Skip development-related profiles
            if profile_name.lower() not in dev_profile_names:
                all_deps.extend(deps)
            else:
                print(f"⏭️  Skipping dev profile: {profile_name}")

    return all_deps


def consolidate_requirements(all_deps):
    """Consolidate requirements, removing duplicates and using highest versions."""
    # Parse all dependencies
    parsed_deps = {}
    original_deps = {}

    for dep in all_deps:
        try:
            pkg_name, operator, pkg_version, marker = parse_dependency(dep)

            if pkg_name not in parsed_deps:
                parsed_deps[pkg_name] = []
                original_deps[pkg_name] = []

            parsed_deps[pkg_name].append(
                {
                    "operator": operator,
                    "version": pkg_version,
                    "marker": marker,
                }
            )
            original_deps[pkg_name].append(dep)
        except Exception as e:
            print(f"⚠️  Could not parse dependency '{dep}': {e}")

    # Consolidate each package
    consolidated = {}
    for pkg_name, versions in parsed_deps.items():
        if len(versions) == 1:
            # Only one version, use it as-is
            consolidated[pkg_name] = original_deps[pkg_name][0]
        else:
            # Multiple versions, find the highest exact version
            exact_versions = []
            for i, v in enumerate(versions):
                if v["operator"] == "==" and v["version"]:
                    try:
                        exact_versions.append((version.parse(v["version"]), i))
                    except Exception:
                        # If version parsing fails, skip this version
                        pass

            if exact_versions:
                # Use the highest exact version
                highest_version_index = max(exact_versions, key=lambda x: x[0])[1]
                consolidated[pkg_name] = original_deps[pkg_name][highest_version_index]
            else:
                # No exact versions, use the first one
                consolidated[pkg_name] = original_deps[pkg_name][0]

    return consolidated


def write_requirements_file(consolidated_deps, output_file):
    """Write consolidated dependencies to requirements.txt."""
    with open(output_file, "w", encoding="utf-8") as f:
        for pkg_name in sorted(consolidated_deps.keys()):
            f.write(f"{consolidated_deps[pkg_name]}\n")


def main():
    """Main function."""
    if len(sys.argv) < 3:
        print(
            "Usage: python consolidate_requirements.py <pyproject_file> <output_file>"
        )
        sys.exit(1)

    pyproject_file = sys.argv[1]
    output_file = sys.argv[2]

    try:
        print(f"📦 Extracting dependencies from {pyproject_file}...")
        all_deps = extract_all_dependencies(pyproject_file)
        print(f"📦 Found {len(all_deps)} total dependencies")

        print("🔧 Consolidating requirements...")
        consolidated = consolidate_requirements(all_deps)
        print(f"✅ Consolidated to {len(consolidated)} unique packages")

        print(f"📄 Writing requirements to {output_file}...")
        write_requirements_file(consolidated, output_file)

        print(f"✅ Clean requirements.txt generated with {len(consolidated)} packages")
        return 0

    except Exception as e:
        print(f"❌ Error generating requirements: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
