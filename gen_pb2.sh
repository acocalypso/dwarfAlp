#!/bin/bash

SCRIPT_PATH="$(realpath -- "${BASH_SOURCE[0]}")"
REPO_DIR="$(dirname "$SCRIPT_PATH")"
PROTO_DIR="$REPO_DIR/src/dwarf_alpaca/proto"
PROTOC="$(command -v protoc)"
if [ -z "$PROTOC" ]; then
    echo "ERROR: protoc not found. Is protobuf installed?"
    exit 1
fi

"$PROTOC" -I "$PROTO_DIR" --python_out="$PROTO_DIR" "$PROTO_DIR"/*.proto
