#!/bin/bash
set -euo pipefail

###############################################################################
# Test Suite for parse-fossa-params.sh
#
# Usage:
#   ./test-parse-fossa-params.sh
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_PASSED=0
TEST_FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

###############################################################################
# Test Helper Functions
###############################################################################

assert_equals() {
  local expected="$1"
  local actual="$2"
  local test_name="$3"

  if [ "$expected" == "$actual" ]; then
    echo -e "${GREEN}✓${NC} $test_name"
    ((TEST_PASSED++))
    return 0
  else
    echo -e "${RED}✗${NC} $test_name"
    echo "  Expected: $expected"
    echo "  Actual:   $actual"
    ((TEST_FAILED++))
    return 1
  fi
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local test_name="$3"

  if [[ "$haystack" == *"$needle"* ]]; then
    echo -e "${GREEN}✓${NC} $test_name"
    ((TEST_PASSED++))
    return 0
  else
    echo -e "${RED}✗${NC} $test_name"
    echo "  Expected to contain: $needle"
    echo "  Actual: $haystack"
    ((TEST_FAILED++))
    return 1
  fi
}

###############################################################################
# Test Cases
###############################################################################

test_basic_flag_parameter() {
  echo ""
  echo "Test: Basic flag parameter"

  export SCA_FOSSA_ANALYZE_DEBUG="true"
  export FOSSA_PARAMS_CONFIG="$SCRIPT_DIR/fossa-params.json"

  source "$SCRIPT_DIR/parse-fossa-params.sh"
  build_fossa_args > /dev/null

  assert_contains "$FOSSA_CLI_ARGS" "--debug" "Should include --debug flag"

  unset SCA_FOSSA_ANALYZE_DEBUG
  unset FOSSA_CLI_ARGS
}

test_value_parameter() {
  echo ""
  echo "Test: Value parameter"

  export SCA_FOSSA_BRANCH="main"
  export FOSSA_PARAMS_CONFIG="$SCRIPT_DIR/fossa-params.json"

  source "$SCRIPT_DIR/parse-fossa-params.sh"
  build_fossa_args > /dev/null

  assert_contains "$FOSSA_CLI_ARGS" "--branch main" "Should include --branch with value"

  unset SCA_FOSSA_BRANCH
  unset FOSSA_CLI_ARGS
}

test_multiple_parameters() {
  echo ""
  echo "Test: Multiple parameters"

  export SCA_FOSSA_ANALYZE_DEBUG="true"
  export SCA_FOSSA_BRANCH="PR"
  export SCA_FOSSA_REVISION="abc123"
  export SCA_FOSSA_PATH="sam-mongodb"
  export SCA_FOSSA_CONFIG="sam-mongodb/.fossa.yml"
  export FOSSA_PARAMS_CONFIG="$SCRIPT_DIR/fossa-params.json"

  source "$SCRIPT_DIR/parse-fossa-params.sh"
  build_fossa_args > /dev/null

  assert_contains "$FOSSA_CLI_ARGS" "--debug" "Should include --debug"
  assert_contains "$FOSSA_CLI_ARGS" "--branch PR" "Should include --branch PR"
  assert_contains "$FOSSA_CLI_ARGS" "--revision abc123" "Should include --revision"
  assert_contains "$FOSSA_CLI_ARGS" "--path sam-mongodb" "Should include --path"
  assert_contains "$FOSSA_CLI_ARGS" "--config sam-mongodb/.fossa.yml" "Should include --config"

  unset SCA_FOSSA_ANALYZE_DEBUG SCA_FOSSA_BRANCH SCA_FOSSA_REVISION SCA_FOSSA_PATH SCA_FOSSA_CONFIG
  unset FOSSA_CLI_ARGS
}

