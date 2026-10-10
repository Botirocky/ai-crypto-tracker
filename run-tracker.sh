#!/usr/bin/env bash
# Az AI Crypto Tracker indítása MINDIG a rendszer-pythonnal (/usr/bin/python3),
# tiszta környezettel — függetlenül attól, melyik interpretert választotta a VS Code.
# A trackerhez a requests/numpy/PySide6/scikit-learn a rendszer-pythonban van (pacman).
cd "$(dirname "$0")" || exit 1
exec env -u PYTHONHOME -u PYTHONPATH /usr/bin/python3 ai-crypto-tracker.py "$@"
