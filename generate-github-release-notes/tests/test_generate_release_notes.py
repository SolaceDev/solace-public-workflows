#!/usr/bin/env python3

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the parent directory to the path so we can import the script
import sys
import importlib.util

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the script as a module
script_path = Path(__file__).parent.parent / "generate-github-release-notes.py"
spec = importlib.util.spec_from_file_location(
    "generate_github_release_notes", script_path
)
generate_github_release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate_github_release_notes)

# Import functions - updated to match refactored code
load_version_config = generate_github_release_notes.load_version_config
get_commits_between_refs = generate_github_release_notes.get_commits_between_refs
parse_commit_message = generate_github_release_notes.parse_commit_message
extract_issue_numbers = generate_github_release_notes.extract_issue_numbers
clean_subject = generate_github_release_notes.clean_subject
generate_release_notes = generate_github_release_notes.generate_release_notes
process_commits = generate_github_release_notes.process_commits
format_commit_line = generate_github_release_notes.format_commit_line


class TestReleaseNotesGenerator(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Initialize a git repository
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)

        # Create initial commit
        Path("test.txt").write_text("initial")
        subprocess.run(["git", "add", "test.txt"], check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], check=True)

    def tearDown(self):
        """Clean up test fixtures"""
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.test_dir)

    def test_load_version_config_default(self):
        """Test loading default configuration when .versionrc.json doesn't exist"""
        config = load_version_config()

        self.assertIn("types", config)
        # Note: issuePrefixes and issueUrlFormat are not included by default for security
        self.assertNotIn("issuePrefixes", config)
        self.assertNotIn("issueUrlFormat", config)

        # Check default types
        type_names = [t["type"] for t in config["types"]]
        self.assertIn("feat", type_names)
        self.assertIn("fix", type_names)
        self.assertIn("chore", type_names)

    def test_load_version_config_custom(self):
        """Test loading custom configuration from .versionrc.json"""
        custom_config = {
            "types": [
                {"type": "feat", "section": "New Features"},
                {"type": "fix", "section": "Bug Fixes"},
            ],
            "issuePrefixes": ["TEST-", "CUSTOM-"],
            "issueUrlFormat": "https://example.com/{{prefix}}{{id}}",
        }

        with open(".versionrc.json", "w") as f:
            json.dump(custom_config, f)

        config = load_version_config()

        self.assertEqual(len(config["types"]), 2)
        self.assertEqual(config["types"][0]["section"], "New Features")
        self.assertEqual(config["issuePrefixes"], ["TEST-", "CUSTOM-"])
        self.assertEqual(
            config["issueUrlFormat"], "https://example.com/{{prefix}}{{id}}"
        )

    def test_parse_commit_message_conventional(self):
        """Test parsing conventional commit messages"""
        # Test with scope and PR - function returns tuple now
        commit_type, scope, subject, pr_number = parse_commit_message(
            "feat(DATAGO-123): add new feature (#45)"
        )
        self.assertEqual(commit_type, "feat")
        self.assertEqual(scope, "DATAGO-123")
        self.assertEqual(subject, "add new feature")
        self.assertEqual(pr_number, "45")

        # Test without scope
        commit_type, scope, subject, pr_number = parse_commit_message(
            "fix: resolve bug (#67)"
        )
        self.assertEqual(commit_type, "fix")
        self.assertIsNone(scope)
        self.assertEqual(subject, "resolve bug")
        self.assertEqual(pr_number, "67")

        # Test without PR
        commit_type, scope, subject, pr_number = parse_commit_message(
            "chore: update dependencies"
        )
        self.assertEqual(commit_type, "chore")
        self.assertEqual(subject, "update dependencies")
        self.assertIsNone(pr_number)

    def test_parse_commit_message_non_conventional(self):
        """Test parsing non-conventional commit messages"""
        commit_type, scope, subject, pr_number = parse_commit_message(
            "random commit message"
        )
        self.assertIsNone(commit_type)
        self.assertEqual(subject, "random commit message")

    def test_extract_issue_numbers(self):
        """Test extracting issue numbers from text"""
        # Test single issue
        config = {"issuePrefixes": ["DATAGO-"]}
        issues = extract_issue_numbers("Fix DATAGO-123 issue", config)
        self.assertEqual(issues, ["DATAGO-123"])

        # Test multiple issues
        config = {"issuePrefixes": ["DATAGO-", "MRE-"]}
        issues = extract_issue_numbers("Fix DATAGO-123 and MRE-456", config)
        self.assertEqual(set(issues), {"DATAGO-123", "MRE-456"})

        # Test no issues
        config = {"issuePrefixes": ["DATAGO-"]}
        issues = extract_issue_numbers("No issues here", config)
        self.assertEqual(issues, [])

        # Test duplicates
        config = {"issuePrefixes": ["DATAGO-"]}
        issues = extract_issue_numbers("DATAGO-123 DATAGO-123 DATAGO-456", config)
        self.assertEqual(set(issues), {"DATAGO-123", "DATAGO-456"})

        # Test no config
        config = {}
        issues = extract_issue_numbers("Fix DATAGO-123 issue", config)
        self.assertEqual(issues, [])

    def test_clean_subject(self):
        """Test cleaning commit subjects"""
        # Test removing DATAGO prefix
        config = {"issuePrefixes": ["DATAGO-"]}
        result = clean_subject("DATAGO-123: add new feature", config)
        self.assertEqual(result, "add new feature")

        # Test removing "and DATAGO-XXX"
        config = {"issuePrefixes": ["DATAGO-"]}
        result = clean_subject("and DATAGO-456 implement feature", config)
        self.assertEqual(result, "implement feature")

        # Test removing "and DATAGO-XXX -"
        config = {"issuePrefixes": ["DATAGO-"]}
        result = clean_subject("and DATAGO-789 - fix bug", config)
        self.assertEqual(result, "fix bug")

        # Test multiple issue references
        config = {"issuePrefixes": ["DATAGO-", "MRE-"]}
        result = clean_subject("DATAGO-111: and MRE-222 - implement feature", config)
        self.assertEqual(result, "implement feature")

        # Test no changes needed
        config = {"issuePrefixes": ["DATAGO-"]}
        result = clean_subject("normal commit message", config)
        self.assertEqual(result, "normal commit message")

        # Test no config
        config = {}
        result = clean_subject("DATAGO-123: add new feature", config)
        self.assertEqual(result, "DATAGO-123: add new feature")

    @patch.dict(
        os.environ, {"GITHUB_TOKEN": "fake_token", "GITHUB_REPOSITORY": "test/repo"}
    )
    @patch.object(generate_github_release_notes, "_get_commits_with_prs_graphql")
    def test_get_commits_between_refs_mocked(self, mock_graphql):
        """Test getting commits between git references with mocked GraphQL"""
        # Mock GraphQL response
        mock_commits = [
            {
                "hash": "abc1234",
                "full_hash": "abc1234567890123456789012345678901234567",
                "subject": "fix: resolve issue",
                "author": "Test User",
                "pr_number": "123",
                "changed_files": 2,
                "committed_date": "2023-01-01T00:00:00Z",
                "authored_date": "2023-01-01T00:00:00Z",
                "additions": 10,
                "deletions": 5,
            }
        ]
        mock_graphql.return_value = mock_commits

        # Test the function
        commits = get_commits_between_refs("v1.0.0", "v1.1.0")

        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["subject"], "fix: resolve issue")
        self.assertEqual(commits[0]["author"], "Test User")
        mock_graphql.assert_called_once()

    @patch.dict(
        os.environ, {"GITHUB_TOKEN": "fake_token", "GITHUB_REPOSITORY": "test/repo"}
    )
    @patch.object(generate_github_release_notes, "get_commits_between_refs")
    def test_generate_release_notes_integration(self, mock_get_commits):
        """Test the main release notes generation function"""
        # Mock commits data
        mock_commits = [
            {
                "hash": "abc1234",
                "full_hash": "abc1234567890123456789012345678901234567",
                "subject": "feat(DATAGO-123): add new feature (#45)",
                "author": "John Doe",
                "pr_number": "45",
            },
            {
                "hash": "def5678",
                "full_hash": "def5678901234567890123456789012345678901",
                "subject": "fix: resolve critical bug (#67)",
                "author": "Jane Smith",
                "pr_number": "67",
            },
            {
                "hash": "ghi9012",
                "full_hash": "ghi9012345678901234567890123456789012345",
                "subject": "chore(release): 1.0.0 [ci skip]",
                "author": "CI Bot",
                "pr_number": None,
            },
        ]
        mock_get_commits.return_value = mock_commits

        # Create a custom config
        config = {
            "types": [
                {"type": "feat", "section": "Features"},
                {"type": "fix", "section": "Bug Fixes"},
                {"type": "chore", "section": "Chores"},
            ],
            "issuePrefixes": ["DATAGO-"],
            "issueUrlFormat": "https://example.com/browse/{{prefix}}{{id}}",
        }

        with open(".versionrc.json", "w") as f:
            json.dump(config, f)

        # Generate release notes
        output_file = "test_release_notes.md"
        generate_release_notes("v1.0.0", "v1.1.0", output_file)

        # Check output file exists
        self.assertTrue(Path(output_file).exists())

        # Read and verify content
        content = Path(output_file).read_text()

        # Should contain sections
        self.assertIn("## Features", content)
        self.assertIn("## Bug Fixes", content)

        # Should contain commit information
        self.assertIn("add new feature", content)
        self.assertIn("resolve critical bug", content)

        # Should contain issue links
        self.assertIn("DATAGO-123", content)

        # Should contain PR links
        self.assertIn("#45", content)
        self.assertIn("#67", content)

        # Should NOT contain release commits
        self.assertNotIn("[ci skip]", content)

    def test_github_actions_environment(self):
        """Test behavior in GitHub Actions environment"""
        # Mock GitHub Actions environment variables
        with patch.dict(
            os.environ,
            {
                "GITHUB_REPOSITORY": "test/repo",
                "GITHUB_SERVER_URL": "https://github.com",
            },
        ):
            # Test that the script can handle GitHub environment
            config = load_version_config()
            self.assertIsInstance(config, dict)

    @patch.dict(
        os.environ, {"GITHUB_TOKEN": "fake_token", "GITHUB_REPOSITORY": "test/repo"}
    )
    def test_output_format_consistency(self):
        """Test that output format is consistent"""
        # Mock a single commit
        with patch.object(
            generate_github_release_notes, "get_commits_between_refs"
        ) as mock_get_commits:
            mock_get_commits.return_value = [
                {
                    "hash": "abc1234",
                    "full_hash": "abc1234567890123456789012345678901234567",
                    "subject": "feat(DATAGO-123): add authentication (#42)",
                    "author": "Test Author",
                    "pr_number": "42",
                }
            ]

            # Create config with issue settings
            config = {
                "types": [{"type": "feat", "section": "Features"}],
                "issuePrefixes": ["DATAGO-"],
                "issueUrlFormat": "https://example.com/browse/{{prefix}}{{id}}",
            }
            with open(".versionrc.json", "w") as f:
                json.dump(config, f)

            output_file = "format_test.md"
            generate_release_notes("v1.0.0", "v1.1.0", output_file)

            content = Path(output_file).read_text()

            # Check format: * [`hash`](url) subject ([#PR](url)) (author) ([ISSUE](url))
            self.assertRegex(
                content,
                r"\* \[`[a-f0-9]{7}`\]\(.*\) add authentication \(\[#42\]\(.*\)\) \(Test Author\) \(\[DATAGO-123\]\(.*\)\)",
            )

    def test_ui_changes_detection(self):
        """Test UI changes detection functionality"""
        # Mock commits with UI bump commits
        mock_commits = [
            {
                "hash": "abc1234",
                "full_hash": "abc1234567890123456789012345678901234567",
                "subject": "feat: add new UI feature",
                "author": "UI Developer",
                "pr_number": "100",
            },
            {
                "hash": "def5678",
                "full_hash": "def5678901234567890123456789012345678901",
                "subject": "bump version to ui-v1.0.0 [skip ci]",
                "author": "CI Bot",
                "pr_number": None,
            },
            {
                "hash": "ghi9012",
                "full_hash": "ghi9012345678901234567890123456789012345",
                "subject": "fix: backend bug fix",
                "author": "Backend Developer",
                "pr_number": "101",
            },
        ]

        # Config with UI changes enabled
        config = {
            "types": [
                {"type": "feat", "section": "Features"},
                {"type": "fix", "section": "Bug Fixes"},
            ],
            "uiChanges": {
                "enabled": True,
                "tagPrefix": "ui-v",
                "bumpCommitPattern": r"bump version to ui-v.*\[skip ci\]",
            },
        }

        # Test UI detection
        type_sections, ui_sections = process_commits(mock_commits, config)

        # Should have UI section
        self.assertEqual(len(ui_sections), 1)
        version_range = list(ui_sections.keys())[0]
        self.assertIn("ui-v1.0.0", version_range)

        # UI section should contain the UI feature commit
        ui_feat_commits = ui_sections[version_range]["feat"]["commits"]
        self.assertEqual(len(ui_feat_commits), 1)
        self.assertIn("add new UI feature", ui_feat_commits[0]["subject"])

        # Main sections should contain the backend fix
        main_fix_commits = type_sections["fix"]["commits"]
        self.assertEqual(len(main_fix_commits), 1)
        self.assertIn("backend bug fix", main_fix_commits[0]["subject"])

    def test_process_commits_functionality(self):
        """Test the process_commits function"""
        mock_commits = [
            {
                "hash": "abc1234",
                "full_hash": "abc1234567890123456789012345678901234567",
                "subject": "feat(DATAGO-123): new feature (#1)",
                "author": "Developer",
                "pr_number": "1",
            },
            {
                "hash": "def5678",
                "full_hash": "def5678901234567890123456789012345678901",
                "subject": "fix: bug fix (#2)",
                "author": "Developer",
                "pr_number": "2",
            },
            {
                "hash": "ghi9012",
                "full_hash": "ghi9012345678901234567890123456789012345",
                "subject": "chore(release): 1.0.0 [ci skip]",
                "author": "CI Bot",
                "pr_number": None,
            },
        ]

        config = {
            "types": [
                {"type": "feat", "section": "Features"},
                {"type": "fix", "section": "Bug Fixes"},
                {"type": "chore", "section": "Chores"},
            ],
            "issuePrefixes": ["DATAGO-"],
        }

        type_sections, ui_sections = process_commits(mock_commits, config)

        # Check that commits are properly categorized
        self.assertEqual(len(type_sections["feat"]["commits"]), 1)
        self.assertEqual(len(type_sections["fix"]["commits"]), 1)
        self.assertEqual(
            len(type_sections["chore"]["commits"]), 0
        )  # [ci skip] should be filtered

        # Check commit processing
        feat_commit = type_sections["feat"]["commits"][0]
        self.assertEqual(
            feat_commit["subject"], "new feature"
        )  # DATAGO-123 should be cleaned
        self.assertEqual(feat_commit["pr_number"], "1")
        self.assertEqual(feat_commit["issue_numbers"], ["DATAGO-123"])

    def test_format_commit_line(self):
        """Test commit line formatting"""
        commit = {
            "hash": "abc1234",
            "full_hash": "abc1234567890123456789012345678901234567",
            "subject": "add new feature",
            "author": "Test Author",
            "pr_number": "42",
            "issue_numbers": ["DATAGO-123"],
        }

        config = {
            "issuePrefixes": ["DATAGO-"],
            "issueUrlFormat": "https://example.com/browse/{{prefix}}{{id}}",
        }

        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "test/repo"}):
            line = format_commit_line(commit, config)

            # Should contain all elements
            self.assertIn("abc1234", line)
            self.assertIn("add new feature", line)
            self.assertIn("Test Author", line)
            self.assertIn("#42", line)
            self.assertIn("DATAGO-123", line)
            self.assertIn("https://github.com/test/repo/commit/", line)
            self.assertIn("https://github.com/test/repo/pull/42", line)
            self.assertIn("https://example.com/browse/DATAGO-123", line)


