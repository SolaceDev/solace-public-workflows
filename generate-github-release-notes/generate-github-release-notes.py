#!/usr/bin/env python3

import argparse
import json
import re
import sys
from os import getenv
from pathlib import Path
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport

# Constants
DEFAULT_VERSION_CONFIG_FILE = ".versionrc.json"


def load_version_config(config_file_path: str = DEFAULT_VERSION_CONFIG_FILE) -> dict:
    """Load configuration from specified config file or default configuration file"""
    # Try GitHub Actions workspace first, then current directory
    workspace_path = Path(f"/github/workspace/{config_file_path}")
    local_path = Path(config_file_path)

    config_path = workspace_path if workspace_path.exists() else local_path

    if not config_path.exists():
        print(f"Warning: {config_file_path} not found, using default configuration")
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
            # No default uiChanges configuration
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
        print(f"Error reading {config_file_path}: {e}")
        sys.exit(1)


def _validate_environment() -> tuple[str, str]:
    """Validate required environment variables"""
    github_token = getenv("GITHUB_TOKEN")
    github_repo = getenv("GITHUB_REPOSITORY")

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)

    if not github_repo:
        print("Error: GITHUB_REPOSITORY environment variable not set")
        sys.exit(1)

    return github_token, github_repo


def _create_graphql_client(github_token: str) -> Client:
    """Create a GraphQL client for GitHub API"""
    transport = RequestsHTTPTransport(
        url="https://api.github.com/graphql",
        headers={"Authorization": f"Bearer {github_token}"},
        verify=True,
        retries=3,
    )
    return Client(transport=transport)


# Old helper functions removed - replaced with optimized GraphQL implementation


def _validate_graphql_response(result: dict, from_ref: str, to_ref: str) -> dict | None:
    """Validate GraphQL response and return commits data or None if invalid"""
    if not result or "repository" not in result:
        print("No repository data in GraphQL result")
        return None

    repo_data = result["repository"]
    if not repo_data or not repo_data.get("baseTagRef"):
        print(f"Error: Could not find base ref '{from_ref}' in repository")
        return None

    compare_data = repo_data["baseTagRef"]["compare"]
    if not compare_data:
        print(f"Error: Could not compare {from_ref} with {to_ref}")
        return None

    return compare_data["commits"]


def _extract_commit_from_node(node: dict) -> dict:
    """Extract commit data from GraphQL node"""
    # Extract PR number
    pr_number = None
    if node["associatedPullRequests"]["nodes"]:
        pr_number = str(node["associatedPullRequests"]["nodes"][0]["number"])

    # Build commit dict
    return {
        "hash": node["abbreviatedOid"],
        "full_hash": node["oid"],
        "subject": node["messageHeadline"],
        "author": node["author"]["name"] if node["author"] else "Unknown",
        "pr_number": pr_number,
        "changed_files": node.get("changedFilesIfAvailable", 0),
        "committed_date": node["committedDate"],
        "authored_date": node["authoredDate"],
        "additions": node.get("additions", 0),
        "deletions": node.get("deletions", 0),
    }


def _get_commits_with_prs_graphql(
    graphql_client: Client, repo_name: str, from_ref: str, to_ref: str
) -> list[dict[str, str]]:
    """Get commits between refs using GraphQL compare API with pagination"""
    owner, repo = repo_name.split("/")

    print(f"Fetching commits between {from_ref} and {to_ref} using GraphQL compare...")

    # GraphQL query using compare API
    query = gql("""
    query($owner: String!, $repo: String!, $baseRef: String!, $headRef: String!, $after: String) {
      repository(owner: $owner, name: $repo) {
        nameWithOwner
        baseTagRef: ref(qualifiedName: $baseRef) {
          name
          compare(headRef: $headRef) {
            status
            aheadBy
            behindBy
            commits(first: 100, after: $after) {
              pageInfo {
                hasNextPage
                endCursor
              }
              totalCount
              nodes {
                oid
                abbreviatedOid
                messageHeadline
                messageBody
                author {
                  name
                  email
                  user {
                    login
                  }
                }
                authoredDate
                committedDate
                additions
                deletions
                changedFilesIfAvailable
                associatedPullRequests(first: 1) {
                  nodes {
                    number
                    title
                    url
                  }
                }
              }
            }
          }
        }
      }
    }
    """)

    commits = []
    has_next_page = True
    cursor = None
    page_count = 0

    while has_next_page and page_count < 50:  # Limit to 50 pages (5000 commits max)
        variables = {
            "owner": owner,
            "repo": repo,
            "baseRef": from_ref,
            "headRef": to_ref,
            "after": cursor,
        }

        try:
            print(f"Executing GraphQL query (page {page_count + 1})...")
            result = graphql_client.execute(query, variable_values=variables)

            commits_data = _validate_graphql_response(result, from_ref, to_ref)
            if not commits_data:
                break

            page_info = commits_data["pageInfo"]
            nodes = commits_data["nodes"]

            print(f"Found {len(nodes)} commits on page {page_count + 1}")
            print(
                f"Total commits in comparison: {commits_data.get('totalCount', 'unknown')}"
            )

            # Process all nodes in this page
            for node in nodes:
                commit_dict = _extract_commit_from_node(node)
                commits.append(commit_dict)

            has_next_page = page_info["hasNextPage"]
            cursor = page_info["endCursor"]
            page_count += 1

        except Exception as e:
            print(f"GraphQL query failed on page {page_count + 1}: {e}")
            import traceback

            traceback.print_exc()
            break

    print(f"Successfully fetched {len(commits)} commits using GraphQL compare")
    return commits


