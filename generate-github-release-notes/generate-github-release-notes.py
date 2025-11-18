#!/usr/bin/env python3

import argparse
import json
import re
import sys
from os import getenv
from pathlib import Path
from packaging import version

import requests
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


def get_latest_release_tag(github_token: str, repo_name: str) -> str | None:
    """Get the latest release tag from the repository using REST API

    Uses the GitHub REST API endpoint: GET /repos/{owner}/{repo}/releases/latest
    The latest release is the most recent non-prerelease, non-draft release.

    Args:
        github_token: GitHub authentication token
        repo_name: Repository name in format "owner/repo"

    Returns:
        The tag name of the latest release, or None if no releases found
    """
    url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        print(f"Attempting to fetch latest release from {repo_name}...")
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            tag_name = data.get("tag_name")
            if tag_name:
                print(f"Found latest release: {tag_name}")
                return tag_name
        elif response.status_code == 404:
            print("No releases found in repository")
            return None
        else:
            print(f"Error fetching latest release: HTTP {response.status_code}")
            return None

    except Exception as e:
        print(f"Error fetching latest release: {e}")
        return None


# Old helper functions removed - replaced with optimized GraphQL implementation


class RefNotFoundError(Exception):
    """Raised when a git ref/tag cannot be found"""

    def __init__(self, ref: str, is_base_ref: bool = True):
        self.ref = ref
        self.is_base_ref = is_base_ref
        super().__init__(f"Could not find ref '{ref}'")


