#!/usr/bin/env python3

import argparse
import json
import re
import sys
from os import getenv
from pathlib import Path
from github import Github, Auth


def load_version_config(config_file_path: str = ".versionrc.json") -> dict:
    """Load configuration from specified config file or default .versionrc.json"""
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


# Old helper functions removed - replaced with optimized GraphQL implementation


def _get_commits_with_prs_graphql(
    github_client, repo_name: str, from_ref: str, to_ref: str
) -> list[dict[str, str]]:
    """Get commits with PR associations and file changes using GraphQL with pagination"""
    owner, repo = repo_name.split("/")

    # GraphQL query to get commits with associated PRs and file changes
    query = """
    query($owner: String!, $repo: String!, $since: GitTimestamp, $until: GitTimestamp, $after: String) {
      repository(owner: $owner, name: $repo) {
        defaultBranchRef {
          target {
            ... on Commit {
              history(since: $since, until: $until, first: 100, after: $after) {
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  oid
                  abbreviatedOid
                  message
                  author {
                    name
                    email
                  }
                  committedDate
                  associatedPullRequests(first: 1) {
                    nodes {
                      number
                    }
                  }
                  changedFiles
                  changedFilesIfAvailable
                }
              }
            }
          }
        }
      }
    }
    """

    commits = []
    has_next_page = True
    cursor = None

    # Get commit date ranges for filtering
    try:
        repo_obj = github_client.get_repo(repo_name)

        # Get the date range for filtering
        since_date = None
        until_date = None

        if from_ref:
            try:
                from_commit = repo_obj.get_commit(from_ref)
                since_date = from_commit.commit.committer.date.isoformat()
            except:
                pass

        try:
            to_commit = repo_obj.get_commit(to_ref)
            until_date = to_commit.commit.committer.date.isoformat()
        except:
            pass
    except Exception as e:
        print(f"Warning: Could not get date range for filtering: {e}")

    page_count = 0
    while has_next_page and page_count < 50:  # Limit to 50 pages (5000 commits max)
        variables = {
            "owner": owner,
            "repo": repo,
            "since": since_date,
            "until": until_date,
            "after": cursor,
        }

        try:
            result = github_client._Github__requester.graphql_query(query, variables)

            if not result or "data" not in result:
                break

            history = result["data"]["repository"]["defaultBranchRef"]["target"][
                "history"
            ]
            page_info = history["pageInfo"]
            nodes = history["nodes"]

            for node in nodes:
                # Extract PR number
                pr_number = None
                if node["associatedPullRequests"]["nodes"]:
                    pr_number = str(
                        node["associatedPullRequests"]["nodes"][0]["number"]
                    )

                # Build commit dict
                commit_dict = {
                    "hash": node["abbreviatedOid"],
                    "full_hash": node["oid"],
                    "subject": node["message"].split("\n")[0],
                    "author": node["author"]["name"] if node["author"] else "Unknown",
                    "pr_number": pr_number,
                    "changed_files": node.get("changedFiles", 0),
                    "committed_date": node["committedDate"],
                }
                commits.append(commit_dict)

            has_next_page = page_info["hasNextPage"]
            cursor = page_info["endCursor"]
            page_count += 1

            print(
                f"Fetched page {page_count}, got {len(nodes)} commits (total: {len(commits)})"
            )

        except Exception as e:
            print(f"Warning: GraphQL query failed on page {page_count}: {e}")
            break

    # Filter commits to the actual range if we have specific refs
    if from_ref and to_ref:
        try:
            repo_obj = github_client.get_repo(repo_name)
            comparison = repo_obj.compare(from_ref, to_ref)
            commit_shas = {c.sha for c in comparison.commits}

            # Filter to only commits in the comparison
            filtered_commits = [c for c in commits if c["full_hash"] in commit_shas]
            print(
                f"Filtered to {len(filtered_commits)} commits in range {from_ref}..{to_ref}"
            )
            return filtered_commits
        except Exception as e:
            print(f"Warning: Could not filter commits to range: {e}")

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
    """Get commits between two git references using optimized API calls"""
    github_token, github_repo = _validate_environment()

    try:
        auth = Auth.Token(github_token)
        g = Github(auth=auth)
        repo = g.get_repo(github_repo)

        # Get commits using REST API comparison (reliable for commit ranges)
        if from_ref:
            comparison = repo.compare(from_ref, to_ref)
            commits_data = comparison.commits
        else:
            commits_data = repo.get_commits(sha=to_ref)

        print(
            f"Processing {commits_data.totalCount if hasattr(commits_data, 'totalCount') else len(list(commits_data))} commits..."
        )

        # Convert to our format and batch fetch PR associations using GraphQL
        commits = []
        commit_shas = []

        # First pass: collect commits and SHAs
        for commit in commits_data:
            commit_dict = {
                "hash": commit.sha[:7],
                "full_hash": commit.sha,
                "subject": commit.commit.message.split("\n")[0],
                "author": commit.commit.author.name
                if commit.commit.author
                else "Unknown",
                "pr_number": None,  # Will be filled by GraphQL batch query
            }
            commits.append(commit_dict)
            commit_shas.append(commit.sha)

        # Second pass: batch fetch PR associations using GraphQL
        if commit_shas:
            pr_associations = _get_pr_associations_batch(g, github_repo, commit_shas)
            for commit in commits:
                commit["pr_number"] = pr_associations.get(commit["full_hash"])

        print(f"Successfully processed {len(commits)} commits with PR associations")
        return commits

    except Exception as e:
        print(f"Error: Failed to get commits: {e}")
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


