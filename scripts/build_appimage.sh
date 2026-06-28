#!/bin/bash
#
# Build the DWARF Alpaca Control Center as a portable Linux AppImage.
#
# Steps:
#   1. Freeze the PySide6 GUI with PyInstaller using the shared spec.
#   2. Assemble an AppDir (binary + .desktop + icon + AppRun).
#   3. Wrap it into dist/DwarfAlpacaGUI-x86_64.AppImage with appimagetool.
#
# Prerequisites: python3 + pip, pyinstaller, protoc (for gen_pb2.sh), and the
# system libraries PySide6 needs at runtime (libGL, libEGL, xcb-*). FUSE is
# required to *run* the resulting AppImage; appimagetool itself is downloaded
# here and run via its embedded runtime.
set -euo pipefail

SCRIPT_PATH="$(realpath -- "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

ARCH="${ARCH:-x86_64}"
APP_NAME="DwarfAlpacaGUI"
DIST_DIR="$REPO_DIR/dist"
APPDIR="$DIST_DIR/AppDir"
APPIMAGETOOL_VERSION="${APPIMAGETOOL_VERSION:-continuous}"
APPIMAGETOOL="$DIST_DIR/appimagetool-$ARCH.AppImage"

cd "$REPO_DIR"

echo "==> Ensuring generated protobuf modules exist"
if ! ls "$REPO_DIR"/src/dwarf_alpaca/proto/*_pb2.py >/dev/null 2>&1; then
    bash "$REPO_DIR/gen_pb2.sh"
fi

echo "==> Freezing GUI with PyInstaller"
pyinstaller --noconfirm packaging/dwarf_alpaca_gui.spec

echo "==> Assembling AppDir at $APPDIR"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

install -m 0755 "$DIST_DIR/$APP_NAME" "$APPDIR/usr/bin/$APP_NAME"

# Desktop entry (required at the AppDir root and conventionally also under usr/share)
cp "$REPO_DIR/packaging/dwarf-alpaca-gui.desktop" "$APPDIR/dwarf-alpaca-gui.desktop"
cp "$REPO_DIR/packaging/dwarf-alpaca-gui.desktop" "$APPDIR/usr/share/applications/"

# Icon (top-level icon name must match the desktop entry's Icon= key)
cp "$REPO_DIR/images/dwarfalplogo.png" "$APPDIR/dwarfalplogo.png"
cp "$REPO_DIR/images/dwarfalplogo.png" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps/dwarfalplogo.png"

# AppRun launcher
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/DwarfAlpacaGUI" "$@"
EOF
chmod +x "$APPDIR/AppRun"

echo "==> Fetching appimagetool ($APPIMAGETOOL_VERSION)"
if [ ! -x "$APPIMAGETOOL" ]; then
    curl -fsSL -o "$APPIMAGETOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/$APPIMAGETOOL_VERSION/appimagetool-$ARCH.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

echo "==> Building AppImage"
OUTPUT="$DIST_DIR/$APP_NAME-$ARCH.AppImage"
# --appimage-extract-and-run avoids needing FUSE just to *build* the image.
ARCH="$ARCH" "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUTPUT"

echo "==> Done: $OUTPUT"
