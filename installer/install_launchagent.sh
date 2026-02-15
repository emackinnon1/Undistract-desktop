#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PLIST_TEMPLATE="$SCRIPT_DIR/com.undistract.desktop.plist"
LAUNCHAGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_DEST="$LAUNCHAGENTS_DIR/com.undistract.desktop.plist"

# Prefer the installed .app bundle, fall back to venv entry point
if [[ -d "/Applications/Undistract.app" ]]; then
  UNDISTRACT_BIN="/Applications/Undistract.app/Contents/MacOS/Undistract"
elif [[ -d "$REPO_DIR/desktop/dist/Undistract.app" ]]; then
  UNDISTRACT_BIN="$REPO_DIR/desktop/dist/Undistract.app/Contents/MacOS/Undistract"
else
  UNDISTRACT_BIN="$REPO_DIR/desktop/.venv/bin/undistract"
fi

if [[ ! -x "$UNDISTRACT_BIN" ]]; then
  echo "ERROR: Undistract binary not found at $UNDISTRACT_BIN"
  echo ""
  echo "Please build and install the app first:"
  echo "  installer/build_app.sh"
  echo ""
  echo "Or run: uv sync --project desktop"
  exit 1
fi

echo "Using Undistract binary: $UNDISTRACT_BIN"

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$LAUNCHAGENTS_DIR"

# Install: substitute the binary path and copy to LaunchAgents
install() {
  echo "Installing LaunchAgent..."
  sed "s|__UNDISTRACT_BIN__|$UNDISTRACT_BIN|g" "$PLIST_TEMPLATE" > "$PLIST_DEST"
  echo "Installed plist to $PLIST_DEST"
  
  # Load the agent
  launchctl load "$PLIST_DEST" 2>/dev/null || true
  echo "LaunchAgent loaded. Undistract will start automatically at login."
  echo ""
  echo "To start now, run: launchctl start com.undistract.desktop"
}

# Uninstall: unload and remove plist
uninstall() {
  echo "Uninstalling LaunchAgent..."
  launchctl unload "$PLIST_DEST" 2>/dev/null || true
  rm -f "$PLIST_DEST"
  echo "LaunchAgent unloaded and removed."
  echo "Undistract will no longer start automatically at login."
}

# Parse command
case "${1:-install}" in
  install)
    install
    ;;
  uninstall)
    uninstall
    ;;
  *)
    echo "Usage: $0 {install|uninstall}"
    echo ""
    echo "  install   - Install and load the LaunchAgent (auto-start at login)"
    echo "  uninstall - Unload and remove the LaunchAgent"
    exit 1
    ;;
esac
