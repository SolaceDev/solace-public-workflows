#!/usr/bin/env python3
"""
Test runner for generate-github-release-notes action
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, cwd=None, check=True):
    """Run a command and return the result"""
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, cwd=cwd, check=check, capture_output=True, text=True
        )
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        if check:
            raise
        return e


def test_python_script():
    """Test the Python script directly"""
    print("\n" + "=" * 50)
    print("Testing Python Script")
    print("=" * 50)

    # Run unit tests
    try:
        result = run_command(
            [sys.executable, "-m", "unittest", "test_simple.py", "-v"],
            cwd=Path(__file__).parent,
        )
        print("✅ Python unit tests passed")
        return True
    except subprocess.CalledProcessError:
        print("❌ Python unit tests failed")
        return False


def test_integration():
    """Run integration test"""
    print("\n" + "=" * 50)
    print("Testing Integration")
    print("=" * 50)

    action_dir = Path(__file__).parent.parent
    script_path = action_dir / "generate-github-release-notes.py"

    # Create a temporary test repository
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        test_repo = Path(temp_dir) / "test-repo"
        test_repo.mkdir()

        # Initialize git repo
        os.chdir(test_repo)

        try:
            run_command(["git", "init"])
            run_command(["git", "config", "user.name", "Test User"])
            run_command(["git", "config", "user.email", "test@example.com"])

            # Create test commits
            commits = [
                ("file1.txt", "feat(DATAGO-123): add authentication (#1)"),
                ("file2.txt", "fix: resolve login bug (#2)"),
                ("file3.txt", "chore: update dependencies"),
            ]

            for i, (filename, commit_msg) in enumerate(commits):
                Path(filename).write_text(f"Content {i}")
                run_command(["git", "add", filename])
                run_command(["git", "commit", "-m", commit_msg])

                if i == 1:  # Tag after second commit
                    run_command(["git", "tag", "v1.0.0"])

            # Test the script
            run_command(
                [sys.executable, str(script_path), "v1.0.0", "HEAD", "test-output.md"]
            )

            # Check output
            output_file = Path("test-output.md")
            if not output_file.exists():
                print("❌ Output file not created")
                return False

            content = output_file.read_text()
            print("Generated content:")
            print(content)

            # Basic checks - only chore commit should be after v1.0.0 tag
            if "update dependencies" not in content:
                print("❌ Chore commit not found")
                return False

            if "## Chores" not in content:
                print("❌ Chores section not found")
                return False

            print("✅ Integration test passed")
            return True

        except Exception as e:
            print(f"❌ Integration test failed: {e}")
            return False


def main():
    """Main test runner"""
    print("🧪 Running tests for generate-github-release-notes action")

    # Change to the action directory
    Path(__file__).parent.parent
    original_cwd = os.getcwd()

    try:
        results = []

        # Run tests
        results.append(("Python Script", test_python_script()))
        results.append(("Integration", test_integration()))

        # Summary
        print("\n" + "=" * 50)
        print("TEST SUMMARY")
        print("=" * 50)

        all_passed = True
        for test_name, passed in results:
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"{test_name:20} {status}")
            if not passed:
                all_passed = False

        print("\n" + "=" * 50)
        if all_passed:
            print("🎉 All tests passed!")
            return 0
        else:
            print("💥 Some tests failed!")
            return 1

    finally:
        os.chdir(original_cwd)


if __name__ == "__main__":
    sys.exit(main())
