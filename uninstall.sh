#!/usr/bin/env bash

# Stop and remove the session-index-viewer launchd agent.
# Kills the running server, removes the plist, and deletes the log file.

set -euo pipefail

label="dev.session-index-viewer"
plist_path="$HOME/Library/LaunchAgents/$label.plist"
log_path="$HOME/Library/Logs/session-index-viewer.log"

# Remove the launchd agent (stops the kept-alive process).
launchctl bootout "gui/$UID/$label" 2>/dev/null || true

# Force-kill any lingering server process on the port.
lsof -ti :7333 2>/dev/null | xargs kill -9 2>/dev/null || true

# Clean up the plist and log file.
rm -f "$plist_path" "$log_path"

echo "Uninstalled $label"
