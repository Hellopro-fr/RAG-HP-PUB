#!/bin/sh
set -e

# Ensure the upload directory is writable by appuser. The host volume mount
# can override the image's directory permissions, so we re-apply ownership
# at startup (running as root, before dropping privileges).
UPLOAD_DIR="${UPLOAD_DIR:-/data/uploads}"

if [ -d "$UPLOAD_DIR" ]; then
    chown -R appuser:appuser "$UPLOAD_DIR" 2>/dev/null || true
    mkdir -p "$UPLOAD_DIR/icons" "$UPLOAD_DIR/images"
    chown -R appuser:appuser "$UPLOAD_DIR/icons" "$UPLOAD_DIR/images" 2>/dev/null || true
fi

# Drop to appuser and exec the Go binary
exec su-exec appuser:appuser ./mcp-gateway "$@"
