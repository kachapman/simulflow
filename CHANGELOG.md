# Changelog

All notable changes to Simulflow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.0.0] - 2026-09-05

### Changed

- **Rebranded to Simulflow** — the project has been renamed from USB Desktop Extend to Simulflow (a Dune-inspired name: multiple data streams flowing into one coherent display). All UI strings, config paths, CLI commands, and packaging references now use `simulflow`.
- **Config path** — credentials have moved to `~/.config/simulflow/config.json`; existing `~/.config/usb-desktop-extend/config.json` is automatically migrated on first launch.
- **AppImage** — output is now `dist/simulflow-x86_64.AppImage`; the icon is the new Simulflow branding (green merge streams on dark background).
- **Show/hide password toggle** — the saved RDP password field now includes an eye icon to reveal or mask the password in-app.

## [1.1.0] - 2026-09-04

### Added

- **Wireless mode** — Connect over Android 11+ wireless debugging (no USB cable). New USB/Wireless radio selector, an in-app wireless pairing panel with a full setup tooltip, and automatic `adb pair` / `adb connect` / `adb disconnect`.
- **QR code pairing** — Wireless pairing is now QR-first: the app generates a `WIFI:T:ADB;...` QR code (new `qrcode`/`Pillow`/`zeroconf` deps), the tablet scans it via "Pair device with QR code", and the app discovers the tablet over mDNS and pairs automatically — no IP/port/code typing. Manual entry is kept behind a collapsible "Manual entry" section for networks where mDNS is blocked.
- **GNOME 49 warning** — Detects the GNOME version and warns in the log and footer that the Microsoft Windows App RDP client cannot connect on GNOME 49+ (RDSTLS security change), recommending aRDP or Remmina.
- **AppImage build** — New `build-appimage.sh` produces a self-contained `dist/simulflow-x86_64.AppImage` (with explicit `AppRun`) that runs anywhere via libfuse or `--appimage-extract-and-run`.

### Changed

- **Serial-aware ADB commands** — All `adb` commands now target a specific device via `adb -s <serial>` with `adb` first in the command line, so connecting over both USB and wireless simultaneously (which makes the tablet appear twice in `adb devices`) no longer fails with "more than one device/emulator" or `No such file or directory: '-s'`.
- **QR code shown immediately** — Wireless mode generates the QR code before polling or auto-connect attempts, so the pairing dialog appears instantly and the same credentials are reused throughout (the QR never changes mid-scan).
- **Auto-connect to previously paired tablet is best-effort** — mDNS discovery timeout reduced to 3s; if the advertised IP is stale (e.g. after switching Wi-Fi networks) the app explains this and pairs fresh via QR.
- **Transport-aware tablet detection** — `_detect_tablet()` filters devices by connection mode (USB vs wireless) to avoid picking up stale entries from the other transport.
- **`protocol fault` pairing errors** — The app explains that `protocol fault (couldn't read status message): Success` is usually a race where pairing actually succeeded, and continues to connect instead of giving up.
- **Mode switching cancels in-progress connections** — Switching USB/Wireless stops any running connection thread and closes the QR dialog, so USB mode is no longer blocked by a background wireless attempt. Pressing START during an active connection now shows a message instead of doing nothing.
- **Wireless panel hint** — The wireless panel now states up front that QR code generation is the default and to press START CONNECTION, with manual entry as a fallback for blocked mDNS.

### Fixed

- **Duplicate log lines** — Backend messages (e.g. the GNOME 49 warning) were shown twice because `_log()` both emitted a Qt signal and routed through Python logging. The redundant logging call was removed.
- **Stale thread signals** — `_on_finished` now ignores signals from a previous connection manager, preventing an old thread's result from clobbering a newer connection's state.

### Docs

- **README** — Added a "Wireless (no USB cable)" usage section with the full pairing steps (QR + manual fallback) and a note that wireless is a convenience mode (higher latency/artifacts), plus new troubleshooting rows for Wi-Fi pairing issues.
- **README** — Documents the GNOME 49+ / Windows App incompatibility in Requirements, Usage, Troubleshooting, and Credits, and the AppImage build/run steps.
- **CHANGELOG** — Version 1.1.0.

## [Future]

- **Monitor position customization** — Choose whether the virtual extend monitor appears on the left, right, above, or below the primary display at connection time (via `org.gnome.Mutter.DisplayConfig`).

## [0.1.1] - 2026-08-11

### Fixed

- **Connection loss after suspend/resume** — Added health check monitor that verifies ADB tunnel and RDP port every 10 seconds, with automatic reconnection
- **Stale tunnel on app exit** — Added atexit handler and SIGTERM/SIGINT signal handlers to always clean up ADB reverse tunnels
- **RDP service not restarting properly** — Added verification step after initial setup and automatic gnome-remote-desktop restart on failure

### Changed

- Footer text now says "Tunnel Connected. Connect with your RDP app on the tablet" instead of "Connected. Drag windows between screens freely"
- Tooltip hover delay reduced from ~700ms to 100ms
- Close button now shows dialog: "Disconnect & Quit" / "Minimize to Tray" / Cancel (instead of always minimizing)

### Added

- Health check monitor (10s interval) verifies tablet, tunnel, and RDP port after connection
- Auto-reconnect: restarts gnome-remote-desktop and re-establishes ADB tunnel on failure
- Connection lost notification with specific failure reason
- `connection_lost` signal for UI notification when connection fails permanently
- `_verify_rdp_connectivity()` tests actual TCP connection, not just port state

## [0.1.0] - 2026-08-10

### Added

- **GUI application** with PyQt6
  - Main window with credentials, status indicators, connect/disconnect buttons
  - Real-time log output with color-coded messages
  - System tray integration (minimize to tray, quick actions)
- **Terminal theme** (green-on-black aesthetic)
  - Full CSS stylesheet with monospace fonts
  - Styled input fields, buttons, scrollbars, tooltips
- **Info icons** with hover tooltips
  - Credentials section — explains RDP auth defaults
  - ADB indicator — "Enable USB Debugging in Settings → Developer Options"
  - RDP indicator — explains GNOME Remote Desktop extend mode
  - Tunnel indicator — explains ADB reverse tunnel bypass
  - Log area — describes what the log shows
  - Start/Stop buttons — detailed step-by-step descriptions
- **Footer status bar** showing connection state
- **Binary packaging** via PyInstaller (`dist/simulflow`)
- **Installation** via `pip install -e .` with `simulflow` command
- **Desktop entry** (`simulflow.desktop`) for Linux app launchers
- **Documentation** — README, CHANGELOG, AGENTS.md

### Fixed

- Removed `self._emit_status.adb = False` bug that caused crash on connect
