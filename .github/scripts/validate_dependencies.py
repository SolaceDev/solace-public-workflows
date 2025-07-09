#!/usr/bin/env python3
"""
Validate pyproject.toml for conflicting dependencies across profiles.
"""

import re
import sys
import argparse
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


def extract_dependencies(pyproject_file):
    """Extract all dependencies from pyproject.toml organized by profile."""
    with open(pyproject_file, "r", encoding="utf-8") as f:
        data = toml.load(f)

    all_deps = {}

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
        all_deps["main"] = data["project"]["dependencies"]

    # Optional dependencies (profiles) - skip dev-related profiles
    if "project" in data and "optional-dependencies" in data["project"]:
        for profile_name, deps in data["project"]["optional-dependencies"].items():
            # Skip development-related profiles
            if profile_name.lower() not in dev_profile_names:
                all_deps[profile_name] = deps
            else:
                print(f"⏭️  Skipping dev profile: {profile_name}")

    return all_deps


def find_conflicts(all_deps):
    """Find conflicting dependencies across profiles."""
    # Parse all dependencies
    parsed_deps = {}
    for profile, deps in all_deps.items():
        parsed_deps[profile] = []
        for dep in deps:
            try:
                pkg_name, operator, pkg_version, marker = parse_dependency(dep)
                parsed_deps[profile].append(
                    {
                        "original": dep,
                        "package": pkg_name,
                        "operator": operator,
                        "version": pkg_version,
                        "marker": marker,
                    }
                )
            except Exception as e:
                print(
                    f"⚠️  Could not parse dependency '{dep}' in profile '{profile}': {e}"
                )

    # Group by package name across all profiles
    package_map = defaultdict(list)
    for profile, deps in parsed_deps.items():
        for dep in deps:
            package_map[dep["package"]].append((profile, dep))

    # Find conflicts
    conflicts = []
    for pkg_name, occurrences in package_map.items():
        if len(occurrences) > 1:
            # Check if there are actual version conflicts
            versions = {}
            for profile, dep in occurrences:
                if dep["operator"] == "==" and dep["version"]:
                    if dep["version"] not in versions:
                        versions[dep["version"]] = []
                    versions[dep["version"]].append((profile, dep))

            # If we have multiple exact versions, it's a conflict
            if len(versions) > 1:
                conflicts.append(
                    {
                        "package": pkg_name,
                        "versions": versions,
                        "all_occurrences": occurrences,
                    }
                )
            # Also check for mixed operators (e.g., == vs >=)
            elif len(occurrences) > 1:
                operators = set()
                for profile, dep in occurrences:
                    if dep["operator"]:
                        operators.add(f"{dep['operator']}{dep['version']}")

                if len(operators) > 1:
                    # Potential conflict with different operators
                    exact_versions = [
                        (profile, dep)
                        for profile, dep in occurrences
                        if dep["operator"] == "=="
                    ]
                    if len(exact_versions) > 1:
                        version_set = set()
                        for profile, dep in exact_versions:
                            version_set.add(dep["version"])

                        if len(version_set) > 1:
                            conflicts.append(
                                {
                                    "package": pkg_name,
                                    "versions": {
                                        dep["version"]: [(profile, dep)]
                                        for profile, dep in exact_versions
                                    },
                                    "all_occurrences": occurrences,
                                }
                            )

    return conflicts


def format_conflict_report(conflicts):
    """Format conflicts into a readable report."""
    if not conflicts:
        return "✅ No dependency conflicts found!"

    report = []
    report.append("❌ Dependency conflicts detected:")
    report.append("")

    for i, conflict in enumerate(conflicts, 1):
        pkg_name = conflict["package"]
        report.append(f"{i}. Package: {pkg_name}")

        if "versions" in conflict and conflict["versions"]:
            for version_str, occurrences in conflict["versions"].items():
                profiles = [profile for profile, dep in occurrences]
                report.append(
                    f"   Version {version_str} found in profiles: {', '.join(profiles)}"
                )
                for profile, dep in occurrences:
                    report.append(f"     - {profile}: {dep['original']}")
        else:
            report.append("   Different version constraints:")
            for profile, dep in conflict["all_occurrences"]:
                report.append(f"     - {profile}: {dep['original']}")

        report.append("")

    report.append("💡 Resolution suggestions:")
    report.append("   1. Align versions across all profiles to use the same version")
    report.append(
        "   2. Remove duplicate dependencies if they're not needed in multiple profiles"
    )
    report.append(
        "   3. Use version ranges (>=, <) instead of exact pins where appropriate"
    )
    report.append("")

    return "\n".join(report)


def main():
    """Main validation function."""
    parser = argparse.ArgumentParser(
        description="Validate pyproject.toml for dependency conflicts"
    )
    parser.add_argument(
        "pyproject_file",
        default="pyproject.toml",
        nargs="?",
        help="Path to pyproject.toml file (default: pyproject.toml)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="dependency_conflicts.txt",
        help="Output conflicts report file (default: dependency_conflicts.txt)",
    )
    parser.add_argument(
        "--detailed",
        "-d",
        action="store_true",
        help="Include detailed analysis in output",
    )

    args = parser.parse_args()

    try:
        all_deps = extract_dependencies(args.pyproject_file)
        print(f"📦 Found {len(all_deps)} dependency profiles:")
        for profile in all_deps.keys():
            print(f"   - {profile} ({len(all_deps[profile])} dependencies)")
        print("")

        conflicts = find_conflicts(all_deps)
        report = format_conflict_report(conflicts)

        print(report)

        # Write detailed report to file
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)

            if args.detailed:
                f.write("\n\n" + "=" * 60 + "\n")
                f.write("DETAILED ANALYSIS\n")
                f.write("=" * 60 + "\n\n")

                for profile, deps in all_deps.items():
                    f.write(f"Profile: {profile}\n")
                    f.write("-" * (len(profile) + 9) + "\n")
                    for dep in deps:
                        f.write(f"  {dep}\n")
                    f.write("\n")

        print(f"📄 Report written to: {args.output}")

        return 1 if conflicts else 0

    except Exception as e:
        print(f"❌ Error validating dependencies: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
