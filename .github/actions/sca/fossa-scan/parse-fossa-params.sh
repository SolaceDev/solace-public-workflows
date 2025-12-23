#!/bin/bash
set -euo pipefail

###############################################################################
# FOSSA Parameter Parser
#
# Reads fossa-params.json and builds CLI arguments from environment variables.
#
# Usage:
#   source parse-fossa-params.sh
#   build_fossa_args
#   echo "$FOSSA_CLI_ARGS"
#
# Environment:
#   FOSSA_PARAMS_CONFIG - Path to fossa-params.json (default: ./fossa-params.json)
#   SCA_FOSSA_* - Various FOSSA configuration variables
#
# Output:
#   FOSSA_CLI_ARGS - Space-separated CLI arguments for FOSSA
###############################################################################

# Default configuration file path
FOSSA_PARAMS_CONFIG="${FOSSA_PARAMS_CONFIG:-$(dirname "${BASH_SOURCE[0]}")/fossa-params.json}"

###############################################################################
# build_fossa_args [command]
#
# Reads JSON configuration and builds FOSSA CLI arguments from environment
# variables. Sets the FOSSA_CLI_ARGS variable with the result.
#
# Parameters:
#   command - Optional FOSSA command to filter parameters by (e.g., "analyze", "test")
#             If not provided, uses all parameters regardless of command.
#
# Returns:
#   0 on success, 1 on error
###############################################################################
build_fossa_args() {
  local filter_command="${1:-}"
  local config_file="$FOSSA_PARAMS_CONFIG"

  # Validate config file exists
  if [ ! -f "$config_file" ]; then
    echo "❌ Error: FOSSA parameters config not found: $config_file" >&2
    return 1
  fi

  # Validate JSON syntax
  if ! jq empty "$config_file" 2>/dev/null; then
    echo "❌ Error: Invalid JSON in $config_file" >&2
    return 1
  fi

  if [ -n "$filter_command" ]; then
    echo "📋 Loading FOSSA '$filter_command' parameter mappings from: $config_file"
  else
    echo "📋 Loading FOSSA parameter mappings from: $config_file"
  fi

  # Initialize output variable
  FOSSA_CLI_ARGS=""

  # Parse JSON and process each parameter
  # Use jq to iterate and output shell-safe commands
  local param_count
  param_count=$(jq -r '.parameters | length' "$config_file")

  for ((i=0; i<param_count; i++)); do
    local env_var cli_flag param_type env_value commands

    env_var=$(jq -r ".parameters[$i].env" "$config_file")
    cli_flag=$(jq -r ".parameters[$i].flag" "$config_file")
    param_type=$(jq -r ".parameters[$i].type" "$config_file")
    commands=$(jq -r ".parameters[$i].commands | join(\",\")" "$config_file")

    # Filter by command if specified
    if [ -n "$filter_command" ]; then
      # Check if this parameter supports the requested command
      if ! echo "$commands" | grep -q "$filter_command"; then
        continue  # Skip this parameter
      fi
    fi

    # Get the environment variable value
    # Use indirect expansion instead of eval for safety and compatibility
    env_value="${!env_var:-}"

    case "$param_type" in
      flag)
        # Boolean flag - only add if explicitly set to "true"
        if [ "$env_value" == "true" ]; then
          # Skip if this is an action-specific parameter (empty flag)
          if [ -n "$cli_flag" ]; then
            FOSSA_CLI_ARGS="$FOSSA_CLI_ARGS $cli_flag"
            echo "  ✓ Enabled: $cli_flag"
          else
            echo "  ✓ Action parameter set: $env_var"
          fi
        fi
        ;;

      value)
        # Flag with value - only add if value is non-empty
        if [ -n "$env_value" ]; then
          # Skip if this is an action-specific parameter (empty flag)
          if [ -n "$cli_flag" ]; then
            FOSSA_CLI_ARGS="$FOSSA_CLI_ARGS $cli_flag $env_value"
            echo "  ✓ Using $cli_flag: $env_value"
          else
            echo "  ✓ Action parameter set: $env_var=$env_value"
          fi
        fi
        ;;

      multi_value)
        # Flag that can be specified multiple times with comma-separated values
        if [ -n "$env_value" ]; then
          # Split by comma and add each value separately
          IFS=',' read -ra VALUES <<< "$env_value"
          for val in "${VALUES[@]}"; do
            # Trim whitespace
            val=$(echo "$val" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            if [ -n "$val" ]; then
              FOSSA_CLI_ARGS="$FOSSA_CLI_ARGS $cli_flag $val"
              echo "  ✓ Using $cli_flag: $val"
            fi
          done
        fi
        ;;

      *)
        echo "  ⚠️  Unknown parameter type '$param_type' for $env_var" >&2
        ;;
    esac
  done

  # Trim leading whitespace
  FOSSA_CLI_ARGS="${FOSSA_CLI_ARGS# }"

  echo "✅ Built FOSSA CLI args: $FOSSA_CLI_ARGS"

  # Export for use in calling scripts
  export FOSSA_CLI_ARGS

  return 0
}

###############################################################################
# print_fossa_config
#
# Pretty-prints the FOSSA parameter configuration for debugging.
###############################################################################
print_fossa_config() {
  local config_file="$FOSSA_PARAMS_CONFIG"

  if [ ! -f "$config_file" ]; then
    echo "❌ Error: Config file not found: $config_file" >&2
    return 1
  fi

  echo "📋 FOSSA Parameter Configuration"
  echo "================================"
  echo ""

  jq -r '.parameters[] | "  \(.env)\n    Flag: \(.flag)\n    Type: \(.type)\n    Desc: \(.description)\n    Example: \(.example)\n"' "$config_file"
}

###############################################################################
# If script is executed directly (not sourced), run build_fossa_args
###############################################################################
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
  build_fossa_args "$@"
fi
