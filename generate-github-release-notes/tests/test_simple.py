#!/usr/bin/env python3
"""
Simple tests for generate-github-release-notes action
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestSimpleReleaseNotes(unittest.TestCase):
    """Simple tests that don't require complex mocking"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Initialize git repository
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)

        # Create initial commit
        Path("initial.txt").write_text("initial content")
        subprocess.run(["git", "add", "initial.txt"], check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], check=True)

    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.test_dir)

    def test_script_runs_without_error(self):
        """Test that the script runs without error"""
        script_path = Path(__file__).parent.parent / "generate-github-release-notes.py"

        # Create some test commits
        commits = [
            "feat(DATAGO-123): add authentication feature (#1)",
            "fix: resolve login bug (#2)",
            "chore: update dependencies",
        ]

        for i, commit_msg in enumerate(commits):
            file_path = Path(f"test{i}.txt")
            file_path.write_text(f"Test content {i}")
            subprocess.run(["git", "add", str(file_path)], check=True)
            subprocess.run(["git", "commit", "-m", commit_msg], check=True)

            if i == 1:  # Tag after second commit
                subprocess.run(["git", "tag", "v1.0.0"], check=True)

        # Run the script
        result = subprocess.run(
            ["python3", str(script_path), "v1.0.0", "HEAD", "test-output.md"],
            capture_output=True,
            text=True,
        )

        # Check it ran successfully
        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        # Check output file was created
        output_file = Path("test-output.md")
        self.assertTrue(output_file.exists(), "Output file was not created")

        # Check basic content
        content = output_file.read_text()
        # Only chore commit should be after v1.0.0 tag
        self.assertIn("## Chores", content)
        self.assertIn("update dependencies", content)

    def test_script_with_custom_config(self):
        """Test script with custom configuration"""
        script_path = Path(__file__).parent.parent / "generate-github-release-notes.py"

        # Create custom config
        config = {
            "types": [
                {"type": "feat", "section": "New Features"},
                {"type": "fix", "section": "Bug Fixes"},
            ],
            "issuePrefixes": ["TEST-", "CUSTOM-"],
            "issueUrlFormat": "https://example.com/browse/{{prefix}}{{id}}",
        }

        config_file = Path(".versionrc.json")
        config_file.write_text(json.dumps(config, indent=2))

        # Create test commits
        Path("feature.txt").write_text("feature content")
        subprocess.run(["git", "add", "feature.txt"], check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat(TEST-100): add test feature (#10)"],
            check=True,
        )

        subprocess.run(["git", "tag", "v1.0.0"], check=True)

        Path("bugfix.txt").write_text("bugfix content")
        subprocess.run(["git", "add", "bugfix.txt"], check=True)
        subprocess.run(
            ["git", "commit", "-m", "fix(CUSTOM-200): fix test bug (#11)"], check=True
        )

        # Run the script
        result = subprocess.run(
            ["python3", str(script_path), "v1.0.0", "HEAD", "custom-output.md"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        # Check output
        output_file = Path("custom-output.md")
        self.assertTrue(output_file.exists())

        content = output_file.read_text()
        self.assertIn("## Bug Fixes", content)  # Custom section name
        # TEST-100 was before the tag, so only CUSTOM-200 should be in the output
        self.assertIn("CUSTOM-200", content)
        self.assertIn("example.com/browse", content)  # Custom URL format

    def test_script_handles_no_commits(self):
        """Test script handles case with no commits between refs"""
        script_path = Path(__file__).parent.parent / "generate-github-release-notes.py"

        # Run script with same from and to refs (no commits between)
        result = subprocess.run(
            ["python3", str(script_path), "HEAD", "HEAD", "no-commits.md"],
            capture_output=True,
            text=True,
        )

        # Should handle gracefully (exit code 0 or 1 is acceptable)
        self.assertIn(result.returncode, [0, 1])

        # If file was created, it should indicate no commits
        output_file = Path("no-commits.md")
        if output_file.exists():
            content = output_file.read_text()
            self.assertIn("No commits found", content)

    def test_script_help(self):
        """Test script shows help"""
        script_path = Path(__file__).parent.parent / "generate-github-release-notes.py"

        result = subprocess.run(
            ["python3", str(script_path), "--help"], capture_output=True, text=True
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout.lower())
        self.assertIn("from_tag", result.stdout)
        self.assertIn("to_tag", result.stdout)


if __name__ == "__main__":
    unittest.main()
