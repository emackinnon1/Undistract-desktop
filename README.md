# Undistract Desktop (Prototype)

Browser-only website blocker companion app for macOS.

## What this includes
- PyQt desktop app to manage a domain list and a `blocking` toggle.
- Native Messaging host stub (Chrome/Firefox).
- Chrome MV3 and Firefox extensions (prototype).

## Setup (step by step)

### 1. Install Python dependencies
```bash
uv sync --project desktop --extra dev
```
This creates `desktop/.venv` with all dependencies including `py2app` for building the macOS app bundle.

### 2. Build the macOS application
```bash
installer/build_app.sh
```
This will:
- Build `Undistract.app` using py2app
- Optionally install it to `/Applications/`
- Create a proper macOS app with icon, name, and bundle identifier

**Note:** If you encounter py2app build issues, you can run the app directly from the terminal for development:
```bash
uv run --project desktop undistract
```

For a production install, the app bundle ensures proper macOS integration (correct app name in tray, double-clickable icon, etc.).

### 3. Load the Chrome extension
1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** and select the `extensions/chrome` folder
4. Note the **extension ID** shown under the extension name (a long lowercase string like `abcdefghijklmnopabcdefghijklmnop`)

### 4. Install the Native Messaging host
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

### 5. Restart Chrome
**Close and reopen Chrome completely.** Chrome only reads native messaging manifests at startup.

### 6. Run the desktop app
Open Undistract from Spotlight, Launchpad, or `/Applications/Undistract.app`.

Alternatively, for development/testing:
```bash
uv run --project desktop undistract
```

Add some domains to the blocklist and toggle "Blocking enabled".

The app features:
- **System tray icon**: Click to show/hide the window, access blocking toggle, or quit
- **App icon**: Uses Undistract-logo.png from the repo root
- **Background mode**: Closing the window hides it to the tray instead of quitting
- **BLE device scanning**: Lists nearby Bluetooth devices for future integration
- **Proper macOS integration**: Shows "Undistract" in the menu bar (not "python3.13")

### 7. Enable auto-start at login (optional)
To have Undistract start automatically when you log in:
```bash
chmod +x installer/install_launchagent.sh
installer/install_launchagent.sh install
```

To disable auto-start:
```bash
installer/install_launchagent.sh uninstall
```

The LaunchAgent will automatically use the installed .app bundle if available (preferred), or fall back to the venv binary for development.

### 8. Verify it works
1. Open the Chrome extension's service worker console:  
   `chrome://extensions` → click **service worker** link under the extension
2. You should see the native port connect without errors
3. Try visiting a blocked domain — it should be blocked

### Firefox (optional)
- Go to `about:debugging` → This Firefox → **Load Temporary Add-on** → select `extensions/firefox/manifest.json`
- Firefox uses the fixed ID `undistract@local` (already in the manifest)

## Features
- **System tray integration**: App lives in the macOS menu bar with quick access to blocking toggle
- **Auto-start**: Optional LaunchAgent for launching at login
- **BLE device scanning**: Built-in Bluetooth Low Energy scanner for future hardware integration
- **Native messaging**: Browser extensions communicate with the desktop app via Chrome/Firefox Native Messaging
- **Domain blocking**: Manage a blocklist of domains directly from the desktop app
- **Cross-browser**: Works with both Chrome and Firefox

## Notes
- This is an early prototype; BLE sync is stubbed but wired for future implementation.
- Domain blocking is browser-only.
- Dependency lockfile lives at `desktop/uv.lock`.
- Native messaging manifests are per-user (no admin/root required).
