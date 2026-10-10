# AI Crypto Tracker

Kripto-, tőzsdei, nyersanyag- és deviza-elemző asztali program: Yahoo Finance adatok,
RSI/MACD/Bollinger, gyertyadiagram alakzatfelismeréssel, gépi tanulásos előrejelzés,
Telegram/Discord értesítés és opcionális AI-kommentár (Claude / OpenAI).

## Telepítés

### Linux

```bash
./telepites.sh
```

- A programot a `~/.local/share/ai-crypto-tracker/` mappába másolja.
- Menübejegyzést és ikont készít, és terminálból is indítható: `ai-crypto-tracker`.
- Ha a rendszer Pythonjában megvan minden csomag (requests, numpy, scikit-learn,
  PySide6), azt használja. Ha valami hiányzik, saját környezetet (venv) készít
  és oda telepíti őket.
- Eltávolítás: `./telepites.sh --eltavolitas`. A beállítások és az előzmények
  (`~/.config/ai-cripto-tracker/`) ilyenkor megmaradnak.

Frissítéshez elég újra futtatni a `./telepites.sh`-t.

### Windows

1. Telepítsd a Pythont (3.10 vagy újabb) és az [Inno Setup 6](https://jrsoftware.org/isdl.php)-ot.
2. Futtasd a `build.bat`-ot.
3. Az eredmény: `dist\AI-Crypto-Tracker-telepito.exe`. Ezzel bármelyik gépre
   telepíthető, rendszergazdai jog nélkül.

## Indítás forrásból

```bash
./run-tracker.sh            # grafikus felület
./run-tracker.sh --cli      # parancssori elemzés
```

## Adatok helye

Minden beállítás, előzmény és az élő mód CSV-je itt van:
`~/.config/ai-cripto-tracker/` (Windowson: `%USERPROFILE%\.config\ai-cripto-tracker\`).