def _validate_graphql_response(result: dict, from_ref: str, to_ref: str) -> dict | None:
    """Validate GraphQL response and return commits data or raise exception if invalid

    Raises:
        RefNotFoundError: If tags/refs cannot be found (may be recoverable)
        SystemExit: If repository data is completely invalid
    """
    if not result or "repository" not in result:
        print("Error: No repository data in GraphQL result")
        sys.exit(1)

    repo_data = result["repository"]
    if not repo_data or not repo_data.get("baseTagRef"):
        # Base ref (from_ref) not found - this might be recoverable
        raise RefNotFoundError(from_ref, is_base_ref=True)

    compare_data = repo_data["baseTagRef"]["compare"]
    if not compare_data:
        # Could be either ref, but likely the to_ref
        raise RefNotFoundError(to_ref, is_base_ref=False)

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

            # This will raise RefNotFoundError if tags/refs are invalid
            commits_data = _validate_graphql_response(result, from_ref, to_ref)

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

        except RefNotFoundError:
            # Re-raise to be handled by caller
            raise
        except Exception as e:
            print(f"Error: GraphQL query failed on page {page_count + 1}: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

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
    """Get commits between two git references using efficient GraphQL queries

    If from_ref is not found but to_ref is valid, attempts to use the latest release
    tag as a fallback for from_ref.
    """
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

    except RefNotFoundError as e:
        # If the from_ref (base) was not found, try using the latest release as fallback
        if e.is_base_ref:
            print(
                f"Warning: Base ref '{from_ref}' not found. Trying fallback to latest release..."
            )

            latest_tag = get_latest_release_tag(github_token, github_repo)
            if latest_tag:
                print(
                    f"Using latest release tag '{latest_tag}' as base ref instead of '{from_ref}'"
                )
                try:
                    # Retry with the latest release tag
                    commits = _get_commits_with_prs_graphql(
                        graphql_client, github_repo, latest_tag, to_ref
                    )
                    print(f"Processing {len(commits)} commits...")
                    return commits
                except RefNotFoundError as retry_error:
                    print(f"Error: Fallback also failed: {retry_error}")
                    print(f"Could not find ref '{retry_error.ref}'")
                    sys.exit(1)
            else:
                print(
                    f"Error: Could not find base ref '{from_ref}' and no releases found for fallback"
                )
                sys.exit(1)
        else:
            # to_ref (head) not found - cannot recover
            print(f"Error: Could not find head ref '{to_ref}'")
            print(f"Please ensure the tag/ref '{to_ref}' exists")
            sys.exit(1)

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


def _get_custom_sections_config(config: dict) -> dict:
    """Get custom sections configuration"""
    custom_sections = {}

    # Legacy support for uiChanges
    if "uiChanges" in config and config["uiChanges"].get("enabled", False):
        ui_config = config["uiChanges"]
        custom_sections["UI Changes"] = {
            "tagPrefix": ui_config.get("tagPrefix", "ui-v"),
            "pathPatterns": ui_config.get("pathPatterns", ["client/webui/frontend/**"]),
            "bumpCommitPattern": ui_config.get(
                "bumpCommitPattern", r"bump version to ui-v.*\[skip ci\]"
            ),
        }

    # New generalized customSections
    if "customSections" in config:
        for section_name, section_config in config["customSections"].items():
            if section_config.get("enabled", False):
                custom_sections[section_name] = {
                    "tagPrefix": section_config.get("tagPrefix", ""),
                    "pathPatterns": section_config.get("pathPatterns", []),
                    "bumpCommitPattern": section_config.get("bumpCommitPattern", ""),
                }

    return custom_sections


def _is_custom_bump_commit(commit: dict, section_config: dict) -> str | None:
    """Check if commit is a custom section bump commit and return the version if so"""
    if not section_config or not section_config.get("bumpCommitPattern"):
        return None

    pattern = section_config["bumpCommitPattern"]
    if re.search(pattern, commit["subject"], re.IGNORECASE):
        # Extract version from commit subject
        tag_prefix = section_config.get("tagPrefix", "")
        if tag_prefix:
            version_match = re.search(
                f"{re.escape(tag_prefix)}([0-9]+\\.[0-9]+\\.[0-9]+[^\\s]*)",
                commit["subject"],
            )
            if version_match:
                return f"{tag_prefix}{version_match.group(1)}"
        else:
            # If no tag prefix, just return a generic version indicator
            return "version"

    return None


# Old functions removed - replaced with optimized GraphQL versions above


def _process_custom_bump_commit(
    i: int,
    commits: list[dict],
    section_name: str,
    section_config: dict,
    custom_commits: list[dict],
    custom_versions: list[str],
) -> None:
    """Process a custom section bump commit and identify the preceding change commit"""
    commit = commits[i]
    version = _is_custom_bump_commit(commit, section_config)

    if not version:
        return

    custom_versions.append(version)
    print(f"Found {section_name} bump commit: {version}")

    # The previous commit (if exists) is the change commit
    if i > 0:
        change_commit = commits[i - 1]
        # Only add if it's not already a custom commit and not a bump commit
        if change_commit not in custom_commits and not _is_custom_bump_commit(
            change_commit, section_config
        ):
            custom_commits.append(change_commit)
            print(
                f"  -> {section_name} change commit: {change_commit['hash']} {change_commit['subject'][:50]}..."
            )


def _create_version_range(versions: list[str]) -> str:
    """Create version range string from versions"""
    versions.sort()
    oldest_version = versions[0]
    newest_version = versions[-1]

    if oldest_version != newest_version:
        return f"{oldest_version} → {newest_version}"
    else:
        return f"up to {newest_version}"


def _process_section_commits(
    commits: list[dict], section_name: str, section_config: dict
) -> tuple[list[dict], list[str]]:
    """Process commits for a single custom section"""
    custom_commits = []
    custom_versions = []

    for i, commit in enumerate(commits):
        if _is_custom_bump_commit(commit, section_config):
            _process_custom_bump_commit(
                i,
                commits,
                section_name,
                section_config,
                custom_commits,
                custom_versions,
            )

    return custom_commits, custom_versions


def _build_section_title(section_name: str, version_range: str) -> str:
    """Build section title from name and version range"""
    if version_range != "version":
        return f"{section_name} {version_range}"
    return section_name


def _detect_custom_changes(
    commits: list[dict], config: dict
) -> tuple[list[dict], dict]:
    """
    Detect custom section changes and return (non_custom_commits, custom_changes_by_section).
    Efficient logic: Custom change commits are simply the commits before custom bump commits.

    Returns:
        - non_custom_commits: List of commits that are not custom section-related
        - custom_changes_by_section: Dict with entries for each custom section
    """
    custom_sections_config = _get_custom_sections_config(config)
    if not custom_sections_config:
        return commits, {}

    all_custom_commits = []
    custom_changes_by_section = {}

    print(
        f"Analyzing {len(commits)} commits for custom sections: {list(custom_sections_config.keys())}..."
    )

    # Process each custom section
    for section_name, section_config in custom_sections_config.items():
        custom_commits, custom_versions = _process_section_commits(
            commits, section_name, section_config
        )

        # Group all custom changes under a single version range for this section
        if custom_commits and custom_versions:
            version_range = _create_version_range(custom_versions)
            section_title = _build_section_title(section_name, version_range)
            custom_changes_by_section[section_title] = custom_commits
            all_custom_commits.extend(custom_commits)
            print(
                f"Grouped {len(custom_commits)} {section_name} commits under range: {version_range}"
            )

    # Separate non-custom commits
    non_custom_commits = [c for c in commits if c not in all_custom_commits]

    return non_custom_commits, custom_changes_by_section


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
    """Process commits and organize them by type, separating custom sections if configured"""
    # Detect custom section changes first
    non_custom_commits, custom_changes_by_section = _detect_custom_changes(
        commits, config
    )

    # Process non-custom commits
    type_sections = _create_empty_type_sections(config)
    _add_commits_to_sections(non_custom_commits, config, type_sections)

    # Process custom section commits by section
    custom_sections = {}
    for section_title, custom_commits in custom_changes_by_section.items():
        custom_type_sections = _create_empty_type_sections(config)
        _add_commits_to_sections(custom_commits, config, custom_type_sections)
        custom_sections[section_title] = custom_type_sections

    return type_sections, custom_sections


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


def _generate_custom_sections(custom_sections: dict, config: dict) -> tuple[str, bool]:
    """Generate custom commit sections and return (content, has_commits)"""
    content = ""
    has_commits = False

    for section_title, custom_type_sections in custom_sections.items():
        custom_content = ""
        custom_has_commits = False

        for type_config in config["types"]:
            commit_type = type_config["type"]
            if commit_type in custom_type_sections:
                type_data = custom_type_sections[commit_type]
                section = _generate_section_for_type(type_data, config, "###")
                if section:
                    custom_has_commits = True
                    custom_content += section

        if custom_has_commits:
            has_commits = True
            content += f"## {section_title}\n\n{custom_content}"

    return content, has_commits


def generate_content(type_sections: dict, custom_sections: dict, config: dict) -> str:
    """Generate the release notes content from processed commits"""
    # Generate main sections
    main_content, main_has_commits = _generate_main_sections(type_sections, config)

    # Generate custom sections
    custom_content, custom_has_commits = _generate_custom_sections(
        custom_sections, config
    )

    # Combine content
    release_notes = main_content + custom_content

    if not (main_has_commits or custom_has_commits):
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
    """Generate release notes between two tags

    Note: If tags/refs cannot be found, the script will exit with an error
    and no file will be created. If tags are valid but there are no commits
    between them, no file will be created either.

    Raises:
        SystemExit: If tags/refs cannot be found or other errors occur
    """
    print(f"Generating release notes from {from_tag or 'beginning'} to {to_tag}...")

    # Load configuration and get commits
    # Note: get_commits_between_refs will exit if tags don't exist
    config = load_version_config(config_file)
    commits = get_commits_between_refs(from_tag, to_tag)

    # If we get here, tags are valid. Empty list means no commits between valid tags.
    if not commits:
        print("No commits found between the specified references (tags are valid).")
        print("No release notes file will be created.")
        return

    # Process commits and generate content
    type_sections, custom_sections = process_commits(commits, config)
    release_notes = generate_content(type_sections, custom_sections, config)
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
