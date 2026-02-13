# Undistract Desktop (Prototype)

Browser-only website blocker companion app for macOS.

## What this includes
- PyQt desktop app to manage a domain list and a `blocking` toggle.
- Native Messaging host stub (Chrome/Firefox).
- Chrome MV3 and Firefox extensions (prototype).

## Quick start (using uv)
```bash
uv sync --project desktop
uv run --project desktop undistract
```

## Extension loading (dev)
- Chrome/Chromium: enable developer mode, load unpacked from `extensions/chrome`.
- Firefox: about:debugging → This Firefox → Load Temporary Add-on from `extensions/firefox/manifest.json`.

## Notes
- This is an early prototype; BLE sync is stubbed but wired for future implementation.
- Domain blocking is browser-only.
- Dependency lockfile lives at desktop/uv.lock.

## Native Messaging (optional)
To use Native Messaging, load the extensions first so the installer can detect the Chrome ID, then install per-user manifests:

```bash
cp installer/undistract-native-host "$HOME/Library/Application Support/Undistract/undistract-native-host"
chmod +x "$HOME/Library/Application Support/Undistract/undistract-native-host"
installer/install_user_manifest.sh
```

Firefox uses the fixed ID `undistract@local` from the manifest.
