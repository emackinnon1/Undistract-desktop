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

HOST_PATH="$APP_DIR/undistract-native-host"

CHROME_EXTENSION_ID=""
if [[ -f "$CHROME_PROFILE_DIR/Preferences" ]]; then
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
  echo "Could not detect Chrome extension ID."
  echo "Load the unpacked extension from $CHROME_EXTENSION_PATH in Chrome, then re-run this script."
  exit 1
fi

cat > "$APP_DIR/undistract-native-host.json" <<'JSON'
{
  "name": "undistract.native_host",
  "description": "Undistract native messaging host",
  "path": "__HOST_PATH__",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://__CHROME_EXTENSION_ID__/"]
}
JSON

cat > "$APP_DIR/undistract-native-host.firefox.json" <<'JSON'
{
  "name": "undistract.native_host",
  "description": "Undistract native messaging host",
  "path": "__HOST_PATH__",
  "type": "stdio",
  "allowed_extensions": ["__FIREFOX_EXTENSION_ID__"]
}
JSON

sed -i '' "s|__HOST_PATH__|$HOST_PATH|g" "$APP_DIR/undistract-native-host.json"
sed -i '' "s|__HOST_PATH__|$HOST_PATH|g" "$APP_DIR/undistract-native-host.firefox.json"
sed -i '' "s|__CHROME_EXTENSION_ID__|$CHROME_EXTENSION_ID|g" "$APP_DIR/undistract-native-host.json"
sed -i '' "s|__FIREFOX_EXTENSION_ID__|$FIREFOX_EXTENSION_ID|g" "$APP_DIR/undistract-native-host.firefox.json"

cp "$APP_DIR/undistract-native-host.json" "$CHROME_DIR/undistract.native_host.json"
cp "$APP_DIR/undistract-native-host.firefox.json" "$FIREFOX_DIR/undistract.native_host.json"

echo "Installed manifests for Chrome extension ID: $CHROME_EXTENSION_ID"
echo "Firefox extension ID: $FIREFOX_EXTENSION_ID"
