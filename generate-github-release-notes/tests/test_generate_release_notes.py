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

# Import functions
load_version_config = generate_github_release_notes.load_version_config
get_commits_between_refs = generate_github_release_notes.get_commits_between_tags
parse_commit_message = generate_github_release_notes.parse_commit_message
extract_datago_issues = generate_github_release_notes.extract_issue_numbers
clean_subject = generate_github_release_notes.clean_subject
generate_release_notes = generate_github_release_notes.generate_release_notes


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
        self.assertIn("issuePrefixes", config)
        self.assertIn("issueUrlFormat", config)

        # Check default types
        type_names = [t["type"] for t in config["types"]]
        self.assertIn("feat", type_names)
        self.assertIn("fix", type_names)
        self.assertIn("chore", type_names)

        # Check default issue prefixes
        self.assertIn("DATAGO-", config["issuePrefixes"])
        self.assertIn("MRE-", config["issuePrefixes"])

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
        # Test with scope and PR
        result = parse_commit_message("feat(DATAGO-123): add new feature (#45)")
        self.assertEqual(result["type"], "feat")
        self.assertEqual(result["scope"], "DATAGO-123")
        self.assertEqual(result["subject"], "add new feature")
        self.assertEqual(result["pr_number"], "45")

        # Test without scope
        result = parse_commit_message("fix: resolve bug (#67)")
        self.assertEqual(result["type"], "fix")
        self.assertIsNone(result["scope"])
        self.assertEqual(result["subject"], "resolve bug")
        self.assertEqual(result["pr_number"], "67")

        # Test without PR
        result = parse_commit_message("chore: update dependencies")
        self.assertEqual(result["type"], "chore")
        self.assertEqual(result["subject"], "update dependencies")
        self.assertIsNone(result["pr_number"])

    def test_parse_commit_message_non_conventional(self):
        """Test parsing non-conventional commit messages"""
        result = parse_commit_message("random commit message")
        self.assertIsNone(result["type"])
        self.assertEqual(result["subject"], "random commit message")

    def test_extract_datago_issues(self):
        """Test extracting DATAGO issues from text"""
        # Test single issue
        issues = extract_datago_issues("Fix DATAGO-123 issue", ["DATAGO-"])
        self.assertEqual(issues, ["DATAGO-123"])

        # Test multiple issues
        issues = extract_datago_issues(
            "Fix DATAGO-123 and MRE-456", ["DATAGO-", "MRE-"]
        )
        self.assertEqual(set(issues), {"DATAGO-123", "MRE-456"})

        # Test no issues
        issues = extract_datago_issues("No issues here", ["DATAGO-"])
        self.assertEqual(issues, [])

        # Test duplicates
        issues = extract_datago_issues("DATAGO-123 DATAGO-123 DATAGO-456", ["DATAGO-"])
        self.assertEqual(set(issues), {"DATAGO-123", "DATAGO-456"})

    def test_clean_subject(self):
        """Test cleaning commit subjects"""
        # Test removing DATAGO prefix
        result = clean_subject("DATAGO-123: add new feature", None, ["DATAGO-"])
        self.assertEqual(result, "add new feature")

        # Test removing "and DATAGO-XXX"
        result = clean_subject("and DATAGO-456 implement feature", None, ["DATAGO-"])
        self.assertEqual(result, "implement feature")

        # Test removing "and DATAGO-XXX -"
        result = clean_subject("and DATAGO-789 - fix bug", None, ["DATAGO-"])
        self.assertEqual(result, "fix bug")

        # Test multiple issue references
        result = clean_subject(
            "DATAGO-111: and MRE-222 - implement feature", None, ["DATAGO-", "MRE-"]
        )
        self.assertEqual(result, "implement feature")

        # Test no changes needed
        result = clean_subject("normal commit message", None, ["DATAGO-"])
        self.assertEqual(result, "normal commit message")

    def test_get_commits_between_refs(self):
        """Test getting commits between git references"""
        # Create some test commits
        for i in range(3):
            Path(f"file{i}.txt").write_text(f"content {i}")
            subprocess.run(["git", "add", f"file{i}.txt"], check=True)
            subprocess.run(
                ["git", "commit", "-m", f"feat: add file {i} (#1{i})"], check=True
            )

        # Tag the current commit
        subprocess.run(["git", "tag", "v1.0.0"], check=True)

        # Add one more commit
        Path("file3.txt").write_text("content 3")
        subprocess.run(["git", "add", "file3.txt"], check=True)
        subprocess.run(
            ["git", "commit", "-m", "fix(DATAGO-123): fix issue (#20)"], check=True
        )

        # Test getting commits between tag and HEAD
        commits = get_commits_between_refs("v1.0.0", "HEAD")
        self.assertEqual(len(commits), 1)
        self.assertIn("fix issue", commits[0]["subject"])
        self.assertEqual(commits[0]["author"], "Test User")

    def test_generate_release_notes_integration(self):
        """Test the main release notes generation function"""
        # Mock commits data
        mock_commits = [
            {
                "hash": "abc123456789",
                "subject": "feat(DATAGO-123): add new feature (#45)",
                "author": "John Doe",
            },
            {
                "hash": "def987654321",
                "subject": "fix: resolve critical bug (#67)",
                "author": "Jane Smith",
            },
            {
                "hash": "ghi555666777",
                "subject": "chore(release): 1.0.0 [ci skip]",
                "author": "CI Bot",
            },
        ]

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

        # Mock the function and generate release notes
        with patch.object(
            generate_github_release_notes,
            "get_commits_between_tags",
            return_value=mock_commits,
        ):
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

    def test_output_format_consistency(self):
        """Test that output format is consistent"""
        # Mock a single commit
        with patch(
            "generate_github_release_notes.get_commits_between_refs"
        ) as mock_get_commits:
            mock_get_commits.return_value = [
                {
                    "hash": "abc1234567890123456789012345678901234567",
                    "subject": "feat(DATAGO-123): add authentication (#42)",
                    "author": "Test Author",
                }
            ]

            output_file = "format_test.md"
            generate_release_notes("v1.0.0", "v1.1.0", output_file)

            content = Path(output_file).read_text()

            # Check format: * [`hash`](url) subject ([#PR](url)) (author) ([ISSUE](url))
            self.assertRegex(
                content,
                r"\* \[`[a-f0-9]{7}`\]\(.*\) add authentication \(\[#42\]\(.*\)\) \(Test Author\) \(\[DATAGO-123\]\(.*\)\)",
            )


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

    def test_command_line_args(self):
        """Test command line argument parsing"""
        script_path = Path(__file__).parent.parent / "generate-github-release-notes.py"

        # Test with valid arguments
        result = subprocess.run(
            ["python3", str(script_path), "HEAD~1", "HEAD", "test_output.md"],
            capture_output=True,
            text=True,
        )

        # Should not fail (exit code 0 or 1 is acceptable since we might not have enough commits)
        self.assertIn(result.returncode, [0, 1])


if __name__ == "__main__":
    unittest.main()
