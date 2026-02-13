# Undistract Desktop (Prototype)

Browser-only website blocker companion app for macOS.

## What this includes
- PyQt desktop app to manage a domain list and a `blocking` toggle.
- Native Messaging host stub (Chrome/Firefox).
- Chrome MV3 and Firefox extensions (prototype).

## Setup (step by step)

### 1. Install Python dependencies
```bash
uv sync --project desktop
```
This creates `desktop/.venv` with all dependencies and entry points (`undistract`, `undistract-native-host`).

### 2. Load the Chrome extension
1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** and select the `extensions/chrome` folder
4. Note the **extension ID** shown under the extension name (a long lowercase string like `abcdefghijklmnopabcdefghijklmnop`)

### 3. Install the Native Messaging host
Run the installer, passing the Chrome extension ID:
```bash
chmod +x installer/install_user_manifest.sh installer/undistract-native-host
installer/install_user_manifest.sh <paste-chrome-extension-id-here>
```
Or, if the extension is already loaded in Chrome's Default profile, the installer can auto-detect the ID:
```bash
installer/install_user_manifest.sh
```

This does three things:
- Copies the native host wrapper to `~/Library/Application Support/Undistract/`
- Writes the Chrome manifest to `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/undistract.native_host.json`
- Writes the Firefox manifest to `~/Library/Application Support/Mozilla/NativeMessagingHosts/undistract.native_host.json`

### 4. Restart Chrome
**Close and reopen Chrome completely.** Chrome only reads native messaging manifests at startup.

### 5. Run the desktop app
```bash
uv run --project desktop undistract
```
Add some domains to the blocklist and toggle "Blocking enabled".

### 6. Verify it works
1. Open the Chrome extension's service worker console:  
   `chrome://extensions` → click **service worker** link under the extension
2. You should see the native port connect without errors
3. Try visiting a blocked domain — it should be blocked

### Firefox (optional)
- Go to `about:debugging` → This Firefox → **Load Temporary Add-on** → select `extensions/firefox/manifest.json`
- Firefox uses the fixed ID `undistract@local` (already in the manifest)

## Notes
- This is an early prototype; BLE sync is stubbed but wired for future implementation.
- Domain blocking is browser-only.
- Dependency lockfile lives at `desktop/uv.lock`.
- Native messaging manifests are per-user (no admin/root required).