def _build_commit_dict(commit, pr_number: str | None) -> dict[str, str]:
    """Build commit dictionary from commit object"""
    return {
        "hash": commit.sha[:7],
        "full_hash": commit.sha,
        "subject": commit.commit.message.split("\n")[0],
        "author": commit.commit.author.name if commit.commit.author else "Unknown",
        "pr_number": pr_number,
    }


def get_commits_between_refs(from_ref: str, to_ref: str) -> list[dict[str, str]]:
    """Get commits between two git references using efficient GraphQL queries"""
    github_token, github_repo = _validate_environment()

    try:
        # Create GraphQL client for GitHub API
        graphql_client = _create_graphql_client(github_token)

        # Use GraphQL to get commits with associated PRs in a single query
        commits = _get_commits_with_prs_graphql(
            graphql_client, github_repo, from_ref, to_ref
        )

        print(f"Processing {len(commits)} commits...")
        return commits

    except Exception as e:
        print(f"Error: Failed to get commits using GraphQL: {e}")
        import traceback

        traceback.print_exc()
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
        # Create pattern for this prefix (e.g., "ISSUE-" -> "ISSUE-\d+")
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


def _is_ui_changes_enabled(config: dict) -> bool:
    """Check if UI changes detection is enabled"""
    return "uiChanges" in config and config["uiChanges"].get("enabled", False)


def _get_ui_config(config: dict) -> dict:
    """Get UI configuration with defaults"""
    if not _is_ui_changes_enabled(config):
        return {}

    ui_config = config["uiChanges"]
    return {
        "tagPrefix": ui_config.get("tagPrefix", "ui-v"),
        "pathPatterns": ui_config.get("pathPatterns", ["client/webui/frontend/**"]),
        "bumpCommitPattern": ui_config.get(
            "bumpCommitPattern", r"bump version to ui-v.*\[skip ci\]"
        ),
    }


def _is_ui_bump_commit(commit: dict, ui_config: dict) -> str | None:
    """Check if commit is a UI bump commit and return the version if so"""
    if not ui_config:
        return None

    pattern = ui_config["bumpCommitPattern"]
    if re.search(pattern, commit["subject"], re.IGNORECASE):
        # Extract version from commit subject (e.g., "bump version to ui-v0.9.1 [skip ci]")
        tag_prefix = ui_config["tagPrefix"]
        version_match = re.search(
            f"{re.escape(tag_prefix)}([0-9]+\\.[0-9]+\\.[0-9]+[^\\s]*)",
            commit["subject"],
        )
        if version_match:
            return f"{tag_prefix}{version_match.group(1)}"

    return None


# Old functions removed - replaced with optimized GraphQL versions above


