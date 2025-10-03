#!/usr/bin/env python3

import argparse
import json
import re
import sys
import ssl
from os import getenv
from pathlib import Path
import urllib.request
import urllib.parse
import urllib.error


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


def get_github_release_notes(from_tag: str, to_tag: str) -> str:
    """Get release notes from GitHub API"""
    # Get repository info from environment
    github_repo = getenv("GITHUB_REPOSITORY")
    github_token = getenv("GITHUB_TOKEN")

    if not github_repo:
        print("Error: GITHUB_REPOSITORY environment variable not set")
        sys.exit(1)

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)

    owner, repo = github_repo.split("/")

    # Prepare API request
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/generate-notes"

    data = {
        "tag_name": to_tag,
    }

    if from_tag:
        data["previous_tag_name"] = from_tag

    # Make API request
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        # Create SSL context with proper certificate verification and secure TLS version
        ssl_context = ssl.create_default_context()
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        with urllib.request.urlopen(req, context=ssl_context) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("body", "")

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"Error: GitHub API request failed with status {e.code}")
        print(f"Response: {error_body}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to get release notes from GitHub API: {e}")
        sys.exit(1)


def parse_github_release_notes(release_notes_body: str) -> list[dict[str, str]]:
    """Parse GitHub release notes body and extract commit information"""
    commits = []

    # Split by lines and process each line
    lines = release_notes_body.split("\n")

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Parse GitHub release notes format: * commit_title by @author in PR_URL
        match = re.match(
            r"^\*\s+(.+?)\s+by\s+@([^\s]+)\s+in\s+https://github\.com/[^/]+/[^/]+/pull/(\d+)(?:\s|$)",
            line,
        )

        if match:
            subject = match.group(1).strip()
            author = match.group(2).strip()
            pr_number = match.group(3).strip()

            commits.append(
                {
                    "subject": subject,
                    "author": author,
                    "pr_number": pr_number,
                    "hash": "",  # GitHub API doesn't provide commit hash in release notes
                    "full_hash": "",
                }
            )

    return commits


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
                "hash": commit["hash"][:7] if commit["hash"] else "",
                "full_hash": commit["hash"] if commit["hash"] else "",
                "subject": clean_subj,
                "pr_number": pr_number or commit.get("pr_number"),
                "issue_numbers": issue_numbers,
                "author": commit["author"],
            }
        )

    return type_sections


def format_commit_line(commit: dict, config: dict) -> str:
    """Format a single commit line for release notes"""
    # Get repository info from environment or use defaults
    github_repo = getenv("GITHUB_REPOSITORY", "")
    if github_repo:
        repo_url = f"https://github.com/{github_repo}"
    else:
        # Fallback for local testing
        org_name = getenv("GITHUB_REPOSITORY_OWNER", "example")
        repo_name = getenv("REPO_NAME", "repo")
        repo_url = f"https://github.com/{org_name}/{repo_name}"

    # Format commit hash and URL if available
    if commit["full_hash"]:
        commit_url = f"{repo_url}/commit/{commit['full_hash']}"
        line = f"* [`{commit['hash']}`]({commit_url}) {commit['subject']}"
    else:
        # No commit hash available from GitHub API
        line = f"* {commit['subject']}"

    # Add PR reference if present
    if commit["pr_number"]:
        pr_url = f"{repo_url}/pull/{commit['pr_number']}"
        line += f" ([#{commit['pr_number']}]({pr_url}))"

    # Add author information (just the name, no GitHub link)
    line += f" ({commit['author']})"

    # Add issue references only if both issuePrefixes and issueUrlFormat are configured
    if (
        commit["issue_numbers"]
        and "issuePrefixes" in config
        and config["issuePrefixes"]
        and "issueUrlFormat" in config
        and config["issueUrlFormat"]
    ):
        issue_url_template = config["issueUrlFormat"]
        issue_links = []

        for issue in commit["issue_numbers"]:
            # Extract prefix and id from issue format (e.g., DATAGO-123 -> prefix="DATAGO-", id="123")
            for prefix in config["issuePrefixes"]:
                if issue.startswith(prefix):
                    issue_id = issue.replace(prefix, "")
                    url = issue_url_template.replace("{{prefix}}", prefix).replace(
                        "{{id}}", issue_id
                    )
                    issue_links.append(f"[{issue}]({url})")
                    break

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
    print(f"Generating release notes from {from_tag} to {to_tag}...")

    # Load configuration and get GitHub release notes
    config = load_version_config()
    github_release_notes = get_github_release_notes(from_tag, to_tag)

    if not github_release_notes:
        print("No release notes generated by GitHub API.")
        return

    # Parse GitHub release notes to extract commit information
    commits = parse_github_release_notes(github_release_notes)

    if not commits:
        print("No commits found in GitHub release notes.")
        return

    # Process commits and generate content
    type_sections = process_commits(commits, config)
    release_notes = generate_content(type_sections, config)
    write_and_output_results(release_notes, output_file, len(commits))


def main():
    parser = argparse.ArgumentParser(
        description="Generate release notes between two git tags"
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
