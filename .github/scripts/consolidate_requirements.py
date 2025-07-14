#!/usr/bin/env python3
"""
Generate separate requirements.txt files for each profile in pyproject.toml.
This prevents dependency conflicts during WhiteSource scanning.
"""

import re
import sys
import os
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


def extract_dependencies_by_profile(pyproject_file):
    """Extract dependencies organized by profile."""
    with open(pyproject_file, "r", encoding="utf-8") as f:
        data = toml.load(f)

    profiles = {}

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

    # Main dependencies - always include these
    main_deps = []
    if "project" in data and "dependencies" in data["project"]:
        main_deps = data["project"]["dependencies"]

    # Always create a main requirements file
    profiles["main"] = main_deps.copy()

    # Optional dependencies (profiles) - skip dev-related profiles
    if "project" in data and "optional-dependencies" in data["project"]:
        for profile_name, deps in data["project"]["optional-dependencies"].items():
            # Skip development-related profiles
            if profile_name.lower() not in dev_profile_names:
                # Each profile gets main dependencies + its specific dependencies
                profiles[profile_name] = main_deps + deps
            else:
                print(f"⏭️  Skipping dev profile: {profile_name}")

    return profiles


def consolidate_profile_requirements(deps):
    """Consolidate requirements for a single profile, removing duplicates."""
    # Parse all dependencies
    parsed_deps = {}
    original_deps = {}

    for dep in deps:
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
                    "original": dep,
                }
            )
            original_deps[pkg_name].append(dep)
        except Exception as e:
            print(f"⚠️  Could not parse dependency '{dep}': {e}")

    # Consolidate each package within this profile
    consolidated = {}
    for pkg_name, versions in parsed_deps.items():
        if len(versions) == 1:
            # Only one version, use it as-is
            consolidated[pkg_name] = versions[0]["original"]
        else:
            # Multiple versions, find the highest exact version
            exact_versions = []
            for v in versions:
                if v["operator"] == "==" and v["version"]:
                    try:
                        exact_versions.append(
                            (version.parse(v["version"]), v["original"])
                        )
                    except Exception:
                        # If version parsing fails, skip this version
                        pass

            if exact_versions:
                # Use the highest exact version
                consolidated[pkg_name] = max(exact_versions, key=lambda x: x[0])[1]
            else:
                # No exact versions, use the first one
                consolidated[pkg_name] = versions[0]["original"]

    return consolidated


def write_requirements_files(profiles, output_dir):
    """Write separate requirements files for each profile."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    files_created = []

    for profile_name, deps in profiles.items():
        consolidated = consolidate_profile_requirements(deps)

        # Create filename
        if profile_name == "main":
            filename = "requirements.txt"
        else:
            filename = f"requirements-{profile_name}.txt"

        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            for pkg_name in sorted(consolidated.keys()):
                f.write(f"{consolidated[pkg_name]}\n")

        files_created.append(filepath)
        print(f"✅ Created {filepath} with {len(consolidated)} packages")

    return files_created


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python consolidate_requirements.py <pyproject_file> [output_dir]")
        sys.exit(1)

    pyproject_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    try:
        print(f"📦 Extracting dependencies from {pyproject_file}...")
        profiles = extract_dependencies_by_profile(pyproject_file)
        print(f"📦 Found {len(profiles)} profiles:")
        for profile_name, deps in profiles.items():
            print(f"   - {profile_name}: {len(deps)} dependencies")

        print(f"🔧 Generating requirements files in {output_dir}...")
        files_created = write_requirements_files(profiles, output_dir)

        print(f"✅ Successfully generated {len(files_created)} requirements files:")
        for file_path in files_created:
            print(f"   - {file_path}")

        # Write a list of all requirements files for WhiteSource scanning
        files_list_path = os.path.join(output_dir, "requirements-files.txt")
        with open(files_list_path, "w", encoding="utf-8") as f:
            for file_path in files_created:
                f.write(f"{os.path.basename(file_path)}\n")

        print(f"📝 Created file list: {files_list_path}")
        return 0

    except Exception as e:
        print(f"❌ Error generating requirements: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
