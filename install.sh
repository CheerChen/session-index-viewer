#!/usr/bin/env bash

# Install server.py as a launchd user agent (run at login, keep alive).
# Run once per machine; re-run after moving the repo or changing python3.

set -euo pipefail

label="dev.session-index-viewer"
repo_dir="$(cd "$(dirname "$0")" && pwd)"
plist_path="$HOME/Library/LaunchAgents/$label.plist"
log_path="$HOME/Library/Logs/session-index-viewer.log"
python3_bin="$(command -v python3)"

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$plist_path" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$python3_bin</string>
    <string>$repo_dir/server.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$log_path</string>
  <key>StandardErrorPath</key>
  <string>$log_path</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$UID/$label" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$plist_path"

echo "Installed $label"
echo "  plist: $plist_path"
echo "  log:   $log_path"
echo "  url:   http://localhost:7333"