def _process_ui_bump_commit(
    i: int,
    commits: list[dict],
    ui_config: dict,
    ui_commits: list[dict],
    ui_versions: list[str],
) -> None:
    """Process a UI bump commit and identify the preceding UI change commit"""
    commit = commits[i]
    ui_version = _is_ui_bump_commit(commit, ui_config)

    if not ui_version:
        return

    ui_versions.append(ui_version)
    print(f"Found UI bump commit: {ui_version}")

    # The previous commit (if exists) is the UI change commit
    if i > 0:
        ui_change_commit = commits[i - 1]
        # Only add if it's not already a UI commit and not a bump commit
        if ui_change_commit not in ui_commits and not _is_ui_bump_commit(
            ui_change_commit, ui_config
        ):
            ui_commits.append(ui_change_commit)
            print(
                f"  -> UI change commit: {ui_change_commit['hash']} {ui_change_commit['subject'][:50]}..."
            )


def _create_version_range(ui_versions: list[str]) -> str:
    """Create version range string from UI versions"""
    ui_versions.sort()
    oldest_version = ui_versions[0]
    newest_version = ui_versions[-1]

    if oldest_version != newest_version:
        return f"{oldest_version} → {newest_version}"
    else:
        return f"up to {newest_version}"


def _detect_ui_changes(commits: list[dict], config: dict) -> tuple[list[dict], dict]:
    """
    Detect UI changes and return (non_ui_commits, ui_changes_by_version).
    Efficient logic: UI change commits are simply the commits before UI bump commits.

    Returns:
        - non_ui_commits: List of commits that are not UI-related
        - ui_changes_by_version: Dict with single entry for all UI changes
    """
    if not _is_ui_changes_enabled(config):
        return commits, {}

    ui_config = _get_ui_config(config)
    non_ui_commits = []
    ui_commits = []
    ui_versions = []

    print(f"Analyzing {len(commits)} commits for UI changes...")

    # Process commits in order to find UI bump commits and their preceding changes
    for i, commit in enumerate(commits):
        if _is_ui_bump_commit(commit, ui_config):
            _process_ui_bump_commit(i, commits, ui_config, ui_commits, ui_versions)
        elif commit not in ui_commits:
            # Regular commit - add to non-UI unless it's already identified as UI
            non_ui_commits.append(commit)

    # Group all UI changes under a single version range
    ui_changes_by_version = {}
    if ui_commits and ui_versions:
        version_range = _create_version_range(ui_versions)
        ui_changes_by_version[version_range] = ui_commits
        print(f"Grouped {len(ui_commits)} UI commits under range: {version_range}")

    return non_ui_commits, ui_changes_by_version


# Removed unnecessary helper functions - simplified UI detection logic


def _create_empty_type_sections(config: dict) -> dict:
    """Create empty type sections from config"""
    type_sections = {}
    for type_config in config["types"]:
        type_sections[type_config["type"]] = {
            "section": type_config["section"],
            "commits": [],
        }
    return type_sections


def _process_single_commit(commit: dict, config: dict) -> dict | None:
    """Process a single commit and return processed commit dict or None if should be skipped"""
    # Skip release commits
    if "[ci skip]" in commit["subject"]:
        return None

    # Parse commit message
    commit_type, scope, subject, pr_number = parse_commit_message(commit["subject"])

    if not commit_type:
        return None

    # Extract issue numbers and clean subject
    search_text = f"{scope or ''} {subject}"
    issue_numbers = extract_issue_numbers(search_text, config)
    clean_subj = clean_subject(subject, config)

    return {
        "type": commit_type,
        "hash": commit["hash"],
        "full_hash": commit["full_hash"],
        "subject": clean_subj,
        "pr_number": pr_number or commit.get("pr_number"),
        "issue_numbers": issue_numbers,
        "author": commit["author"],
    }


def _add_commits_to_sections(
    commits: list[dict], config: dict, type_sections: dict
) -> None:
    """Add processed commits to their respective type sections"""
    for commit in commits:
        processed_commit = _process_single_commit(commit, config)
        if processed_commit and processed_commit["type"] in type_sections:
            # Remove 'type' key before adding to section
            commit_type = processed_commit.pop("type")
            type_sections[commit_type]["commits"].append(processed_commit)


def process_commits(commits: list[dict], config: dict) -> tuple[dict, dict]:
    """Process commits and organize them by type, separating UI changes if configured"""
    # Detect UI changes first
    non_ui_commits, ui_changes_by_version = _detect_ui_changes(commits, config)

    # Process non-UI commits
    type_sections = _create_empty_type_sections(config)
    _add_commits_to_sections(non_ui_commits, config, type_sections)

    # Process UI commits by version
    ui_sections = {}
    for version_range, ui_commits in ui_changes_by_version.items():
        ui_type_sections = _create_empty_type_sections(config)
        _add_commits_to_sections(ui_commits, config, ui_type_sections)
        ui_sections[version_range] = ui_type_sections

    return type_sections, ui_sections


