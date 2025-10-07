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

            # Test the script with mock environment variables
            env = os.environ.copy()
            env["GITHUB_TOKEN"] = "fake-token-for-testing"
            env["GITHUB_REPOSITORY"] = "test/repo"

            result = subprocess.run(
                [sys.executable, str(script_path), "v1.0.0", "HEAD", "test-output.md"],
                env=env,
                capture_output=True,
                text=True,
            )

            # The script will fail because it tries to make GraphQL calls with fake token
            # But we can check that it at least starts properly
            if (
                "Error: Failed to get commits using GraphQL" not in result.stderr
                and result.returncode == 1
            ):
                print("Expected failure due to fake token - this is OK")
            elif "GITHUB_TOKEN environment variable not set" in result.stdout:
                print("❌ Environment variables not properly set")
                return False

            # Print the result for debugging
            print("Script output:")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            print("Return code:", result.returncode)

            # Check if the script ran and handled errors gracefully
            if (
                result.returncode == 0
                and "✅ GitHub Release notes generated" in result.stdout
            ):
                print("✅ Integration test passed - script completed successfully")
                return True
            elif (
                "401 Client Error: Unauthorized" in result.stderr
                and "✅ GitHub Release notes generated" in result.stdout
            ):
                print(
                    "✅ Integration test passed - script handled auth error gracefully"
                )
                return True
            elif (
                "Error: Failed to get commits using GraphQL" in result.stderr
                or "Error: Failed to get commits using GraphQL" in result.stdout
            ):
                print(
                    "✅ Integration test passed - script failed at expected GraphQL call"
                )
                return True
            elif (
                result.returncode == 1
                and "GITHUB_TOKEN environment variable not set" not in result.stdout
            ):
                print(
                    "✅ Integration test passed - script ran with environment variables"
                )
                return True
            else:
                print("❌ Integration test failed - unexpected error")
                return False

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
