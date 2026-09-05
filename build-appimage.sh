#!/usr/bin/env bash
set -euo pipefail

# Build a self-contained AppImage from source.
#
# Produces: dist/simulflow-x86_64.AppImage
#
# Requires: python3, pip (with PyInstaller), and the build-appimage host tools.
# No FUSE needed to build (appimagetool runs with --appimage-extract-and-run).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="simulflow"
ARCH="x86_64"
BUILD_DIR="build/AppDir"
DIST_DIR="dist"
CACHE_DIR=".cache/appimagetool"

APPIMAGE_TOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"

echo "==> Building binary with PyInstaller..."
python -m PyInstaller --noconfirm simulflow.spec

echo "==> Preparing AppDir..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

cp "$DIST_DIR/$APP_NAME" "$BUILD_DIR/$APP_NAME"

cat > "$BUILD_DIR/AppRun" <<EOF
#!/bin/sh
SELF="\$(readlink -f "\$0")"
exec "\$(dirname "\$SELF")/$APP_NAME"
EOF
chmod +x "$BUILD_DIR/AppRun"

cat > "$BUILD_DIR/$APP_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Simulflow
GenericName=Linux Desktop Extender
Comment=Turn your Android tablet into a second monitor over USB
Exec=$APP_NAME
Icon=$APP_NAME
Terminal=false
Categories=Utility;
Keywords=tablet;monitor;extend;display;adb;rdp;
EOF

cp "assets/icon.png" "$BUILD_DIR/$APP_NAME.png"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/512x512/apps"
cp "assets/icon.png" "$BUILD_DIR/usr/share/icons/hicolor/512x512/apps/$APP_NAME.png"

echo "==> Fetching appimagetool..."
mkdir -p "$CACHE_DIR"
APPIMAGE_TOOL="$CACHE_DIR/appimagetool-${ARCH}.AppImage"
if [ ! -f "$APPIMAGE_TOOL" ]; then
    curl -L -o "$APPIMAGE_TOOL" "$APPIMAGE_TOOL_URL"
fi
chmod +x "$APPIMAGE_TOOL"

echo "==> Bundling AppImage..."
mkdir -p "$DIST_DIR"
APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE_TOOL" "$BUILD_DIR" "$DIST_DIR/${APP_NAME}-${ARCH}.AppImage"

echo "==> Done: $DIST_DIR/${APP_NAME}-${ARCH}.AppImage"
