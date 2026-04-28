#!/bin/bash
set -e
# Ensure tmpfs secret dir exists and is locked down.
mkdir -p /tmp/secrets
chmod 700 /tmp/secrets
exec "$@"
