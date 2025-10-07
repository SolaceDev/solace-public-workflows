#!/usr/bin/env python3

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the parent directory to the path so we can import the script
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the script as a module
import importlib.util

script_path = Path(__file__).parent.parent / "generate-github-release-notes.py"
spec = importlib.util.spec_from_file_location(
    "generate_github_release_notes", script_path
)
generate_github_release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate_github_release_notes)


class TestBasicFunctionality(unittest.TestCase):
    """Basic tests that don't require complex setup"""

    def test_load_version_config_default(self):
        """Test loading default configuration"""
        config = generate_github_release_notes.load_version_config()
        self.assertIn("types", config)
        self.assertIsInstance(config["types"], list)
        self.assertTrue(len(config["types"]) > 0)

    def test_parse_commit_message(self):
        """Test commit message parsing"""
        # Test conventional commit
        result = generate_github_release_notes.parse_commit_message(
            "feat: add new feature"
        )
        self.assertEqual(result[0], "feat")  # type
        self.assertEqual(result[2], "add new feature")  # subject

        # Test with scope
        result = generate_github_release_notes.parse_commit_message(
            "fix(auth): resolve login issue"
        )
        self.assertEqual(result[0], "fix")  # type
        self.assertEqual(result[1], "auth")  # scope
        self.assertEqual(result[2], "resolve login issue")  # subject

    def test_extract_issue_numbers(self):
        """Test issue number extraction"""
        config = {"issuePrefixes": ["DATAGO-", "TEST-"]}

        # Test single issue
        issues = generate_github_release_notes.extract_issue_numbers(
            "Fix DATAGO-123", config
        )
        self.assertEqual(issues, ["DATAGO-123"])

        # Test multiple issues
        issues = generate_github_release_notes.extract_issue_numbers(
            "Fix DATAGO-123 and TEST-456", config
        )
        self.assertEqual(set(issues), {"DATAGO-123", "TEST-456"})

        # Test no config
        issues = generate_github_release_notes.extract_issue_numbers(
            "Fix DATAGO-123", {}
        )
        self.assertEqual(issues, [])

    def test_clean_subject(self):
        """Test subject cleaning"""
        config = {"issuePrefixes": ["DATAGO-"]}

        # Test removing prefix
        result = generate_github_release_notes.clean_subject(
            "DATAGO-123: add feature", config
        )
        self.assertEqual(result, "add feature")

        # Test no changes needed
        result = generate_github_release_notes.clean_subject("normal commit", config)
        self.assertEqual(result, "normal commit")

    def test_process_commits(self):
        """Test commit processing"""
        commits = [
            {
                "hash": "abc1234",
                "full_hash": "abc1234567890123456789012345678901234567",
                "subject": "feat: new feature",
                "author": "Developer",
                "pr_number": "1",
            },
            {
                "hash": "def5678",
                "full_hash": "def5678901234567890123456789012345678901",
                "subject": "fix: bug fix",
                "author": "Developer",
                "pr_number": "2",
            },
        ]

        config = {
            "types": [
                {"type": "feat", "section": "Features"},
                {"type": "fix", "section": "Bug Fixes"},
            ]
        }

        type_sections, ui_sections = generate_github_release_notes.process_commits(
            commits, config
        )

        # Check sections exist
        self.assertIn("feat", type_sections)
        self.assertIn("fix", type_sections)

        # Check commits are categorized
        self.assertEqual(len(type_sections["feat"]["commits"]), 1)
        self.assertEqual(len(type_sections["fix"]["commits"]), 1)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test/repo"})
    def test_format_commit_line(self):
        """Test commit line formatting"""
        commit = {
            "hash": "abc1234",
            "full_hash": "abc1234567890123456789012345678901234567",
            "subject": "add feature",
            "author": "Developer",
            "pr_number": "42",
            "issue_numbers": [],
        }

        config = {}
        line = generate_github_release_notes.format_commit_line(commit, config)

        # Should contain basic elements
        self.assertIn("abc1234", line)
        self.assertIn("add feature", line)
        self.assertIn("Developer", line)
        self.assertIn("#42", line)


if __name__ == "__main__":
    unittest.main()
