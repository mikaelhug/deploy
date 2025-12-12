#!/bin/bash
set -e

# Load environment variables from .env file
if [ -f .env ]; then
    source .env
fi

BASE_DIR="${BASE_DIR:-/opt/docker-fleet}"
cd "$BASE_DIR"

echo "--- Starting Deploy Updater ---"

# Capture the previous commit hash BEFORE updating
PREV_COMMIT=$(git rev-parse HEAD)

# Update the repo
echo ">> Updating repository..."
git fetch origin main
git reset --hard origin/main

# Capture the current commit hash AFTER updating
CURRENT_COMMIT=$(git rev-parse HEAD)

echo ">> Launching Worker..."
exec python3 "deploy.py" "$PREV_COMMIT" "$CURRENT_COMMIT" "$BASE_DIR"
