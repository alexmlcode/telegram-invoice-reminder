#!/bin/bash
# Ouroboros rollback script — reverts to a known-good commit.
# Called by verify.py when health checks fail.
#
# Owned by root, deployed to /opt/ouroboros-verifier/.
# The agent (user 'a') can READ but CANNOT modify this file.
#
# Usage: rollback.sh <known_good_sha>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/config.json"
RETRY_FILE="$SCRIPT_DIR/retry_count.txt"

# Read config
REPO_DIR=$(python3 -c "import json; print(json.load(open('$CONFIG'))['repo_dir'])")
WORKING_DIR=$(python3 -c "import json; print(json.load(open('$CONFIG'))['working_dir'])")

KNOWN_GOOD_SHA="${1:-}"

if [ -z "$KNOWN_GOOD_SHA" ]; then
    echo "[rollback] ERROR: No SHA provided"
    exit 1
fi

echo "[rollback] Target SHA: $KNOWN_GOOD_SHA"

# Increment retry counter
RETRIES=0
if [ -f "$RETRY_FILE" ]; then
    RETRIES=$(cat "$RETRY_FILE" 2>/dev/null || echo "0")
fi
RETRIES=$((RETRIES + 1))
echo "$RETRIES" > "$RETRY_FILE"
echo "[rollback] Retry count: $RETRIES"

# Reset repo to known-good SHA
echo "[rollback] Resetting repo $REPO_DIR to $KNOWN_GOOD_SHA..."
cd "$REPO_DIR"
git fetch origin 2>/dev/null || true
git reset --hard "$KNOWN_GOOD_SHA"
git clean -fd

# Sync working directory (exclude runtime files)
echo "[rollback] Syncing $REPO_DIR -> $WORKING_DIR..."
rsync -a --delete \
    --exclude '.env' \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    --exclude 'state/' \
    --exclude 'logs/' \
    --exclude 'memory/' \
    "$REPO_DIR/" "$WORKING_DIR/"

# Clear bytecode cache
find "$WORKING_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo "[rollback] Rollback complete. Restarting service..."

# Restart the service
systemctl restart ouroboros.service