test_empty_value_not_included() {
  echo ""
  echo "Test: Empty value parameter not included"

  export SCA_FOSSA_BRANCH=""
  export FOSSA_PARAMS_CONFIG="$SCRIPT_DIR/fossa-params.json"

  source "$SCRIPT_DIR/parse-fossa-params.sh"
  build_fossa_args > /dev/null

  if [[ "$FOSSA_CLI_ARGS" == *"--branch"* ]]; then
    echo -e "${RED}✗${NC} Should not include --branch when value is empty"
    echo "  Actual: $FOSSA_CLI_ARGS"
    ((TEST_FAILED++))
  else
    echo -e "${GREEN}✓${NC} Should not include --branch when value is empty"
    ((TEST_PASSED++))
  fi

  unset SCA_FOSSA_BRANCH
  unset FOSSA_CLI_ARGS
}

test_false_flag_not_included() {
  echo ""
  echo "Test: False flag parameter not included"

  export SCA_FOSSA_ANALYZE_DEBUG="false"
  export FOSSA_PARAMS_CONFIG="$SCRIPT_DIR/fossa-params.json"

  source "$SCRIPT_DIR/parse-fossa-params.sh"
  build_fossa_args > /dev/null

  if [[ "$FOSSA_CLI_ARGS" == *"--debug"* ]]; then
    echo -e "${RED}✗${NC} Should not include --debug when set to false"
    echo "  Actual: $FOSSA_CLI_ARGS"
    ((TEST_FAILED++))
  else
    echo -e "${GREEN}✓${NC} Should not include --debug when set to false"
    ((TEST_PASSED++))
  fi

  unset SCA_FOSSA_ANALYZE_DEBUG
  unset FOSSA_CLI_ARGS
}

test_project_parameter() {
  echo ""
  echo "Test: Project parameter"

  export SCA_FOSSA_PROJECT="MyOrg_my-project"
  export FOSSA_PARAMS_CONFIG="$SCRIPT_DIR/fossa-params.json"

  source "$SCRIPT_DIR/parse-fossa-params.sh"
  build_fossa_args > /dev/null

  assert_contains "$FOSSA_CLI_ARGS" "--project MyOrg_my-project" "Should include project override"

  unset SCA_FOSSA_PROJECT
  unset FOSSA_CLI_ARGS
}

test_monorepo_use_case() {
  echo ""
  echo "Test: Monorepo use case (real-world scenario)"

  export SCA_FOSSA_PATH="sam-mongodb"
  export SCA_FOSSA_CONFIG="sam-mongodb/.fossa.yml"
  export SCA_FOSSA_PROJECT="SolaceLabs_sam-mongodb"
  export SCA_FOSSA_BRANCH="PR"
  export SCA_FOSSA_REVISION="feature-branch"
  export FOSSA_PARAMS_CONFIG="$SCRIPT_DIR/fossa-params.json"

  source "$SCRIPT_DIR/parse-fossa-params.sh"
  build_fossa_args > /dev/null

  assert_contains "$FOSSA_CLI_ARGS" "--project SolaceLabs_sam-mongodb" "Should include project name"
  assert_contains "$FOSSA_CLI_ARGS" "--path sam-mongodb" "Should include plugin path"
  assert_contains "$FOSSA_CLI_ARGS" "--config sam-mongodb/.fossa.yml" "Should include plugin config"

  unset SCA_FOSSA_PATH SCA_FOSSA_CONFIG SCA_FOSSA_PROJECT SCA_FOSSA_BRANCH SCA_FOSSA_REVISION
  unset FOSSA_CLI_ARGS
}

###############################################################################
# Run All Tests
###############################################################################

echo "================================================="
echo "🧪 FOSSA Parameter Parser Test Suite"
echo "================================================="

test_basic_flag_parameter
test_value_parameter
test_multiple_parameters
test_empty_value_not_included
test_false_flag_not_included
test_project_parameter
test_monorepo_use_case

echo ""
echo "================================================="
echo "📊 Test Results"
echo "================================================="
echo -e "${GREEN}Passed:${NC} $TEST_PASSED"
echo -e "${RED}Failed:${NC} $TEST_FAILED"
echo "================================================="

if [ $TEST_FAILED -eq 0 ]; then
  echo -e "${GREEN}✅ All tests passed!${NC}"
  exit 0
else
  echo -e "${RED}❌ Some tests failed${NC}"
  exit 1
fi
