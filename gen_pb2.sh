#!/usr/bin/env bash
set -euo pipefail

# Compatibility wrapper. The Python generator is canonical because it uses the
# locked grpcio-tools version and rewrites imports for package-relative use.
SCRIPT_PATH="$(realpath -- "${BASH_SOURCE[0]}")"
REPO_DIR="$(dirname "$SCRIPT_PATH")"
cd "$REPO_DIR"
uv run python scripts/generate_protos.py "$@"
