#!/usr/bin/env python3

import argparse
import json
import re
import sys
from os import getenv
from pathlib import Path
from github import Github


def load_version_config() -> dict:
    """Load configuration from .versionrc.json"""
    # Try GitHub Actions workspace first, then current directory
    workspace_path = Path("/github/workspace/.versionrc.json")
    local_path = Path(".versionrc.json")

    config_path = workspace_path if workspace_path.exists() else local_path

    if not config_path.exists():
        print("Warning: .versionrc.json not found, using default configuration")
        return {
            "types": [
                {"type": "feat", "section": "Features"},
                {"type": "fix", "section": "Bug Fixes"},
                {"type": "ci", "section": "Continuous Integration"},
                {"type": "deps", "section": "Dependencies"},
                {"type": "chore", "section": "Chores"},
                {"type": "build", "section": "Build"},
                {"type": "docs", "section": "Documentation"},
                {"type": "style", "section": "Style"},
                {"type": "refactor", "section": "Refactoring"},
                {"type": "perf", "section": "Performance"},
                {"type": "test", "section": "Tests"},
            ]
            # No default issuePrefixes or issueUrlFormat for security
        }

    try:
        with open(config_path) as f:
            config = json.load(f)

        # Ensure required fields exist
        if "types" not in config:
            config["types"] = [
                {"type": "feat", "section": "Features"},
                {"type": "fix", "section": "Bug Fixes"},
            ]

        # Don't add default issuePrefixes or issueUrlFormat for security
        # They should only be used if explicitly configured

        return config
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading .versionrc.json: {e}")
        sys.exit(1)


def get_commits_between_refs(from_ref: str, to_ref: str) -> list[dict[str, str]]:
    """Get commits between two git references using PyGithub GraphQL API"""
    github_token = getenv("GITHUB_TOKEN")
    github_repo = getenv("GITHUB_REPOSITORY")

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)

    if not github_repo:
        print("Error: GITHUB_REPOSITORY environment variable not set")
        sys.exit(1)

    try:
        g = Github(github_token)
        repo = g.get_repo(github_repo)

        # Get commit range
        if from_ref:
            # Get commits between two refs
            comparison = repo.compare(from_ref, to_ref)
            commits_data = comparison.commits
        else:
            # Get all commits up to to_ref
            commits_data = repo.get_commits(sha=to_ref)

        commits = []
        print(
            f"Processing {commits_data.totalCount if hasattr(commits_data, 'totalCount') else 'unknown number of'} commits..."
        )

        for commit in commits_data:
            # Get associated PRs for this commit using GraphQL
            pr_number = None
            try:
                # Use GraphQL to find PRs associated with this commit
                query = f"""
                {{
                  repository(owner: "{repo.owner.login}", name: "{repo.name}") {{
                    object(oid: "{commit.sha}") {{
                      ... on Commit {{
                        associatedPullRequests(first: 1) {{
                          nodes {{
                            number
                          }}
                        }}
                      }}
                    }}
                  }}
                }}
                """

                result = g._Github__requester.graphql_query(query)
                if result and "data" in result:
                    pr_nodes = result["data"]["repository"]["object"][
                        "associatedPullRequests"
                    ]["nodes"]
                    if pr_nodes:
                        pr_number = str(pr_nodes[0]["number"])
            except Exception:
                # If GraphQL fails, continue without PR number
                pass

            commits.append(
                {
                    "hash": commit.sha[:7],
                    "full_hash": commit.sha,
                    "subject": commit.commit.message.split("\n")[0],  # First line only
                    "author": commit.commit.author.name
                    if commit.commit.author
                    else "Unknown",
                    "pr_number": pr_number,
                }
            )

        return commits

    except Exception as e:
        print(f"Error: Failed to get commits using PyGithub: {e}")
        sys.exit(1)


def parse_commit_message(
    subject: str,
) -> tuple[str | None, str | None, str, str | None]:
    """Parse commit message and return (type, scope, clean_subject, pr_number)"""
    # Format 1: type(scope): subject (#PR)
    match1 = re.match(r"^(\w+)\(([^)]+)\): (.+?)(?:\s+\(#(\d+)\))?$", subject)
    if match1:
        return match1.group(1), match1.group(2), match1.group(3), match1.group(4)

    # Format 2: type: subject (#PR)
    match2 = re.match(r"^(\w+): (.+?)(?:\s+\(#(\d+)\))?$", subject)
    if match2:
        return match2.group(1), None, match2.group(2), match2.group(3)

    return None, None, subject, None