def _detect_ui_changes(commits: list[dict], config: dict) -> tuple[list[dict], dict]:
    """
    Detect UI changes and return (non_ui_commits, ui_changes_by_version).
    Optimized with batch GraphQL operations for large commit ranges.

    Returns:
        - non_ui_commits: List of commits that are not UI-related
        - ui_changes_by_version: Dict mapping version ranges to UI commits
    """
    if not _is_ui_changes_enabled(config):
        return commits, {}

    ui_config = _get_ui_config(config)
    github_token, github_repo = _validate_environment()

    try:
        auth = Auth.Token(github_token)
        g = Github(auth=auth)
    except Exception as e:
        print(f"Warning: Could not connect to GitHub for UI detection: {e}")
        return commits, {}

    ui_changes_by_version = {}
    non_ui_commits = []
    potential_ui_commits = []
    ui_bump_commits = []

    print(f"Analyzing {len(commits)} commits for UI changes...")

    # First pass: identify UI bump commits and potential UI commits
    for commit in commits:
        ui_version = _is_ui_bump_commit(commit, ui_config)
        if ui_version:
            ui_bump_commits.append((commit, ui_version))
        else:
            potential_ui_commits.append(commit)

    print(
        f"Found {len(ui_bump_commits)} UI bump commits, checking {len(potential_ui_commits)} potential UI commits..."
    )

    # Batch check UI file changes for potential commits
    if potential_ui_commits:
        commit_shas = [c["full_hash"] for c in potential_ui_commits]

        # Check commits in batches to avoid overwhelming the API
        ui_results = {}
        batch_size = 20

        for i in range(0, len(commit_shas), batch_size):
            batch_shas = commit_shas[i : i + batch_size]
            print(
                f"Checking UI changes for commits {i + 1}-{min(i + batch_size, len(commit_shas))} of {len(commit_shas)}..."
            )

            batch_results = _get_ui_commits_batch_graphql(
                g, github_repo, batch_shas, ui_config
            )
            ui_results.update(batch_results)

        # Separate UI commits from non-UI commits
        ui_commits = []
        for commit in potential_ui_commits:
            if ui_results.get(commit["full_hash"], False):
                ui_commits.append(commit)
            else:
                non_ui_commits.append(commit)

        print(f"Found {len(ui_commits)} commits that modified UI files")

        # Group UI commits by their associated bump versions
        if ui_commits:
            ui_changes_by_version = _group_ui_commits_by_version(
                ui_commits, ui_bump_commits, commits, g, github_repo, ui_config
            )

    return non_ui_commits, ui_changes_by_version


def _get_ui_commits_batch_graphql(
    github_client, repo_name: str, commit_shas: list[str], ui_config: dict
) -> dict[str, bool]:
    """Check multiple commits for UI changes using efficient batch operations"""
    if not ui_config or not commit_shas:
        return {}

    path_patterns = ui_config["pathPatterns"]
    results = {}

    # For now, use individual checks but with optimized error handling
    # In the future, this could be enhanced with GraphQL file queries
    try:
        repo = github_client.get_repo(repo_name)

        for sha in commit_shas:
            try:
                commit_obj = repo.get_commit(sha)
                files_changed = [file.filename for file in commit_obj.files]

                # Check if any changed file matches UI path patterns
                is_ui_commit = False
                for file_path in files_changed:
                    for pattern in path_patterns:
                        if pattern.endswith("**"):
                            pattern_prefix = pattern[:-2]  # Remove "**"
                            if file_path.startswith(pattern_prefix):
                                is_ui_commit = True
                                break
                        elif pattern in file_path or file_path.startswith(pattern):
                            is_ui_commit = True
                            break
                    if is_ui_commit:
                        break

                results[sha] = is_ui_commit

            except Exception as e:
                print(f"Warning: Could not check commit {sha[:7]}: {e}")
                results[sha] = False

    except Exception as e:
        print(f"Warning: Batch UI check failed: {e}")
        # Return False for all commits if batch fails
        for sha in commit_shas:
            results[sha] = False

    return results