def _get_repo_url() -> str:
    """Get repository URL from environment variables"""
    github_repo = getenv("GITHUB_REPOSITORY")
    if not github_repo:
        print("Error: GITHUB_REPOSITORY environment variable not set")
        sys.exit(1)

    return f"https://github.com/{github_repo}"


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


def _generate_section_for_type(
    type_data: dict, config: dict, header_prefix: str = "##"
) -> str:
    """Generate a section for a specific commit type"""
    if not type_data["commits"]:
        return ""

    section = f"{header_prefix} {type_data['section']}\n\n"
    for commit in type_data["commits"]:
        commit_line = format_commit_line(commit, config)
        section += commit_line + "\n"
    section += "\n"
    return section


def _generate_main_sections(type_sections: dict, config: dict) -> tuple[str, bool]:
    """Generate main commit sections and return (content, has_commits)"""
    content = ""
    has_commits = False

    for type_config in config["types"]:
        commit_type = type_config["type"]
        if commit_type in type_sections:
            type_data = type_sections[commit_type]
            section = _generate_section_for_type(type_data, config)
            if section:
                has_commits = True
                content += section

    return content, has_commits


def _generate_ui_sections(ui_sections: dict, config: dict) -> tuple[str, bool]:
    """Generate UI commit sections and return (content, has_commits)"""
    content = ""
    has_commits = False

    for version_range, ui_type_sections in ui_sections.items():
        ui_content = ""
        ui_has_commits = False

        for type_config in config["types"]:
            commit_type = type_config["type"]
            if commit_type in ui_type_sections:
                type_data = ui_type_sections[commit_type]
                section = _generate_section_for_type(type_data, config, "###")
                if section:
                    ui_has_commits = True
                    ui_content += section

        if ui_has_commits:
            has_commits = True
            content += f"## UI Changes {version_range}\n\n{ui_content}"

    return content, has_commits


def generate_content(type_sections: dict, ui_sections: dict, config: dict) -> str:
    """Generate the release notes content from processed commits"""
    # Generate main sections
    main_content, main_has_commits = _generate_main_sections(type_sections, config)

    # Generate UI sections
    ui_content, ui_has_commits = _generate_ui_sections(ui_sections, config)

    # Combine content
    release_notes = main_content + ui_content

    if not (main_has_commits or ui_has_commits):
        release_notes = "No commits found in this release.\n"

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

        # Set GitHub Action outputs if running in GitHub Actions
        github_output = getenv("GITHUB_OUTPUT")
        if github_output:
            try:
                with open(github_output, "a") as f:
                    f.write(f"release-notes-path={output_file}\n")
                    f.write(f"total-commits={total_commits}\n")
                print(
                    f"✅ GitHub Action outputs set: release-notes-path={output_file}, total-commits={total_commits}"
                )
            except OSError as e:
                print(f"Warning: Could not write to GITHUB_OUTPUT: {e}")

        # Print to console as well
        print("\n" + "=" * 80)
        print(release_notes)
        print("=" * 80)

    except OSError as e:
        print(f"Error writing to {output_file}: {e}")
        sys.exit(1)


def generate_release_notes(
    from_tag: str,
    to_tag: str,
    output_file: str,
    config_file: str = DEFAULT_VERSION_CONFIG_FILE,
) -> None:
    """Generate release notes between two tags"""
    print(f"Generating release notes from {from_tag or 'beginning'} to {to_tag}...")

    # Load configuration and get commits
    config = load_version_config(config_file)
    commits = get_commits_between_refs(from_tag, to_tag)

    if not commits:
        print("No commits found between the specified references.")
        write_and_output_results("No commits found in this release.\n", output_file, 0)
        return

    # Process commits and generate content
    type_sections, ui_sections = process_commits(commits, config)
    release_notes = generate_content(type_sections, ui_sections, config)
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
    parser.add_argument(
        "config_file",
        nargs="?",
        default=DEFAULT_VERSION_CONFIG_FILE,
        help=f"Configuration file path (default: {DEFAULT_VERSION_CONFIG_FILE})",
    )

    args = parser.parse_args()

    generate_release_notes(
        args.from_tag, args.to_tag, args.output_file, args.config_file
    )


if __name__ == "__main__":
    main()