def extract_issue_numbers(text: str, config: dict) -> list[str]:
    """Extract issue numbers from text based on configured prefixes"""
    # Only extract issues if issuePrefixes is configured
    if "issuePrefixes" not in config or not config["issuePrefixes"]:
        return []

    all_issues = []

    for prefix in config["issuePrefixes"]:
        # Create pattern for this prefix (e.g., "DATAGO-" -> "DATAGO-\d+")
        prefix_pattern = re.escape(prefix) + r"\d+"
        pattern = re.compile(prefix_pattern)
        matches = pattern.findall(text)
        all_issues.extend(matches)

    return list(set(all_issues))  # Remove duplicates


def clean_subject(subject: str, config: dict) -> str:
    """Clean subject by removing issue references and associated punctuation"""
    # Only clean issues if issuePrefixes is configured
    if "issuePrefixes" not in config or not config["issuePrefixes"]:
        return subject

    clean_subj = subject

    # Create a pattern that matches any of the configured prefixes
    prefixes_pattern = "|".join(re.escape(prefix) for prefix in config["issuePrefixes"])
    issue_pattern = f"({prefixes_pattern})\\d+"

    # Check if any issue references exist in the subject
    if re.search(issue_pattern, subject):
        # Pattern 1: Remove "ISSUE-XXX: " at the beginning
        clean_subj = re.sub(f"^{issue_pattern}:\\s*", "", clean_subj)

        # Pattern 2: Remove "and ISSUE-XXX " at the beginning (special case)
        clean_subj = re.sub(f"^and\\s+{issue_pattern}\\s*", "", clean_subj)

        # Pattern 3: Remove "and ISSUE-XXX - " at the beginning (special case with dash)
        clean_subj = re.sub(f"^and\\s+{issue_pattern}\\s*-\\s*", "", clean_subj)

        # Pattern 4: Remove "and ISSUE-XXX " in the middle (with surrounding spaces)
        clean_subj = re.sub(f"\\s+and\\s+{issue_pattern}\\s*", " ", clean_subj)

        # Pattern 5: Remove "ISSUE-XXX - " (with dash and spaces)
        clean_subj = re.sub(f"{issue_pattern}\\s*-\\s*", "", clean_subj)

        # Pattern 6: Remove "ISSUE-XXX: " anywhere in the string
        clean_subj = re.sub(f"{issue_pattern}:\\s*", "", clean_subj)

        # Pattern 7: Remove standalone "ISSUE-XXX" references
        clean_subj = re.sub(f"\\s*{issue_pattern}\\s*", " ", clean_subj)

        # Clean up extra spaces and punctuation
        clean_subj = re.sub(r"\s+", " ", clean_subj)  # Multiple spaces to single space
        clean_subj = re.sub(r"^\s*[,\-:]\s*", "", clean_subj)  # Leading punctuation
        clean_subj = re.sub(r"\s*[,\-:]\s*$", "", clean_subj)  # Trailing punctuation
        clean_subj = clean_subj.strip()

    return clean_subj


def process_commits(commits: list[dict], config: dict) -> dict:
    """Process commits and organize them by type"""
    # Create type mapping from config
    type_sections = {}
    for type_config in config["types"]:
        type_sections[type_config["type"]] = {
            "section": type_config["section"],
            "commits": [],
        }

    # Process each commit
    for commit in commits:
        # Skip release commits
        if "[ci skip]" in commit["subject"]:
            continue

        # Parse commit message
        commit_type, scope, subject, pr_number = parse_commit_message(commit["subject"])

        if not commit_type or commit_type not in type_sections:
            continue

        # Extract issue numbers and clean subject
        search_text = f"{scope or ''} {subject}"
        issue_numbers = extract_issue_numbers(search_text, config)
        clean_subj = clean_subject(subject, config)

        # Add processed commit to appropriate type
        type_sections[commit_type]["commits"].append(
            {
                "hash": commit["hash"],
                "full_hash": commit["full_hash"],
                "subject": clean_subj,
                "pr_number": pr_number or commit.get("pr_number"),
                "issue_numbers": issue_numbers,
                "author": commit["author"],
            }
        )

    return type_sections


def _get_repo_url() -> str:
    """Get repository URL from environment variables"""
    github_repo = getenv("GITHUB_REPOSITORY", "")
    if github_repo:
        return f"https://github.com/{github_repo}"

    # Fallback for local testing
    org_name = getenv("GITHUB_REPOSITORY_OWNER", "example")
    repo_name = getenv("REPO_NAME", "repo")
    return f"https://github.com/{org_name}/{repo_name}"