class TestCommandLineInterface(unittest.TestCase):
    """Test the command line interface"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)

        # Create initial commit
        Path("test.txt").write_text("initial")
        subprocess.run(["git", "add", "test.txt"], check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], check=True)

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.test_dir)

    @patch.dict(
        os.environ, {"GITHUB_TOKEN": "fake_token", "GITHUB_REPOSITORY": "test/repo"}
    )
    def test_command_line_args(self):
        """Test command line argument parsing with mocked API calls"""
        # Test directly calling the function with mocked commits
        # (subprocess testing doesn't work well with mocks)
        
        with patch.object(
            generate_github_release_notes, "get_commits_between_refs"
        ) as mock_get_commits:
            # Test with empty commits - should not create file
            mock_get_commits.return_value = []
            
            output_file = "test_output_empty.md"
            generate_release_notes("v1.0.0", "v1.1.0", output_file)
            
            # With new behavior: no file created when no commits
            self.assertFalse(Path(output_file).exists())
            
            # Test with some commits - should create file
            mock_get_commits.return_value = [
                {
                    "hash": "abc1234",
                    "full_hash": "abc1234567890",
                    "subject": "feat: add new feature",
                    "author": "Test Author",
                    "pr_number": "42",
                }
            ]
            
            output_file2 = "test_output_with_commits.md"
            generate_release_notes("v1.0.0", "v1.1.0", output_file2)
            
            # Should create file when commits exist
            self.assertTrue(Path(output_file2).exists())
            
            # Verify file contains expected content
            content = Path(output_file2).read_text()
            self.assertIn("Features", content)
            self.assertIn("add new feature", content)


if __name__ == "__main__":
    unittest.main()