def _group_ui_commits_by_version(
    ui_commits, ui_bump_commits, all_commits, github_client, repo_name, ui_config
):
    """Group UI commits by their associated version ranges"""
    ui_changes_by_version = {}

    # Get UI tags once for all version lookups
    ui_tags = _get_ui_tags_optimized(github_client, repo_name, ui_config)

    for ui_commit in ui_commits:
        # Find the UI bump commit that comes after this UI commit
        ui_version = None
        commit_index = None

        # Find the index of our UI commit
        for i, commit in enumerate(all_commits):
            if commit["full_hash"] == ui_commit["full_hash"]:
                commit_index = i
                break

        if commit_index is not None:
            # Look for UI bump commit that comes after this commit in the list
            for i in range(commit_index + 1, len(all_commits)):
                for bump_commit, bump_version in ui_bump_commits:
                    if all_commits[i]["full_hash"] == bump_commit["full_hash"]:
                        ui_version = bump_version
                        break
                if ui_version:
                    break

        if ui_version:
            # Get the previous UI version from cached tags
            previous_ui_version = _get_previous_ui_version_from_tags(
                ui_version, ui_tags
            )

            if previous_ui_version:
                version_range = f"{previous_ui_version} → {ui_version}"
            else:
                version_range = f"up to {ui_version}"

            if version_range not in ui_changes_by_version:
                ui_changes_by_version[version_range] = []
            ui_changes_by_version[version_range].append(ui_commit)
        else:
            # No bump commit found, add to unreleased
            version_range = "unreleased UI changes"
            if version_range not in ui_changes_by_version:
                ui_changes_by_version[version_range] = []
            ui_changes_by_version[version_range].append(ui_commit)

    return ui_changes_by_version


def _get_ui_tags_optimized(github_client, repo_name: str, ui_config: dict) -> list[str]:
    """Get UI tags efficiently with caching"""
    try:
        repo = github_client.get_repo(repo_name)
        tag_prefix = ui_config["tagPrefix"]

        ui_tags = []
        # Limit to reasonable number of tags to avoid rate limits
        for tag in repo.get_tags()[:200]:  # Get first 200 tags
            if tag.name.startswith(tag_prefix):
                ui_tags.append(tag.name)

        ui_tags.sort()
        return ui_tags

    except Exception as e:
        print(f"Warning: Could not get UI tags: {e}")
        return []


def _get_previous_ui_version_from_tags(
    current_version: str, ui_tags: list[str]
) -> str | None:
    """Get previous UI version from pre-fetched tags list"""
    try:
        current_index = ui_tags.index(current_version)
        if current_index > 0:
            return ui_tags[current_index - 1]
    except ValueError:
        pass
    return None


def process_commits(commits: list[dict], config: dict) -> tuple[dict, dict]:
    """Process commits and organize them by type, separating UI changes if configured"""
    # Detect UI changes first
    non_ui_commits, ui_changes_by_version = _detect_ui_changes(commits, config)

    # Create type mapping from config
    type_sections = {}
    for type_config in config["types"]:
        type_sections[type_config["type"]] = {
            "section": type_config["section"],
            "commits": [],
        }

    # Process non-UI commits
    for commit in non_ui_commits:
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

    # Process UI commits by version
    ui_sections = {}
    for version_range, ui_commits in ui_changes_by_version.items():
        ui_type_sections = {}
        for type_config in config["types"]:
            ui_type_sections[type_config["type"]] = {
                "section": type_config["section"],
                "commits": [],
            }

        for commit in ui_commits:
            # Skip release commits
            if "[ci skip]" in commit["subject"]:
                continue

            # Parse commit message
            commit_type, scope, subject, pr_number = parse_commit_message(
                commit["subject"]
            )

            if not commit_type or commit_type not in ui_type_sections:
                continue

            # Extract issue numbers and clean subject
            search_text = f"{scope or ''} {subject}"
            issue_numbers = extract_issue_numbers(search_text, config)
            clean_subj = clean_subject(subject, config)

            # Add processed commit to appropriate type
            ui_type_sections[commit_type]["commits"].append(
                {
                    "hash": commit["hash"],
                    "full_hash": commit["full_hash"],
                    "subject": clean_subj,
                    "pr_number": pr_number or commit.get("pr_number"),
                    "issue_numbers": issue_numbers,
                    "author": commit["author"],
                }
            )

        ui_sections[version_range] = ui_type_sections

    return type_sections, ui_sections


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


def generate_content(type_sections: dict, ui_sections: dict, config: dict) -> str:
    """Generate the release notes content from processed commits"""
    release_notes = ""
    has_commits = False

    # Output main commits by type (in order defined in config)
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

    # Output UI changes sections
    for version_range, ui_type_sections in ui_sections.items():
        ui_has_commits = False
        ui_content = ""

        # Check if there are any UI commits
        for type_config in config["types"]:
            commit_type = type_config["type"]
            if commit_type not in ui_type_sections:
                continue

            type_data = ui_type_sections[commit_type]
            if not type_data["commits"]:
                continue

            ui_has_commits = True
            ui_content += f"### {type_data['section']}\n\n"

            for commit in type_data["commits"]:
                commit_line = format_commit_line(commit, config)
                ui_content += commit_line + "\n"

            ui_content += "\n"

        if ui_has_commits:
            has_commits = True
            release_notes += f"## UI Changes {version_range}\n\n"
            release_notes += ui_content

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


def generate_release_notes(
    from_tag: str, to_tag: str, output_file: str, config_file: str = ".versionrc.json"
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
        default=".versionrc.json",
        help="Configuration file path (default: .versionrc.json)",
    )

    args = parser.parse_args()

    generate_release_notes(
        args.from_tag, args.to_tag, args.output_file, args.config_file
    )


if __name__ == "__main__":
    main()
