#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_DIR="$HOME/Library/Application Support/Undistract"
CHROME_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
FIREFOX_DIR="$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"
CHROME_PROFILE_DIR="$HOME/Library/Application Support/Google/Chrome/Default"

CHROME_EXTENSION_PATH="$REPO_DIR/extensions/chrome"
FIREFOX_EXTENSION_ID="undistract@local"

mkdir -p "$APP_DIR" "$CHROME_DIR" "$FIREFOX_DIR"

# --- Resolve the venv entry point ---
HOST_BIN="$REPO_DIR/desktop/.venv/bin/undistract-native-host"
if [[ ! -x "$HOST_BIN" ]]; then
  echo "ERROR: Native host entry point not found at $HOST_BIN"
  echo "Run: uv sync --project desktop"
  exit 1
fi
echo "Found native host entry point: $HOST_BIN"

# --- Write the native host wrapper with the absolute path baked in ---
HOST_PATH="$APP_DIR/undistract-native-host"
sed "s|__HOST_BIN__|$HOST_BIN|g" "$SCRIPT_DIR/undistract-native-host" > "$HOST_PATH"
chmod +x "$HOST_PATH"
echo "Installed native host wrapper to $HOST_PATH"

# --- Resolve Chrome extension ID ---
# Accept as first argument, or auto-detect from Chrome profile
CHROME_EXTENSION_ID="${1:-}"

if [[ -z "$CHROME_EXTENSION_ID" && -f "$CHROME_PROFILE_DIR/Preferences" ]]; then
  CHROME_EXTENSION_ID="$(CHROME_PROFILE_DIR="$CHROME_PROFILE_DIR" CHROME_EXTENSION_PATH="$CHROME_EXTENSION_PATH" /usr/bin/python3 - <<'PY'
import json
from pathlib import Path
import os

chrome_profile = Path(os.environ["CHROME_PROFILE_DIR"])
prefs = chrome_profile / "Preferences"
ext_path = Path(os.environ["CHROME_EXTENSION_PATH"]).resolve()

try:
    data = json.loads(prefs.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)

settings = data.get("extensions", {}).get("settings", {})
for ext_id, info in settings.items():
    path = info.get("path")
    if not path:
        continue
    try:
        if Path(path).resolve() == ext_path:
            print(ext_id)
            raise SystemExit(0)
    except Exception:
        continue
print("")
PY
)"
fi

if [[ -z "$CHROME_EXTENSION_ID" ]]; then
  echo ""
  echo "ERROR: Could not detect Chrome extension ID."
  echo "Either:"
  echo "  1. Load the unpacked extension in Chrome first, then re-run this script."
  echo "  2. Pass the ID as an argument:  $0 <chrome-extension-id>"
  echo ""
  echo "To find the ID: open chrome://extensions, enable Developer mode,"
  echo "and copy the ID shown under the extension name."
  exit 1
fi

echo "Chrome extension ID: $CHROME_EXTENSION_ID"

# --- Write Chrome native messaging manifest ---
cat > "$CHROME_DIR/undistract.native_host.json" <<EOF
{
  "name": "undistract.native_host",
  "description": "Undistract native messaging host",
  "path": "$HOST_PATH",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$CHROME_EXTENSION_ID/"]
}
EOF

# --- Write Firefox native messaging manifest ---
cat > "$FIREFOX_DIR/undistract.native_host.json" <<EOF
{
  "name": "undistract.native_host",
  "description": "Undistract native messaging host",
  "path": "$HOST_PATH",
  "type": "stdio",
  "allowed_extensions": ["$FIREFOX_EXTENSION_ID"]
}
EOF

echo "Installed Chrome manifest to $CHROME_DIR/undistract.native_host.json"
echo "Installed Firefox manifest to $FIREFOX_DIR/undistract.native_host.json"
echo ""
echo "Done! Restart Chrome and/or Firefox for native messaging to take effect."