def _format_commit_hash(commit: dict, repo_url: str) -> str:
    """Format commit hash portion of the line"""
    if commit["full_hash"]:
        commit_url = f"{repo_url}/commit/{commit['full_hash']}"
        return f"* [`{commit['hash']}`]({commit_url}) {commit['subject']}"
    return f"* {commit['subject']}"


def _add_pr_reference(line: str, commit: dict, repo_url: str) -> str:
    """Add PR reference to the line if present"""
    if commit["pr_number"]:
        pr_url = f"{repo_url}/pull/{commit['pr_number']}"
        return line + f" ([#{commit['pr_number']}]({pr_url}))"
    return line


def _should_add_issue_links(commit: dict, config: dict) -> bool:
    """Check if issue links should be added"""
    return (
        commit["issue_numbers"]
        and "issuePrefixes" in config
        and config["issuePrefixes"]
        and "issueUrlFormat" in config
        and config["issueUrlFormat"]
    )


def _build_issue_links(commit: dict, config: dict) -> list[str]:
    """Build issue links for the commit"""
    issue_url_template = config["issueUrlFormat"]
    issue_links = []

    for issue in commit["issue_numbers"]:
        for prefix in config["issuePrefixes"]:
            if issue.startswith(prefix):
                issue_id = issue.replace(prefix, "")
                url = issue_url_template.replace("{{prefix}}", prefix).replace(
                    "{{id}}", issue_id
                )
                issue_links.append(f"[{issue}]({url})")
                break

    return issue_links


def format_commit_line(commit: dict, config: dict) -> str:
    """Format a single commit line for release notes"""
    repo_url = _get_repo_url()
    line = _format_commit_hash(commit, repo_url)
    line = _add_pr_reference(line, commit, repo_url)

    # Add author information
    line += f" ({commit['author']})"

    # Add issue references if configured
    if _should_add_issue_links(commit, config):
        issue_links = _build_issue_links(commit, config)
        if issue_links:
            line += f" ({', '.join(issue_links)})"

    return line


def generate_content(type_sections: dict, config: dict) -> str:
    """Generate the release notes content from processed commits"""
    release_notes = ""
    has_commits = False

    # Output commits by type (in order defined in config)
    for type_config in config["types"]:
        commit_type = type_config["type"]
        if commit_type not in type_sections:
            continue

        type_data = type_sections[commit_type]
        if not type_data["commits"]:
            continue

        has_commits = True
        release_notes += f"## {type_data['section']}\n\n"

        for commit in type_data["commits"]:
            commit_line = format_commit_line(commit, config)
            release_notes += commit_line + "\n"

        release_notes += "\n"

    if not has_commits:
        release_notes += "No commits found in this release.\n"

    return release_notes


def write_and_output_results(
    release_notes: str, output_file: str, total_commits: int
) -> None:
    """Write release notes to file and output results to console"""
    try:
        with open(output_file, "w") as f:
            f.write(release_notes)

        print(f"✅ GitHub Release notes generated: {output_file}")
        print(f"📝 Total commits: {total_commits}")

        # Print to console as well
        print("\n" + "=" * 80)
        print(release_notes)
        print("=" * 80)

    except OSError as e:
        print(f"Error writing to {output_file}: {e}")
        sys.exit(1)


def generate_release_notes(from_tag: str, to_tag: str, output_file: str) -> None:
    """Generate release notes between two tags"""
    print(f"Generating release notes from {from_tag or 'beginning'} to {to_tag}...")

    # Load configuration and get commits
    config = load_version_config()
    commits = get_commits_between_refs(from_tag, to_tag)

    if not commits:
        print("No commits found between the specified references.")
        write_and_output_results("No commits found in this release.\n", output_file, 0)
        return

    # Process commits and generate content
    type_sections = process_commits(commits, config)
    release_notes = generate_content(type_sections, config)
    write_and_output_results(release_notes, output_file, len(commits))


def main():
    parser = argparse.ArgumentParser(
        description="Generate release notes between two git tags using PyGithub GraphQL"
    )
    parser.add_argument("from_tag", help="Starting tag (e.g., v1.2.15)")
    parser.add_argument("to_tag", help="Ending tag (e.g., v1.2.16)")
    parser.add_argument(
        "output_file",
        nargs="?",
        default="RELEASE_NOTES.md",
        help="Output file (default: RELEASE_NOTES.md)",
    )

    args = parser.parse_args()

    generate_release_notes(args.from_tag, args.to_tag, args.output_file)


if __name__ == "__main__":
    main()
