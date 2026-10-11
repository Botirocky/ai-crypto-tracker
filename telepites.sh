#!/usr/bin/env bash
set -euo pipefail

APP_ID="ai-crypto-tracker"
APP_NAME="AI Crypto Tracker"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$DATA_HOME/$APP_ID"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/$APP_ID"
DESKTOP_FILE="$DATA_HOME/applications/$APP_ID.desktop"
ICON_PNG="$DATA_HOME/icons/hicolor/256x256/apps/$APP_ID.png"
ICON_SVG="$DATA_HOME/icons/hicolor/scalable/apps/$APP_ID.svg"
CONFIG_DIR="$HOME/.config/ai-cripto-tracker"
MODULES=(requests numpy sklearn PySide6)

usage() {
    cat <<EOF
$APP_NAME – telepítő

Használat:
  ./telepites.sh               telepítés vagy frissítés
  ./telepites.sh --eltavolitas eltávolítás (a beállítások és előzmények megmaradnak)
  ./telepites.sh --help        ez a súgó

Telepítés helye: $INSTALL_DIR
Indítás:         menüből („$APP_NAME”) vagy terminálból: $APP_ID
EOF
}

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m ✗\033[0m %s\n' "$*" >&2; exit 1; }

pick_python() {
    local c
    for c in /usr/bin/python3 python3; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
            command -v "$c"
            return 0
        fi
    done
    return 1
}

missing_modules() {
    local py="$1" m out=()
    for m in "${MODULES[@]}"; do
        "$py" -c "import $m" >/dev/null 2>&1 || out+=("$m")
    done
    echo "${out[@]:-}"
}

distro_hint() {
    if command -v pacman >/dev/null 2>&1; then
        echo "sudo pacman -S --needed python-requests python-numpy python-scikit-learn pyside6"
    elif command -v apt-get >/dev/null 2>&1; then
        echo "sudo apt install python3-venv python3-pip"
    elif command -v dnf >/dev/null 2>&1; then
        echo "sudo dnf install python3-pip"
    fi
}

uninstall() {
    say "$APP_NAME eltávolítása"
    rm -rf "$INSTALL_DIR"
    rm -f "$LAUNCHER" "$DESKTOP_FILE" "$ICON_PNG" "$ICON_SVG"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_HOME/applications" || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true
    ok "Eltávolítva."
    if [[ -d "$CONFIG_DIR" ]]; then
        echo "   A beállítások és előzmények megmaradtak: $CONFIG_DIR"
        echo "   Ha ezekre sincs szükség: rm -rf \"$CONFIG_DIR\""
    fi
}

install_app() {
    [[ -f "$SRC_DIR/ai-crypto-tracker.py" ]] || die "Nem találom az ai-crypto-tracker.py-t a $SRC_DIR mappában."

    say "Python keresése"
    local sys_py
    sys_py="$(pick_python)" || die "Python 3.10 vagy újabb kell. $(distro_hint)"
    ok "$("$sys_py" --version) ($sys_py)"

    say "Fájlok másolása ide: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/assets"
    install -m 644 "$SRC_DIR/ai-crypto-tracker.py" "$INSTALL_DIR/ai-crypto-tracker.py"
    install -m 644 "$SRC_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
    [[ -f "$SRC_DIR/discordbot.zip" ]] && install -m 644 "$SRC_DIR/discordbot.zip" "$INSTALL_DIR/discordbot.zip"
    install -m 644 "$SRC_DIR/assets/icon.png" "$SRC_DIR/assets/icon.svg" "$INSTALL_DIR/assets/"
    ok "Kész."

    say "Függőségek ellenőrzése (${MODULES[*]})"
    local run_py="$sys_py" missing
    missing="$(missing_modules "$sys_py")"
    if [[ -z "$missing" ]]; then
        rm -rf "$INSTALL_DIR/venv"
        ok "Minden megvan a rendszer Pythonjában, külön környezet nem kell."
    else
        warn "Hiányzik: $missing – saját környezetet készítek (venv)."
        if [[ ! -x "$INSTALL_DIR/venv/bin/python" ]]; then
            "$sys_py" -m venv --system-site-packages "$INSTALL_DIR/venv" \
                || die "A venv létrehozása nem sikerült. $(distro_hint)"
        fi
        run_py="$INSTALL_DIR/venv/bin/python"
        "$run_py" -m pip install --quiet --upgrade pip
        "$run_py" -m pip install --quiet -r "$INSTALL_DIR/requirements.txt" \
            || die "A csomagok telepítése nem sikerült (internet kell hozzá)."
        missing="$(missing_modules "$run_py")"
        [[ -z "$missing" ]] || die "Még mindig hiányzik: $missing"
        ok "Függőségek telepítve a saját környezetbe."
    fi

    say "Indító, menübejegyzés és ikon"
    mkdir -p "$BIN_DIR" "$(dirname "$DESKTOP_FILE")" "$(dirname "$ICON_PNG")" "$(dirname "$ICON_SVG")"
    cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec env -u PYTHONHOME -u PYTHONPATH "$run_py" "$INSTALL_DIR/ai-crypto-tracker.py" "\$@"
EOF
    chmod 755 "$LAUNCHER"
    install -m 644 "$SRC_DIR/assets/icon.png" "$ICON_PNG"
    install -m 644 "$SRC_DIR/assets/icon.svg" "$ICON_SVG"
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
GenericName=Eszközelemző
Comment=Kripto-, tőzsdei és deviza-elemző AI előrejelzéssel
Exec=$LAUNCHER
Icon=$APP_ID
Terminal=false
Categories=Office;Finance;
Keywords=crypto;kripto;bitcoin;tőzsde;elemzés;
StartupWMClass=$APP_ID
EOF
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_HOME/applications" || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true
    ok "Kész."

    say "Próbaindítás (parancssori mód)"
    if "$LAUNCHER" --help >/dev/null 2>&1; then
        ok "A program elindul."
    else
        die "A próbaindítás nem sikerült: futtasd kézzel: $LAUNCHER --help"
    fi

    echo
    ok "$APP_NAME telepítve."
    echo "   Indítás: alkalmazásmenü → „$APP_NAME”, vagy terminálból: $APP_ID"
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) warn "A $BIN_DIR nincs a PATH-ban – a menüből így is indul." ;;
    esac
}

case "${1:-}" in
    --eltavolitas|--uninstall) uninstall ;;
    -h|--help) usage ;;
    "") install_app ;;
    *) usage; exit 2 ;;
esac
