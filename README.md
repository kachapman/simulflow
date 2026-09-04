# USB Desktop Extend

Turn your Android tablet into a second monitor over USB — no WiFi, no dummy adapters, no extra hardware.

Uses GNOME Remote Desktop's extend mode + ADB reverse tunneling to create a virtual second display that you can drag windows to, just like a real monitor.

![Terminal Theme](https://img.shields.io/badge/theme-terminal%20green-black) ![Python](https://img.shields.io/badge/python-3.10+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **One-click connect** — detect tablet, configure RDP, create tunnel
- **Real-time log** — see exactly what's happening at each step
- **System tray** — minimize to tray, quick connect/disconnect
- **Terminal theme** — green-on-black aesthetic with info tooltips
- **Credentials in UI** — set your own RDP username/password, saved between sessions

## How It Works

```
┌─────────────┐    USB Cable    ┌─────────────┐
│   Laptop    │◄───────────────►│   Tablet    │
│  (Fedora)   │    ADB tunnel   │ (Android)   │
│             │    :3389        │  RDP Client │
│  GNOME RDP  │────────────────►│             │
│  Extend Mode│  display stream │  127.0.0.1  │
└─────────────┘                 └─────────────┘
```

1. **ADB detection** — finds your tablet via USB
2. **Service setup** — disables conflicting system RDP, enables user-level Desktop Sharing in extend mode
3. **Tunnel** — `adb reverse tcp:3389 tcp:3389` routes the tablet's RDP client to your laptop
4. **Extend** — GNOME creates a virtual monitor; drag windows between screens freely

## Requirements

- **OS:** Fedora 40+ (GNOME/Wayland)
- **Python:** 3.10+
- **Tablet:** Android with USB Debugging enabled
- **USB cable:** USB-C to USB-C (or adapter)

> **Note:** On GNOME 49+, the Microsoft Windows App RDP client cannot connect due to GNOME's switch to RDSTLS security. Use aRDP or Remmina on the tablet instead (see Troubleshooting).

### System Packages

```bash
# ADB (Android Debug Bridge)
sudo dnf install -y android-tools

# GNOME Remote Desktop (usually pre-installed)
sudo dnf install -y gnome-remote-desktop
```

### Tablet Setup

1. Enable **Developer Options** (tap Build Number 7 times)
2. Enable **USB Debugging** in Developer Options
3. Connect USB cable and tap **Allow** on the authorization prompt

## Installation

### Option 1: pip install (recommended)

```bash
git clone https://github.com/kachapman/linux-usb-desktop-extend.git
cd linux-usb-desktop-extend
pip install -e .
```

This installs the `usb-desktop-extend` command globally.

### Option 2: Run directly

```bash
python -m usb_desktop_extend
```

### Option 3: Pre-built binary

Download `usb-desktop-extend` from [Releases](https://github.com/kachapman/linux-usb-desktop-extend/releases) and run it directly — no Python needed.

## Usage

1. Connect your tablet via USB
2. Run the app:
   ```bash
   usb-desktop-extend
   ```
3. Enter your sudo password when prompted
4. Enter your desired RDP username and password in the app (these are the credentials your tablet will use to connect)
5. Click **START CONNECTION**
6. On your tablet, open an RDP client (aRDP or Remmina recommended) and connect to:
   - **PC Name:** `127.0.0.1`
   - **Port:** `3389`
   - **Username:** (the same username you entered in the app)
   - **Password:** (the same password you entered in the app)
7. Accept the certificate warning on first connect
8. Drag windows to the tablet — it's your second screen!

The credentials you enter in the app are set as your GNOME RDP credentials and used by the tablet to authenticate.

Credentials are saved to `~/.config/usb-desktop-extend/config.json` after the first successful connection.

> **Note:** The app automatically enables GNOME Desktop Sharing via `grdctl rdp enable`. You can also manually configure sharing in **GNOME Settings → Sharing**, but this is not required — the app handles it for you.

### Wireless (no USB cable)

You can also connect over Wi-Fi using Android 11+ **Wireless debugging** instead of a USB cable. Select the **Wireless** mode at the top of the app. Pairing only needs to happen once — the app auto-connects to a previously paired tablet on the same network.

#### QR code pairing (recommended)

The app pairs the tablet by QR code — no typing required:

1. On the tablet, enable **Developer Options** (Settings → About → tap "Build number" 7 times)
2. Enable **USB Debugging** under Developer Options (required for the first pairing)
3. Go to **Settings → Developer Options → Wireless debugging** and turn it **on**
4. In the app (Wireless mode), click **START CONNECTION** — the app shows a QR code
5. On the tablet, tap **"Pair device with QR code"** (next to the pairing code option) and scan the code shown by the app
6. The app discovers the tablet over mDNS, pairs, connects, and sets up the tunnel automatically
7. Open your RDP client on the tablet and connect to `127.0.0.1:3389` as usual

Pairing persists across reboots. Already-paired tablets are detected automatically on the same network.

#### Manual pairing (fallback)

If mDNS is blocked on your network, expand **"Manual entry"** in the wireless panel before starting, then enter:

- **Tablet IP** — from either Wireless debugging screen
- **Pair port + code** — from the "Pair device with pairing code" screen
- **Connect port** — from the Wireless debugging main screen

Click **START CONNECTION**. The app pairs, connects, and sets up the tunnel automatically.

> **Note:** "protocol fault (couldn't read status message): Success" during pairing is usually a harmless race — pairing often still succeeds. The app continues to connect; if it doesn't work, reopen the pairing screen and retry.

> **Note:** Wireless is a **convenience mode, not a quality upgrade**. It has higher latency and more artifacts than a USB cable — for smooth dragging and 60 fps content, prefer USB. Try lowering the RDP client's resolution/color depth on the tablet if streaming feels rough.

### Disconnecting

Click **STOP CONNECTION** in the app. This removes the tunnel, disables RDP, and (in Wireless mode) disconnects the adb device. You can also just unplug the USB cable.

## Building the Binary

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name usb-desktop-extend \
  --icon=assets/icon.png --add-data "assets/icon.png:assets" \
  run_app.py
```

Output: `dist/usb-desktop-extend` (~62 MB)

### AppImage

You can also build a single-file AppImage that runs anywhere without installation:

```bash
./build-appimage.sh
```

Output: `dist/usb-desktop-extend-x86_64.AppImage`

**Prerequisites:** `python3`, `pip` with `PyInstaller`, and `curl`. No FUSE is required to *build* (the script runs appimagetool in extract-and-run mode).

**Run the AppImage:**

```bash
chmod +x dist/usb-desktop-extend-x86_64.AppImage
./dist/usb-desktop-extend-x86_64.AppImage
```

On Fedora you may need `libfuse2` installed to run AppImages:

```bash
sudo dnf install libfuse2
```

If FUSE is unavailable, run with `--appimage-extract-and-run`:

```bash
./dist/usb-desktop-extend-x86_64.AppImage --appimage-extract-and-run
```

> **Note:** The AppImage bundles the PyQt6 GUI but still calls host-system tools (`adb`, `grdctl`, `gsettings`, etc.) from your `PATH` at runtime, so all functionality is unchanged.

## Project Structure

```
linux-usb-desktop-extend/
├── usb_desktop_extend/
│   ├── __init__.py          # Package metadata
│   ├── __main__.py          # python -m entry point
│   ├── main.py              # CLI entry point with sudo prompt
│   ├── app.py               # PyQt6 GUI (terminal theme)
│   ├── backend.py           # Connection logic (ADB/RDP/GNOME)
│   └── log_handler.py       # Logging → GUI signal bridge
├── assets/
│   └── icon.png             # App icon
├── run_app.py               # Standalone entry point for PyInstaller
├── build-appimage.sh        # Build a standalone AppImage
├── setup.py                 # pip install support
├── requirements.txt         # Dependencies
├── usb-desktop-extend.desktop  # Linux desktop entry
├── CHANGELOG.md
└── README.md
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Port 3389 conflict | Both system and user RDP running | The app disables system-level Remote Login automatically |
| Tablet not detected | USB Debugging off | Enable in Settings → Developer Options |
| "unauthorized" in ADB | Tablet not authorized | Tap "Allow" on tablet's USB debugging prompt |
| Connection refused | RDP not enabled | Check `grdctl status` — app handles this automatically |
| Black screen on tablet | Wrong RDP mode | App sets extend mode; restart if needed |
| Windows App can't connect (GNOME 49+) | GNOME 49 switched to RDSTLS security, which the Windows App doesn't negotiate | Use aRDP or Remmina instead |
| Can't find tablet on Wi-Fi | Wi-Fi AP/client isolation blocks device-to-device traffic | Use the same network; disable guest network isolation |
| "protocol fault (couldn't read status message): Success" on pairing | Usually a harmless race — pairing often actually succeeded | Let the app continue; if it fails, reopen the pairing screen and retry |
| Wireless pair fails after reboot | Pairing port changed | Reopen "Pair device with pairing code" (or "Pair device with QR code") for a fresh pairing session |
| Wireless pair times out | Tablet pairing screen closed or expired | Reopen Settings → Developer Options → Wireless debugging → Pair device with QR code / pairing code |
| mDNS discovery not working | mDNS (UDP 5353) blocked on the network | Expand "Manual entry" and enter the tablet IP/ports to connect manually |

## Credits

- Built for Fedora 43 + GNOME 47
- Tested with Xiaomi tablets and Microsoft RDP client (pre-GNOME 49)
- Terminal theme inspired by classic CRT monitors

## License

MIT
