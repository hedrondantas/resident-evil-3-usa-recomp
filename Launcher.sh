#!/bin/sh
# Resident Evil 3: Nemesis (USA) Recompiled — Linux entry point.
#
# Opens the game's launcher (the one inside the executable). On a fresh
# checkout, launcher/bootstrap.py first builds that executable as a setup host;
# its wizard then takes the disc and the BIOS and recompiles the game. Nothing
# is installed system-wide and no password is asked: the portable toolchain
# (CMake, Clang, SDL3, Python) lives in ~/.local/share/retcomm.
#
#   ./Launcher.sh                      open the launcher
#   ./Launcher.sh --rebuild-launcher   rebuild the executable, then open it

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd) || exit 1
EXE="$ROOT/build-release/Resident_Evil_3_Nemesis_USA_Recompiled"
TOOLCHAIN_URL="https://github.com/TechnicallyComputers/retcomm-toolchains/releases/latest/download/cmake-clang-v1-linux-x64.zip"
PACK_LATEST="${XDG_DATA_HOME:-$HOME/.local/share}/retcomm/toolchains/cmake-clang-v1/latest"

fail() {
    echo "Launcher: $1" >&2
    if [ ! -t 2 ]; then
        if command -v zenity >/dev/null 2>&1; then
            zenity --error --title="Resident Evil 3: Nemesis Recompiled" --width=520 --text="$1" 2>/dev/null
        elif command -v kdialog >/dev/null 2>&1; then
            kdialog --title "Resident Evil 3: Nemesis Recompiled" --error "$1" 2>/dev/null
        elif command -v notify-send >/dev/null 2>&1; then
            notify-send "Resident Evil 3: Nemesis Recompiled" "$1" 2>/dev/null
        fi
    fi
    exit 1
}

# Fast path: the executable exists, so its launcher handles everything.
if [ -x "$EXE" ] && [ "${1:-}" != "--rebuild-launcher" ]; then
    cd "$ROOT/build-release" || exit 1
    exec "$EXE" "$@"
fi

python_ok() {
    "$1" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null
}

# 1. A system Python 3.11+ (no tkinter or other packages needed).
PY=""
for candidate in python3 python3.14 python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
        PY=$candidate
        break
    fi
done

# 2. The Python inside an already installed toolchain pack.
if [ -z "$PY" ] && [ -x "$PACK_LATEST/python/bin/python3" ] &&
    python_ok "$PACK_LATEST/python/bin/python3"; then
    PY="$PACK_LATEST/python/bin/python3"
fi

# 3. No Python at all: download the pack and run its Python. bootstrap.py
#    installs the same zip into the shared cache (RE3_TOOLCHAIN_ZIP).
if [ -z "$PY" ]; then
    TMP=$(mktemp -d) || fail "Could not create a temporary folder."
    trap 'rm -rf "$TMP"' EXIT
    ZIP="$TMP/cmake-clang-v1-linux-x64.zip"
    echo "Downloading the portable toolchain..."
    if command -v curl >/dev/null 2>&1; then
        curl -fL --progress-bar -o "$ZIP" "$TOOLCHAIN_URL" || fail "Download failed: $TOOLCHAIN_URL"
    elif command -v wget >/dev/null 2>&1; then
        wget -q --show-progress -O "$ZIP" "$TOOLCHAIN_URL" || fail "Download failed: $TOOLCHAIN_URL"
    else
        fail "Python 3.11+ was not found, and neither curl nor wget is available to download the toolchain."
    fi
    if command -v unzip >/dev/null 2>&1; then
        unzip -q "$ZIP" -d "$TMP/pack" || fail "Could not extract the toolchain."
    elif command -v bsdtar >/dev/null 2>&1; then
        mkdir -p "$TMP/pack" && bsdtar -xf "$ZIP" -C "$TMP/pack" || fail "Could not extract the toolchain."
    else
        fail "Python 3.11+ was not found, and neither unzip nor bsdtar is available to extract the toolchain."
    fi
    PACK_PY=$(find "$TMP/pack" -path '*/python/bin/python3' | head -n 1)
    [ -n "$PACK_PY" ] || fail "The toolchain archive has no Python."
    chmod +x "$(dirname "$PACK_PY")"/* 2>/dev/null
    python_ok "$PACK_PY" || fail "The toolchain's Python does not run on this system."
    PY=$PACK_PY
    export RE3_TOOLCHAIN_ZIP="$ZIP"
    "$PY" "$ROOT/launcher/bootstrap.py" "$@"
    exit $?
fi

exec "$PY" "$ROOT/launcher/bootstrap.py" "$@"
