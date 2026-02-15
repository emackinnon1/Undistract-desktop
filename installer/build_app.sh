#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DESKTOP_DIR="$REPO_DIR/desktop"
ICON_PATH="$REPO_DIR/Undistract-logo.png"

echo "Building Undistract.app with PyInstaller..."

# Check if icon exists
if [[ ! -f "$ICON_PATH" ]]; then
  echo "ERROR: Icon not found at $ICON_PATH"
  exit 1
fi

cd "$DESKTOP_DIR"

# Ensure PyInstaller is installed
if ! "$DESKTOP_DIR/.venv/bin/python" -c "import PyInstaller" 2>/dev/null; then
  echo "Installing PyInstaller..."
  uv sync --project "$DESKTOP_DIR" --extra dev
fi

# Clean previous builds
rm -rf "$DESKTOP_DIR/build" "$DESKTOP_DIR/dist"

# Build the .app bundle
echo "Running PyInstaller..."
"$DESKTOP_DIR/.venv/bin/pyinstaller" \
  --name="Undistract" \
  --windowed \
  --icon="$ICON_PATH" \
  --add-data="$ICON_PATH:." \
  --osx-bundle-identifier="com.undistract.desktop" \
  --hidden-import=undistract_desktop.blocklist_store \
  --hidden-import=undistract_desktop.websocket_server \
  --clean \
  --noconfirm \
  run_app.py

if [[ ! -d "$DESKTOP_DIR/dist/Undistract.app" ]]; then
  echo "ERROR: Build failed - Undistract.app not found"
  exit 1
fi

echo "✓ Build complete: $DESKTOP_DIR/dist/Undistract.app"

# Optional: Install to /Applications
read -p "Install to /Applications? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  echo "Installing to /Applications..."
  rm -rf "/Applications/Undistract.app"
  cp -R "$DESKTOP_DIR/dist/Undistract.app" "/Applications/"
  echo "✓ Installed to /Applications/Undistract.app"
  echo ""
  echo "You can now:"
  echo "  1. Open Undistract from Spotlight or Launchpad"
  echo "  2. Drag /Applications/Undistract.app to your Dock"
  echo "  3. Create a Desktop alias"
  echo ""
  echo "To enable auto-start at login, run:"
  echo "  installer/install_launchagent.sh install"
fi
