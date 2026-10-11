#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PY="ai-crypto-tracker.py"
ISS="windows/telepito.iss"

usage() {
    cat <<EOF
AI Crypto Tracker – kiadás a GitHubra

Használat:
  ./kiadas.sh --javitas [-m "leírás"]   2.0.0 → 2.0.1
  ./kiadas.sh --funkcio [-m "leírás"]   2.0.0 → 2.1.0
  ./kiadas.sh --fo      [-m "leírás"]   2.0.0 → 3.0.0
  ./kiadas.sh X.Y.Z     [-m "leírás"]   pontos verzió

Lépések: verziószám átírása ($PY + $ISS) → ellenőrzés → commit → v-tag →
push → GitHub-kiadás az $PY csatolásával (ezt tölti le a program frissítője).
EOF
}

die() { printf '\033[1;31m ✗\033[0m %s\n' "$*" >&2; exit 1; }
ok()  { printf '\033[1;32m ✓\033[0m %s\n' "$*"; }

[[ $# -ge 1 ]] || { usage; exit 2; }
BUMP="$1"; shift
NOTES=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -m) NOTES="${2:-}"; shift 2 ;;
        *) usage; exit 2 ;;
    esac
done

CUR="$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' "$PY")"
[[ -n "$CUR" ]] || die "Nem találom az APP_VERSION-t a $PY-ban."
IFS=. read -r MA MI PA <<<"$CUR"
case "$BUMP" in
    --javitas) NEW="$MA.$MI.$((PA + 1))" ;;
    --funkcio) NEW="$MA.$((MI + 1)).0" ;;
    --fo)      NEW="$((MA + 1)).0.0" ;;
    -h|--help) usage; exit 0 ;;
    [0-9]*.[0-9]*.[0-9]*) NEW="$BUMP" ;;
    *) usage; exit 2 ;;
esac

command -v gh >/dev/null || die "A gh (GitHub CLI) nincs telepítve."
gh auth status >/dev/null 2>&1 || die "A gh nincs bejelentkezve: gh auth login"
[[ "$(git branch --show-current)" == "main" ]] || die "Csak a main ágról adok ki."
git diff --quiet && git diff --cached --quiet || die "Vannak nem commitolt változások – előbb commitold őket."
git rev-parse "v$NEW" >/dev/null 2>&1 && die "A v$NEW tag már létezik."

echo "Kiadás: $CUR → $NEW"
sed -i "s/^APP_VERSION = \".*\"$/APP_VERSION = \"$NEW\"/" "$PY"
sed -i "s/^#define AppVersion \".*\"/#define AppVersion \"$NEW\"/" "$ISS"
python3 -c "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())" "$PY" || die "Szintaktikai hiba a $PY-ban."
python3 "$PY" --help >/dev/null || die "A program nem indul (--help)."
ok "Verzió átírva és ellenőrizve."

git add "$PY" "$ISS"
git commit -q -m "Kiadás v$NEW"
git tag -a "v$NEW" -m "AI Crypto Tracker v$NEW"
git push -q origin main
git push -q origin "v$NEW"
ok "Feltöltve: main + v$NEW."

[[ -n "$NOTES" ]] || NOTES="AI Crypto Tracker v$NEW"
if [[ -f docs/screenshot.png ]]; then
    NOTES="![AI Crypto Tracker](https://raw.githubusercontent.com/Botirocky/ai-crypto-tracker/main/docs/screenshot.png)

$NOTES"
fi
gh release create "v$NEW" "$PY" --title "AI Crypto Tracker v$NEW" --notes "$NOTES" --latest
ok "GitHub-kiadás kész: v$NEW – a telepített programok a Menü → Frissítések keresése alatt megtalálják."
