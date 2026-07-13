#!/bin/sh
# Placeholder wrapper for future repository secret/PII scanning.
# This script is intentionally a no-op until project-specific scanners are added.
set -eu
cd "$(dirname "$0")/.."
case "${1:-}" in
  --help|-h)
    echo "Usage: $0 [--staged|--all|--worktree]"
    echo "Currently a placeholder for future secrets/PII scanning tools."
    exit 0
    ;;
  *)
    echo "No scanner configured yet. Please add a secrets audit script to .githooks or scripts/." >&2
    exit 0
    ;;
esac
