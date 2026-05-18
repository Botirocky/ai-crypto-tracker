import sys
import os
import argparse
import time
import shutil
import subprocess
import csv
import html
import json
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
import requests
import numpy as np


def configure_cross_platform_stdio():
    """
    Windows konzolon a magyar ékezet és az emoji stabilabb megjelenítése (UTF-8).
    Linux/macOS: változatlanul hagyja az alapértelmezett streamet.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

try:
    from PySide6.QtCore import QTimer, QDateTime, Qt, QTime
    from PySide6.QtWidgets import (
        QApplication,
        QWidget,
        QVBoxLayout,
        QPushButton,
        QTextEdit,
        QListWidget,
        QLabel,
        QHBoxLayout,
        QGridLayout,
        QAbstractItemView,
        QInputDialog,
        QTabWidget,
        QCheckBox,
        QLineEdit,
        QComboBox,
        QTableWidget,
        QTableWidgetItem,
        QFileDialog,
        QTimeEdit,
    )
    from PySide6.QtCharts import QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis
    from PySide6.QtGui import QBrush, QColor, QPainter, QPen
    QT_AVAILABLE = True
    QT_IMPORT_ERROR = None
except Exception as e:
    QT_AVAILABLE = False
    QT_IMPORT_ERROR = e

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

# ---- ESZKÖZÖK ----
ASSETS = {
    "Bitcoin": "BTC-USD",
    "Ethereum": "ETH-USD",
    "BNB": "BNB-USD",
    "Solana": "SOL-USD",
    "XRP": "XRP-USD",
    "Cardano": "ADA-USD",
    "Dogecoin": "DOGE-USD",
    "TRON": "TRX-USD",
    "Polkadot": "DOT-USD",
    "Avalanche": "AVAX-USD",
    "Chainlink": "LINK-USD",
    "Litecoin": "LTC-USD",
    "ApeCoin (NFT)": "APE-USD",
    "Decentraland (NFT/Metaverse)": "MANA-USD",
    "The Sandbox (NFT/Metaverse)": "SAND-USD",
    "Enjin Coin (NFT)": "ENJ-USD",
    "Flow (NFT infrastruktúra)": "FLOW-USD",
    "Arany": "GC=F",
    "Kőolaj": "CL=F",
    "Földgáz": "NG=F",
    "Apple": "AAPL",
    "Microsoft": "MSFT",
    "NVIDIA": "NVDA",
    "Amazon": "AMZN",
    "Meta": "META",
    "Alphabet (Google)": "GOOGL",
    "Tesla": "TSLA",
    "AMD": "AMD",
    "Netflix": "NFLX",
    # Magyar részvények (BÉT, Yahoo: .BD)
    "OTP Bank": "OTP.BD",
    "MOL": "MOL.BD",
    "Richter Gedeon": "RICHTER.BD",
    "Magyar Telekom": "MTEL.BD",
    "4iG": "4IG.BD",
    "Opus Global": "OPUS.BD",
    "Waberer's": "WABERERS.BD",
    "Masterplast": "MASTERPLAST.BD",
    "AKKO Invest": "AKKO.BD",
    "Appeninn": "APPENINN.BD",
    # További kriptók (Yahoo *-USD)
    "Stellar": "XLM-USD",
    "Cosmos": "ATOM-USD",
    "NEAR Protocol": "NEAR-USD",
    "Uniswap": "UNI-USD",
    "Algorand": "ALGO-USD",
    "Filecoin": "FIL-USD",
    "Hedera": "HBAR-USD",
    "VeChain": "VET-USD",
    "Shiba Inu": "SHIB-USD",
    "Aptos": "APT-USD",
    "Arbitrum": "ARB-USD",
    "Optimism": "OP-USD",
    # További részvények / blue chip
    "JPMorgan Chase": "JPM",
    "Visa": "V",
    "Coca-Cola": "KO",
    "SAP": "SAP",
    "McDonald's": "MCD",
    "Walt Disney": "DIS",
    "Spotify": "SPOT",
    "Berkshire Hathaway": "BRK-B",
    "Intel": "INTC",
}

FX_URL = "https://api.exchangerate-api.com/v4/latest/USD"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL_DEFAULT = "gpt-4o-mini"
REQUEST_TIMEOUT = 15
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AssetTracker/1.0)",
}

APP_STATE_DIR = Path.home() / ".config" / "ai-cripto-tracker"
FAVORITES_PATH = APP_STATE_DIR / "favorites.json"
CUSTOM_ALERTS_PATH = APP_STATE_DIR / "custom_alerts.json"
TELEGRAM_CONFIG_PATH = APP_STATE_DIR / "telegram_config.json"


def http_get(url, timeout=REQUEST_TIMEOUT, headers=None):
    try:
        return requests.get(url, timeout=timeout, headers=headers)
    except requests.RequestException as first_error:
        # Ha env proxy akadályozza, próbáljuk direktben (trust_env=False).
        try:
            with requests.Session() as session:
                session.trust_env = False
                return session.get(url, timeout=timeout, headers=headers)
        except requests.RequestException:
            raise first_error


def http_post(url, timeout=REQUEST_TIMEOUT, **kwargs):
    try:
        return requests.post(url, timeout=timeout, **kwargs)
    except requests.RequestException as first_error:
        try:
            with requests.Session() as session:
                session.trust_env = False
                return session.post(url, timeout=timeout, **kwargs)
        except requests.RequestException:
            raise first_error


# ---- USD → HUF ----
def get_rate(timeout=REQUEST_TIMEOUT, strict=True):
    errors = []

    try:
        r = http_get(FX_URL, timeout=timeout)
        r.raise_for_status()
        return float(r.json()["rates"]["HUF"])
    except (requests.RequestException, KeyError, ValueError, TypeError) as e:
        errors.append(f"exchangerate-api: {e}")

    # Fallback: Yahoo FX árfolyam
    try:
        yahoo_fx = "https://query1.finance.yahoo.com/v8/finance/chart/USDHUF=X?range=1d&interval=5m"
        r = http_get(yahoo_fx, timeout=timeout, headers=YAHOO_HEADERS)
        r.raise_for_status()
        data = r.json()
        chart = data.get("chart") or {}
        result = (chart.get("result") or [None])[0]
        closes = (((result or {}).get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        closes = [v for v in closes if v is not None]
        if not closes:
            raise ValueError("Yahoo FX close érték hiányzik")
        return float(closes[-1])
    except (requests.RequestException, KeyError, ValueError, TypeError) as e:
        errors.append(f"yahoo-fx: {e}")

    error = RuntimeError("USD→HUF árfolyam nem elérhető | " + " | ".join(errors))
    if strict:
        raise error
    return 1.0


def get_effective_rate():
    try:
        return get_rate(strict=True), "HUF", None
    except Exception as e:
        return 1.0, "USD", str(e)


def yahoo_price_display_multiplier(symbol, rate, display_currency):
    """
    Yahoo chart: USA részvények és *-USD instrumentumok USD-ben;
    BÉT (.BD) részvények HUF-ban.
    rate: 1 USD = rate HUF (get_rate érték).
    """
    cur = (display_currency or "HUF").strip().upper()
    r = float(rate) if rate not in (None, 0) else 1.0
    if r <= 0:
        r = 1.0
    sym = str(symbol or "").strip().upper()
    is_bet = sym.endswith(".BD")
    if cur == "HUF":
        return 1.0 if is_bet else r
    if is_bet:
        return 1.0 / r
    return 1.0


def get_usdhuf_vs_ma20(timeout=REQUEST_TIMEOUT):
    """
    Napi USD/HUF: utolsó záró ár vs. 20 napos mozgóátlag (%).
    None, ha nincs elég adat vagy hiba.
    """
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/USDHUF=X"
        "?range=90d&interval=1d"
    )
    try:
        r = http_get(url, timeout=timeout, headers=YAHOO_HEADERS)
        r.raise_for_status()
        data = r.json()
        chart = data.get("chart") or {}
        result = (chart.get("result") or [None])[0]
        quotes = ((result or {}).get("indicators") or {}).get("quote") or []
        if not quotes:
            return None
        closes = quotes[0].get("close") or []
        arr = np.array([x for x in closes if x is not None], dtype=float)
        if arr.size < 21:
            return None
        current = float(arr[-1])
        ma20 = float(np.mean(arr[-20:]))
        if ma20 == 0:
            return None
        pct_vs_ma = (current / ma20 - 1.0) * 100.0
        return {"current": current, "ma20": ma20, "pct_vs_ma": pct_vs_ma}
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None


# ---- ADAT ----
def get_asset(symbol, timeout=REQUEST_TIMEOUT):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        "?range=90d&interval=1h"
    )
    r = http_get(url, timeout=timeout, headers=YAHOO_HEADERS)
    r.raise_for_status()
    data = r.json()

    chart = data.get("chart") or {}
    if chart.get("error") or not chart.get("result"):
        raise ValueError(f"Nincs árfolyam adat: {symbol}")

    result = chart["result"][0]
    quotes = (result.get("indicators") or {}).get("quote") or []
    if not quotes:
        raise ValueError(f"Üres idősor: {symbol}")

    closes = quotes[0].get("close") or []
    vols = quotes[0].get("volume") or []
    if len(vols) != len(closes):
        vols = [None] * len(closes)
    pc, pv = [], []
    for c, v in zip(closes, vols):
        if c is not None:
            pc.append(float(c))
            pv.append(float(v) if v is not None else np.nan)
    prices = np.array(pc, dtype=float)
    volumes = np.array(pv, dtype=float)
    if prices.size < 2:
        raise ValueError(f"Túl kevés érvényes ár: {symbol}")
    meta = result.get("meta") or {}
    native_open_fallback = None
    if meta.get("regularMarketOpen") is None:
        native_open_fallback = infer_session_open_native_from_chart(result)
    return prices, meta, native_open_fallback, volumes


def fetch_chart_series(symbol, range_param="1d", interval_param="5m", timeout=REQUEST_TIMEOUT):
    """
    Yahoo chart idősor (záró árak + időbélyegek) diagramhoz.
    range_param: 1d, 5d, 1mo, 3mo, 6mo, 1y
    interval_param: 1m, 2m, 5m, 15m, 1h, 1d (Yahoo által támogatott kombinációk)
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?range={range_param}&interval={interval_param}"
    )
    r = http_get(url, timeout=timeout, headers=YAHOO_HEADERS)
    r.raise_for_status()
    data = r.json()
    chart = data.get("chart") or {}
    if chart.get("error") or not chart.get("result"):
        raise ValueError(f"Nincs diagram adat: {symbol}")
    result = chart["result"][0]
    ts = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or []
    if not quotes:
        raise ValueError(f"Üres idősor: {symbol}")
    closes = quotes[0].get("close") or []
    points = []
    for t, c in zip(ts, closes):
        if c is not None and t is not None:
            points.append((int(t) * 1000, float(c)))
    if len(points) < 2:
        raise ValueError(f"Túl kevés diagram pont: {symbol}")
    meta = result.get("meta") or {}
    native_open_fb = None
    if meta.get("regularMarketOpen") is None:
        native_open_fb = infer_session_open_native_from_chart(result)
    return {
        "points": points,
        "meta": meta,
        "native_open_fallback": native_open_fb,
    }


def fetch_ohlc_series(symbol, range_param="1d", interval_param="5m", timeout=REQUEST_TIMEOUT):
    """
    Yahoo chart OHLCV idősor gyertyadiagramhoz.
    Visszaad: list of (timestamp_ms, open, high, low, close) tuples, csak érvényes gyertyák.
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?range={range_param}&interval={interval_param}"
    )
    r = http_get(url, timeout=timeout, headers=YAHOO_HEADERS)
    r.raise_for_status()
    data = r.json()
    chart = data.get("chart") or {}
    if chart.get("error") or not chart.get("result"):
        raise ValueError(f"Nincs OHLC adat: {symbol}")
    result = chart["result"][0]
    ts = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or []
    if not quotes:
        raise ValueError(f"Üres OHLC idősor: {symbol}")
    q = quotes[0]
    opens   = q.get("open")   or []
    highs   = q.get("high")   or []
    lows    = q.get("low")    or []
    closes  = q.get("close")  or []
    candles = []
    for t, o, h, l, c in zip(ts, opens, highs, lows, closes):
        if None in (t, o, h, l, c):
            continue
        candles.append((int(t) * 1000, float(o), float(h), float(l), float(c)))
    if len(candles) < 2:
        raise ValueError(f"Túl kevés érvényes gyertya: {symbol}")
    meta = result.get("meta") or {}
    native_open_fb = None
    if meta.get("regularMarketOpen") is None:
        native_open_fb = infer_session_open_native_from_chart(result)
    return {
        "candles": candles,
        "meta": meta,
        "native_open_fallback": native_open_fb,
    }


def regular_market_change_pct(meta):
    """Százalékos változás a meta mezők alapján (ha elérhető)."""
    if not meta:
        return None
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    price = meta.get("regularMarketPrice")
    try:
        if prev is None or price is None:
            return None
        p, pr = float(price), float(prev)
        if pr == 0:
            return None
        return (p / pr - 1.0) * 100.0
    except (TypeError, ValueError):
        return None


def _utc_date_from_ts(tsec):
    return datetime.fromtimestamp(int(tsec), tz=timezone.utc).date()


def infer_session_open_native_from_chart(chart_result):
    """
    Ha a meta-ban nincs regularMarketOpen: az idősor utolsó napjának első ismert open értéke (Yahoo pénznem).
    """
    ts = chart_result.get("timestamp") or []
    quotes = (chart_result.get("indicators") or {}).get("quote") or []
    if not quotes or not ts:
        return None
    opens = quotes[0].get("open") or []
    if len(opens) != len(ts):
        return None
    i = len(ts) - 1
    while i >= 0 and opens[i] is None:
        i -= 1
    if i < 0:
        return None
    last_day = _utc_date_from_ts(ts[i])
    first_i = i
    j = i - 1
    while j >= 0:
        if opens[j] is None:
            j -= 1
            continue
        if _utc_date_from_ts(ts[j]) != last_day:
            break
        first_i = j
        j -= 1
    o = opens[first_i]
    try:
        return float(o) if o is not None else None
    except (TypeError, ValueError):
        return None


def meta_session_open_previous_close(meta, multiplier, native_open_fallback=None):
    """
    Részvény / instrumentum session nyitás és előző záró (Yahoo meta), megjelenítési devizában.
    - regularMarketOpen: aktuális (mai) piaci session nyitás
    - chartPreviousClose vagy previousClose: előző záró (napi változás bázisa)
    Ha a nyitás hiányzik a meta-ból, lehet native_open_fallback (Yahoo ár, még nem szorozva mult-tal).
    """
    if not meta and native_open_fallback is None:
        return None, None
    mult = float(multiplier) if multiplier not in (None, 0) else 1.0
    raw_open = (meta or {}).get("regularMarketOpen")
    raw_prev = (meta or {}).get("chartPreviousClose") or (meta or {}).get("previousClose")
    try:
        o = float(raw_open) * mult if raw_open is not None else None
        if o is None and native_open_fallback is not None:
            o = float(native_open_fallback) * mult
        pc = float(raw_prev) * mult if raw_prev is not None else None
        return o, pc
    except (TypeError, ValueError):
        return None, None


# ---- ÁLLAPOT (kedvencek, riasztások, SQLite) ----
def ensure_app_state_dir():
    APP_STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_favorites():
    ensure_app_state_dir()
    if not FAVORITES_PATH.is_file():
        return []
    try:
        data = json.loads(FAVORITES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x) for x in data if x in ASSETS]
    except (OSError, ValueError, TypeError):
        pass
    return []


def save_favorites(names):
    ensure_app_state_dir()
    FAVORITES_PATH.write_text(json.dumps(sorted(set(names)), ensure_ascii=False, indent=2), encoding="utf-8")


def load_custom_alert_rules():
    ensure_app_state_dir()
    if not CUSTOM_ALERTS_PATH.is_file():
        return []
    try:
        data = json.loads(CUSTOM_ALERTS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return []


def save_custom_alert_rules(rules):
    ensure_app_state_dir()
    CUSTOM_ALERTS_PATH.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")


def load_telegram_config():
    ensure_app_state_dir()
    if not TELEGRAM_CONFIG_PATH.is_file():
        return {}, {}
    try:
        data = json.loads(TELEGRAM_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("token", ""), data.get("chat_id", "")
    except (OSError, ValueError, TypeError):
        pass
    return "", ""


def save_telegram_config(token, chat_id):
    ensure_app_state_dir()
    TELEGRAM_CONFIG_PATH.write_text(
        json.dumps({"token": token, "chat_id": chat_id}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def db_conn():
    ensure_app_state_dir()
    p = APP_STATE_DIR / "history.sqlite3"
    conn = sqlite3.connect(str(p))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS analysis_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, asset TEXT, currency TEXT,
        current REAL, future REAL, decision TEXT,
        rsi REAL, next_up_prob REAL, accuracy REAL,
        macd_hist REAL, vol_ann REAL, max_dd REAL
    )"""
    )
    conn.commit()
    return conn


def db_insert_rows(rows):
    if not rows:
        return
    conn = db_conn()
    try:
        conn.executemany(
            """INSERT INTO analysis_log
            (ts, asset, currency, current, future, decision, rsi, next_up_prob, accuracy, macd_hist, vol_ann, max_dd)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def db_search_history(asset_needle="", limit=500):
    conn = db_conn()
    try:
        if asset_needle.strip():
            cur = conn.execute(
                """SELECT ts, asset, currency, current, future, decision, rsi, next_up_prob, accuracy
                FROM analysis_log WHERE asset LIKE ? ORDER BY id DESC LIMIT ?""",
                (f"%{asset_needle.strip()}%", int(limit)),
            )
        else:
            cur = conn.execute(
                """SELECT ts, asset, currency, current, future, decision, rsi, next_up_prob, accuracy
                FROM analysis_log ORDER BY id DESC LIMIT ?""",
                (int(limit),),
            )
        return cur.fetchall()
    finally:
        conn.close()


# ---- TOVÁBBI INDIKÁTOROK / KOCKÁZAT ----
def ema_np(x, span):
    if x.size == 0:
        return x
    alpha = 2.0 / (span + 1)
    y = np.empty_like(x, dtype=float)
    y[0] = x[0]
    for i in range(1, x.size):
        y[i] = alpha * x[i] + (1.0 - alpha) * y[i - 1]
    return y


def macd_bundle(prices):
    if prices.size < 40:
        return None, None, None
    ema12 = ema_np(prices, 12)
    ema26 = ema_np(prices, 26)
    line = ema12 - ema26
    signal = ema_np(line, 9)
    hist = line - signal
    return float(line[-1]), float(signal[-1]), float(hist[-1])


def bollinger_last(prices, window=20, n_std=2.0):
    if prices.size < window:
        return None, None, None
    w = prices[-window:]
    mid = float(np.mean(w))
    sd = float(np.std(w))
    return mid + n_std * sd, mid - n_std * sd, mid


def max_drawdown_pct_series(prices):
    if prices.size < 2:
        return None
    peak = np.maximum.accumulate(prices)
    dd = np.where(peak > 0, (peak - prices) / peak, 0.0)
    return float(np.max(dd) * 100.0)


def realized_vol_annual_pct(prices):
    if prices.size < 16:
        return None
    lr = np.diff(np.log(prices))
    # Órás sávok: évesítés ~ sqrt(252 * 24)
    return float(np.std(lr) * np.sqrt(252.0 * 24.0) * 100.0)


def volume_stats(volumes):
    if volumes is None or volumes.size == 0:
        return None, None, None
    clean = volumes[~np.isnan(volumes)]
    if clean.size == 0:
        return None, None, None
    last_v = float(clean[-1])
    w = min(20, clean.size)
    sma_v = float(np.mean(clean[-w:]))
    ratio = (last_v / sma_v) if sma_v > 0 else None
    return last_v, sma_v, ratio


def build_extended_metrics(prices, volumes):
    m, s, h = macd_bundle(prices)
    bu, bl, bm = bollinger_last(prices)
    lv, sv, rr = volume_stats(volumes)
    return {
        "macd_line": m,
        "macd_signal": s,
        "macd_hist": h,
        "bb_upper": bu,
        "bb_lower": bl,
        "bb_mid": bm,
        "volume_last": lv,
        "volume_sma20": sv,
        "volume_vs_sma": rr,
        "max_drawdown_pct": max_drawdown_pct_series(prices),
        "realized_vol_annual_pct": realized_vol_annual_pct(prices),
    }


def correlation_matrix_log_returns(asset_items, rate, display_currency, timeout=REQUEST_TIMEOUT):
    series = []
    names = []
    min_len = None
    for name, sym in asset_items:
        try:
            p, _, _, _ = get_asset(sym, timeout=timeout)
            mult = yahoo_price_display_multiplier(sym, rate, display_currency)
            a = p * mult
            lr = np.diff(np.log(a))
            if lr.size < 5:
                continue
            series.append(lr)
            names.append(name)
            min_len = lr.size if min_len is None else min(min_len, lr.size)
        except (requests.RequestException, ValueError, KeyError):
            continue
    if len(series) < 2 or min_len is None or min_len < 5:
        return None, names
    n = len(series)
    mat = np.eye(n, dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            xi = series[i][-min_len:]
            xj = series[j][-min_len:]
            c = float(np.corrcoef(xi, xj)[0, 1])
            if np.isnan(c):
                c = 0.0
            mat[i, j] = mat[j, i] = c
    return mat, names


def fetch_yahoo_headlines(symbol, limit=8, timeout=REQUEST_TIMEOUT):
    from urllib.parse import quote

    q = quote(str(symbol), safe="")
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={q}&region=US&lang=en-US"
    try:
        r = http_get(url, timeout=timeout, headers=YAHOO_HEADERS)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out = []
        for it in root.findall(".//item"):
            if len(out) >= limit:
                break
            t = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if t:
                out.append({"title": t, "link": link})
        return out
    except (requests.RequestException, ET.ParseError, ValueError):
        return []


def format_correlation_table(mat, names):
    if mat is None or not names or mat.shape[0] != len(names):
        return "Nincs eleg adat a korrelaciohoz (legalabb 2 eszkoz, sikeres letoltes)."
    lines = ["Korrelacio (log-hozam, kozos idosor vege)", ""]
    header = " " * 14 + "".join(f"{n[:10]:>12}" for n in names)
    lines.append(header)
    for i, row_name in enumerate(names):
        row = f"{row_name[:12]:14}"
        for j in range(len(names)):
            row += f"{mat[i, j]:12.2f}"
        lines.append(row)
    return "\n".join(lines)


def build_html_report(results, currency, title="AI Eszkoz riport"):
    esc = html.escape
    parts = [
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"/>",
        f"<title>{esc(title)}</title>",
        "<style>body{font-family:system-ui;background:#111827;color:#e5e7eb;padding:24px;}",
        "h2{color:#93c5fd;} table{border-collapse:collapse;width:100%;margin:12px 0;}",
        "td,th{border:1px solid #374151;padding:8px;text-align:left;}</style></head><body>",
        f"<h1>{esc(title)}</h1>",
        f"<p>Deviza: {esc(currency)}</p>",
    ]
    for r in results:
        rec = r.get("recommendation") or {}
        parts.append(f"<h2>{esc(str(r.get('name','')))}</h2>")
        parts.append("<table>")
        for label, key in [
            ("Ar", "current"),
            ("AI celar", "future"),
            ("RSI", "rsi"),
            ("Dontes", "decision"),
        ]:
            if key in r:
                parts.append(f"<tr><th>{esc(label)}</th><td>{esc(str(r[key]))}</td></tr>")
        if rec:
            parts.append(f"<tr><th>Ajanlas</th><td>{esc(str(rec.get('action','')))}</td></tr>")
        parts.append("</table><hr/>")
    parts.append("</body></html>")
    return "".join(parts)


def custom_rule_matches(rule, result):
    target = str(rule.get("asset", "*")).strip()
    if target != "*" and target != result.get("name"):
        return False
    kind = str(rule.get("rule", "")).strip()
    try:
        val = float(rule.get("value"))
    except (TypeError, ValueError):
        return False
    cur = float(result["current"])
    rsi = float(result["rsi"])
    if kind == "price_above":
        return cur >= val
    if kind == "price_below":
        return cur <= val
    if kind == "rsi_above":
        return rsi >= val
    if kind == "rsi_below":
        return rsi <= val
    return False


def fire_custom_rules_if_needed(rules, result, cooldown_until, cooldown_sec=180):
    """cooldown_until: dict rule_key -> epoch when ok to fire again"""
    import time

    now = time.time()
    msgs = []
    for rule in rules:
        key = f"{rule.get('asset')}|{rule.get('rule')}|{rule.get('value')}"
        if not custom_rule_matches(rule, result):
            continue
        until = float(cooldown_until.get(key, 0))
        if now < until:
            continue
        cooldown_until[key] = now + cooldown_sec
        msgs.append(
            f"Szabaly [{rule.get('rule')} {rule.get('value')}] — {result.get('name')}: "
            f"RSI {result.get('rsi'):.1f}, ar {result.get('current'):.2f}"
        )
    return msgs


# ---- RSI (Wilder simítás) ----
def calculate_rsi(prices, period=14):
    if prices.size < period + 1:
        return 50.0

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ---- MOZGÓÁTLAG ----
def moving_average(prices, window=20):
    w = min(window, prices.size)
    return float(np.mean(prices[-w:]))


# ---- AI ----
def build_features_and_labels(prices):
    """
    Features on each hour:
    - short / medium returns
    - short volatility
    - moving average ratios
    - RSI normalized
    Label: next-hour direction (1=up, 0=down/flat)
    """
    if prices.size < 120:
        raise ValueError("Túl kevés adat a modellhez (min. 120 pont kell).")

    X, y = [], []
    returns = np.diff(prices) / prices[:-1]
    lookback = 30

    for i in range(lookback, prices.size - 1):
        ret_1 = returns[i - 1]
        ret_3 = (prices[i] / prices[i - 3]) - 1.0
        ret_12 = (prices[i] / prices[i - 12]) - 1.0
        vol_12 = float(np.std(returns[i - 12:i]))
        ma_10 = float(np.mean(prices[i - 10:i]))
        ma_30 = float(np.mean(prices[i - 30:i]))
        ma_ratio_10 = (prices[i] / ma_10) - 1.0
        ma_ratio_30 = (prices[i] / ma_30) - 1.0
        rsi = calculate_rsi(prices[: i + 1]) / 100.0

        X.append(
            [
                ret_1,
                ret_3,
                ret_12,
                vol_12,
                ma_ratio_10,
                ma_ratio_30,
                rsi,
            ]
        )
        y.append(1 if prices[i + 1] > prices[i] else 0)

    return np.array(X, dtype=float), np.array(y, dtype=int)


def random_forest_up_probability(model, feature_row):
    """
    P(következő óra fel) = osztály 1 valószínűsége.
    Ha a tanítóhalmaz egy osztályú volt, a predict_proba csak 1 oszlop — a [0][1] index hibát dobna.
    """
    row = np.asarray(feature_row, dtype=float).reshape(1, -1)
    proba = model.predict_proba(row)[0]
    classes = np.asarray(getattr(model, "classes_", np.arange(len(proba))))
    if classes.size <= 1:
        if classes.size == 0:
            return 0.5
        return 1.0 if int(classes[0]) == 1 else 0.0
    idx = np.flatnonzero(classes == 1)
    if idx.size > 0:
        return float(proba[int(idx[0])])
    return float(1.0 - proba[0])


def predict(prices):
    X, y = build_features_and_labels(prices)
    if X.shape[0] < 80:
        raise ValueError("Túl kevés minta a tanításhoz.")

    X_train = X_test = y_train = y_test = None
    uniq, counts = np.unique(y, return_counts=True)
    can_stratify = uniq.size >= 2 and int(counts.min()) >= 2
    if can_stratify:
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
        except ValueError:
            X_train = None
    if X_train is None:
        split = int(X.shape[0] * 0.8)
        split = max(1, min(split, X.shape[0] - 1))
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

    model = RandomForestClassifier(
        n_estimators=300,
        min_samples_leaf=3,
        random_state=42,
    )
    model.fit(X_train, y_train)

    accuracy = float((model.predict(X_test) == y_test).mean()) if y_test.size else 0.0
    next_up_prob = random_forest_up_probability(model, X[-1])

    current = float(prices[-1])
    tail = prices[-49:]
    recent_returns = np.diff(tail) / tail[:-1]
    recent_abs_move = float(np.mean(np.abs(recent_returns)))
    drift = (2.0 * next_up_prob - 1.0) * recent_abs_move
    future = current * (1.0 + drift)

    return current, future, next_up_prob, accuracy


# ---- KOMBINÁLT DÖNTÉS ----
def smart_decision(prices):
    current, future, next_up_prob, accuracy = predict(prices)

    rsi = calculate_rsi(prices)
    ma = moving_average(prices)

    signals = []

    if next_up_prob < 0.45:
        signals.append("SELL")
    elif next_up_prob > 0.55:
        signals.append("BUY")

    if rsi > 70:
        signals.append("SELL")
    elif rsi < 30:
        signals.append("BUY")

    if current > ma:
        signals.append("BUY")
    else:
        signals.append("SELL")

    sell_count = signals.count("SELL")
    buy_count = signals.count("BUY")

    if sell_count >= 2:
        decision = "ELADÁS ⚠️"
    elif buy_count >= 2:
        decision = "VÉTEL 📈"
    else:
        decision = "VÁRJ ⏳"

    return decision, current, future, rsi, ma, next_up_prob, accuracy


def build_recommendation(current, future, next_up_prob, accuracy, rsi, ma):
    edge = next_up_prob - 0.5
    confidence = max(0.0, min(1.0, (abs(edge) * 2.0) * (0.6 + 0.4 * accuracy)))

    # Volatilitás alapú kockázati távolság (minimum 1.5%)
    base_risk = max(0.015, abs((future / current) - 1.0))
    stop_distance = base_risk * 0.8
    tp_distance = base_risk * 1.6

    if next_up_prob >= 0.58:
        side = "LONG"
        action = "VÉTEL"
        entry = current
        stop = entry * (1.0 - stop_distance)
        take_profit = entry * (1.0 + tp_distance)
    elif next_up_prob <= 0.42:
        side = "SHORT"
        action = "ELADÁS"
        entry = current
        stop = entry * (1.0 + stop_distance)
        take_profit = entry * (1.0 - tp_distance)
    else:
        side = "NEUTRAL"
        action = "KIVÁRÁS"
        entry = current
        stop = current
        take_profit = current

    reasons = []
    reasons.append(f"AI valószínűség: {next_up_prob * 100:.1f}%")
    reasons.append(f"Modell validáció: {accuracy * 100:.1f}%")
    reasons.append("RSI túlvett" if rsi > 70 else "RSI túladott" if rsi < 30 else "RSI semleges")
    reasons.append("Ár MA felett" if current > ma else "Ár MA alatt")

    return {
        "action": action,
        "side": side,
        "confidence": confidence,
        "entry": entry,
        "stop": stop,
        "take_profit": take_profit,
        "reasons": reasons,
    }


def evaluate_today_investment(amount, currency, has_real_huf_rate, fx_ctx, result):
    """
    Összeg + árfolyam-kontextus + AI/jel: napi „érdemes-e” és javasolt tét (%).
    Nem pénzügyi tanács — csak modell-alapú összefoglaló.
    """
    rec = result["recommendation"]
    decision = result["decision"]
    conf = float(rec["confidence"])
    side = rec["side"]

    deploy_frac = 0.0
    if side == "LONG" or "VÉTEL" in decision:
        deploy_frac = min(0.85, 0.18 + 0.62 * conf)
        verdict = (
            "A mai jelzések alapján érdemes lehet korlátozott összeggel részt venni "
            "(lásd javasolt tét)."
            if conf >= 0.48
            else "Mérsékelt a jel; csak kisebb részt tarts ma kockázaton."
        )
    elif side == "SHORT" or "ELADÁS" in decision:
        deploy_frac = 0.0
        verdict = (
            "Ma nem javasolt új vételi pozíciót nyitni; inkább kivárás vagy "
            "meglévő pozíció felülvizsgálata."
        )
    else:
        deploy_frac = min(0.30, 0.08 + 0.22 * conf)
        verdict = (
            "Ma nincs egyértelmű vételi jel; érdemes várni, vagy csak nagyon kis tétet fontolgatni."
        )

    fx_note = ""
    if fx_ctx is not None:
        p = float(fx_ctx["pct_vs_ma"])
        if currency == "HUF" and has_real_huf_rate:
            if p > 1.2:
                deploy_frac *= 0.82
                fx_note = (
                    f"USD/HUF kb {p:+.1f}% a 20 napos átlag felett — a forintban vásárlás "
                    "ma általában drágább; a javasolt tétet enyhén csökkentettem."
                )
            elif p < -1.2:
                deploy_frac = min(0.88, deploy_frac * 1.06)
                fx_note = (
                    f"USD/HUF kb {p:+.1f}% a 20 napos átlag alatt — relatíve kedvezőbb "
                    "árfolyam-környezet a dollárban árazott eszközökhöz."
                )
            else:
                fx_note = (
                    f"USD/HUF kb {p:+.1f}% a 20 napos átlaghoz képest — közel „normál” "
                    "árfolyam-sáv."
                )
        else:
            fx_note = (
                f"(Tájékoztató) USD/HUF kb {p:+.1f}% a 20 napos átlaghoz képest — "
                "ha forintból váltanál, ez a környezet számít."
            )

    deploy_frac = max(0.0, min(deploy_frac, 0.88))
    deploy_amount = float(amount) * deploy_frac

    if deploy_frac < 0.08 and side != "SHORT" and "ELADÁS" not in decision:
        verdict = (
            "Ma gyenge a jel egy nagyobb befektetéshez; inkább minimális összeg, "
            "vagy kihagyás."
        )

    return {
        "amount": float(amount),
        "deploy_frac": deploy_frac,
        "deploy_amount": deploy_amount,
        "verdict": verdict,
        "fx_note": fx_note,
    }


def analyze_asset(name, symbol, rate, display_currency="HUF"):
    mult = yahoo_price_display_multiplier(symbol, rate, display_currency)
    prices_raw, meta, open_fallback_native, volumes_raw = get_asset(symbol)
    prices = prices_raw * mult
    decision, current, future, rsi, ma, next_up_prob, accuracy = smart_decision(prices)
    recommendation = build_recommendation(
        current=current,
        future=future,
        next_up_prob=next_up_prob,
        accuracy=accuracy,
        rsi=rsi,
        ma=ma,
    )
    session_open, previous_close = meta_session_open_previous_close(
        meta, mult, native_open_fallback=open_fallback_native
    )
    metrics = build_extended_metrics(prices, volumes_raw)
    return {
        "name": name,
        "symbol": symbol,
        "current": current,
        "future": future,
        "rsi": rsi,
        "ma": ma,
        "decision": decision,
        "next_up_prob": next_up_prob,
        "accuracy": accuracy,
        "recommendation": recommendation,
        "day_change_pct": regular_market_change_pct(meta),
        "session_open": session_open,
        "previous_close": previous_close,
        "metrics": metrics,
    }


def get_current_price(symbol, rate, display_currency="HUF"):
    prices, _, _, _ = get_asset(symbol)
    mult = yahoo_price_display_multiplier(symbol, rate, display_currency)
    return float(prices[-1] * mult)


def notify_price_change(title, message):
    # Linux desktop notification via notify-send (if available)
    if sys.platform.startswith("linux") and shutil.which("notify-send"):
        try:
            subprocess.run(
                ["notify-send", title, message],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
    print(f"[ÉRTESÍTÉS] {title} - {message}")


def send_telegram_message(bot_token, chat_id, message, timeout=REQUEST_TIMEOUT, parse_mode="HTML"):
    if not bot_token or not chat_id:
        return False, "Hiányzó Telegram token/chat_id"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": parse_mode}
    try:
        r = requests.post(url, data=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            return False, str(data)
        return True, None
    except (requests.RequestException, ValueError, TypeError) as e:
        return False, str(e)


def format_telegram_result(result, currency="HUF"):
    """Format a single asset result as a rich Telegram HTML message."""
    decision = str(result.get("decision", ""))
    if "VÉTEL" in decision or "VETEL" in decision:
        signal_emoji = "📈"
        signal_color = "✅"
    elif "ELADÁS" in decision or "ELADAS" in decision:
        signal_emoji = "📉"
        signal_color = "🔴"
    else:
        signal_emoji = "⏳"
        signal_color = "🟡"

    rec = result.get("recommendation", {})
    name = html.escape(str(result.get("name", "")))
    symbol = html.escape(str(result.get("symbol", "")))

    lines = [
        f"{signal_emoji} <b>{name}</b> ({symbol})",
        f"━━━━━━━━━━━━━━━━━",
    ]
    dcp = result.get("day_change_pct")
    if dcp is not None:
        arrow = "▲" if dcp >= 0 else "▼"
        lines.append(f"📊 Napi változás: <b>{arrow} {dcp:+.2f}%</b>")
    lines.append(f"💰 Ár: <b>{int(result['current']):,} {currency}</b>")
    lines.append(f"🎯 AI célár (1h): <b>{int(result['future']):,} {currency}</b>")
    lines.append(f"🤖 AI valószínűség fel: <b>{result['next_up_prob'] * 100:.1f}%</b>")
    lines.append(f"📐 RSI: <b>{result['rsi']:.1f}</b>")
    lines.append(f"{signal_color} Döntés: <b>{html.escape(decision)}</b>")
    lines.append(f"💼 Ajánlás: <b>{html.escape(str(rec.get('action', '-')))}</b> ({html.escape(str(rec.get('side', '-')))})")
    lines.append(f"🎲 Bizalom: <b>{rec.get('confidence', 0) * 100:.1f}%</b>")
    if rec.get("side") != "NEUTRAL":
        lines.append(f"🚫 Stop-loss: {int(rec.get('stop', 0)):,} {currency}")
        lines.append(f"✨ Take-profit: {int(rec.get('take_profit', 0)):,} {currency}")
    inv = result.get("investment")
    if inv:
        lines.append(
            f"💵 Javasolt tét: <b>{int(inv['deploy_amount']):,} {currency}</b> "
            f"({inv['deploy_frac'] * 100:.0f}%)"
        )
    return "\n".join(lines)


def format_telegram_alert(message, asset_name=""):
    """Format a price alert as Telegram HTML."""
    if asset_name:
        header = f"⚠️ <b>Riasztás – {html.escape(asset_name)}</b>\n"
    else:
        header = "⚠️ <b>Árfolyam riasztás</b>\n"
    return header + html.escape(message)


def append_live_csv(csv_path, rows):
    if not rows:
        return
    path = Path(csv_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "asset",
                "currency",
                "current",
                "future",
                "decision",
                "next_up_prob",
                "model_accuracy",
                "confidence",
                "invest_amount",
                "deploy_amount",
                "deploy_frac",
            ],
        )
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def get_ai_commentary(result, currency, api_key, model=OPENAI_MODEL_DEFAULT, timeout=20):
    if not api_key:
        return None, "Nincs AI API kulcs."
    rec = result.get("recommendation", {})
    prompt = (
        "Adj rovid, 3-5 pontos magyar piaci osszefoglalot ezek alapjan. "
        "Ne adj befektetesi garanciat, legyen ovatos hangnem.\n\n"
        f"Eszkoz: {result.get('name')}\n"
    )
    if result.get("session_open") is not None:
        prompt += f"Mai nyitas: {float(result['session_open']):.2f} {currency}\n"
    if result.get("previous_close") is not None:
        prompt += f"Elozo zaro: {float(result['previous_close']):.2f} {currency}\n"
    prompt += (
        f"Most: {result.get('current'):.2f} {currency}\n"
        f"AI celar (1 ora): {result.get('future'):.2f} {currency}\n"
        f"AI fel esely: {result.get('next_up_prob', 0.0) * 100:.1f}%\n"
        f"Modell pontossag: {result.get('accuracy', 0.0) * 100:.1f}%\n"
        f"RSI: {result.get('rsi', 0.0):.2f}\n"
        f"Mozgoatlag: {result.get('ma', 0.0):.2f}\n"
        f"Dontes: {result.get('decision')}\n"
        f"Javasolt irany: {rec.get('action', 'ismeretlen')}\n"
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Te egy konzervativ penzugyi elemzo asszisztens vagy."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    try:
        r = http_post(OPENAI_API_URL, headers=headers, json=payload, timeout=timeout)
        data = r.json()
        if r.status_code >= 400:
            err = data.get("error") if isinstance(data, dict) else None
            if isinstance(err, dict):
                msg = err.get("message") or err.get("code") or str(err)
            else:
                msg = str(err) if err else r.text or r.reason
            return None, f"OpenAI API ({r.status_code}): {msg}"
        content = (((data.get("choices") or [None])[0] or {}).get("message") or {}).get("content")
        if not content:
            return None, "Ures AI valasz."
        return str(content).strip(), None
    except (requests.RequestException, ValueError, TypeError) as e:
        return None, str(e)


def monitor_price_changes(selected_assets, interval_sec=60, threshold_pct=1.0):
    print(
        f"Árfigyelés indul | időköz: {interval_sec}s | értesítési küszöb: {threshold_pct:.2f}%"
    )
    print("Kilépés: Ctrl+C")

    rate, currency, rate_warning = get_effective_rate()
    if rate_warning:
        print(f"Figyelem: árfolyam hiba, USD módra váltva. ({rate_warning})")

    last_prices = {}
    had_error = False
    for name, symbol in selected_assets:
        try:
            current = get_current_price(symbol, rate, currency)
            last_prices[name] = current
            print(f"Kezdő ár — {name}: {current:,.2f} {currency}")
        except (requests.RequestException, ValueError, KeyError) as e:
            had_error = True
            print(f"{name}: induló ár lekérés hiba — {e}")

    if not last_prices:
        return 1

    while True:
        try:
            time.sleep(max(1, int(interval_sec)))
            rate, currency, rate_warning = get_effective_rate()
            if rate_warning:
                print(f"Figyelem: árfolyam hiba, USD módra váltva. ({rate_warning})")

            for name, symbol in selected_assets:
                if name not in last_prices:
                    continue
                try:
                    current = get_current_price(symbol, rate, currency)
                    previous = last_prices[name]
                    if previous == 0:
                        last_prices[name] = current
                        continue

                    change_pct = ((current / previous) - 1.0) * 100.0
                    if abs(change_pct) >= threshold_pct:
                        direction = "nőtt" if change_pct > 0 else "csökkent"
                        msg = (
                            f"{name}: {direction} {change_pct:+.2f}% | "
                            f"{previous:,.2f} → {current:,.2f} {currency}"
                        )
                        print(msg)
                        notify_price_change("Árfolyam riasztás", msg)
                        last_prices[name] = current
                except (requests.RequestException, ValueError, KeyError) as e:
                    had_error = True
                    print(f"{name}: figyelési hiba — {e}")
        except KeyboardInterrupt:
            print("\nÁrfigyelés leállítva.")
            return 1 if had_error else 0


# ---- ALAKZATFELISMERÉS ----
def find_local_extrema(closes, order=5):
    """
    Lokális maximumok és minimumok keresése a záróárak listájában.
    order: hány szomszéd mindkét oldalon kell a csúcs/völgy feltételéhez.
    Visszaad: (maxima_idx, minima_idx) — indexek listái.
    """
    arr = np.array(closes, dtype=float)
    n = len(arr)
    maxima, minima = [], []
    for i in range(order, n - order):
        window = arr[i - order: i + order + 1]
        if arr[i] == window.max() and arr[i] > window.mean():
            maxima.append(i)
        if arr[i] == window.min() and arr[i] < window.mean():
            minima.append(i)
    # Deduplikáció: egymáshoz túl közel eső pontok közül csak az erősebb marad
    def dedup(idxs, arr, is_max, min_gap):
        result = []
        for idx in idxs:
            if not result or idx - result[-1] >= min_gap:
                result.append(idx)
            else:
                if is_max:
                    result[-1] = idx if arr[idx] > arr[result[-1]] else result[-1]
                else:
                    result[-1] = idx if arr[idx] < arr[result[-1]] else result[-1]
        return result

    min_gap = max(3, order)
    maxima = dedup(maxima, arr, True, min_gap)
    minima = dedup(minima, arr, False, min_gap)
    return maxima, minima


def detect_patterns(candles, mult=1.0):
    """
    Alakzatfelismerés az utolsó N gyertyán.
    Visszaad: list of dict { 'type', 'label', 'emoji', 'desc',
                              'start_idx', 'end_idx', 'direction', 'color' }
    Típusok: 'M' (double top / bearish), 'W' (double bottom / bullish),
             'V' (sharp reversal up), 'inverse_V' (sharp reversal down)
    """
    if not candles or len(candles) < 10:
        return []

    closes = [c[4] * mult for c in candles]
    n = len(closes)
    arr = np.array(closes, dtype=float)

    # Adaptív order: hosszabb idősoron nagyobb ablak
    order = max(3, min(8, n // 20))
    maxima, minima = find_local_extrema(closes, order=order)

    patterns = []

    # --- M alakzat (Double Top) ---
    # Két közel azonos magasságú maximum, köztük völgy
    if len(maxima) >= 2:
        for i in range(len(maxima) - 1):
            m1, m2 = maxima[i], maxima[i + 1]
            if m2 - m1 < order * 2:
                continue
            h1, h2 = arr[m1], arr[m2]
            # A két csúcs legyen közel azonos (max 3% különbség)
            if abs(h1 - h2) / max(h1, h2) > 0.03:
                continue
            # Köztük legyen egy völgy legalább 1.5%-kal lejjebb
            valley = arr[m1:m2 + 1].min()
            avg_top = (h1 + h2) / 2
            if (avg_top - valley) / avg_top < 0.015:
                continue
            patterns.append({
                "type": "M",
                "label": "M (Double Top)",
                "emoji": "🔴",
                "desc": (
                    f"M alakzat (Double Top): két közel azonos csúcs "
                    f"({h1 * mult:.2f} / {h2 * mult:.2f}). "
                    "Medvés jel — esés várható."
                ),
                "start_idx": m1,
                "end_idx": m2,
                "direction": "bearish",
                "color": "#ef4444",
            })

    # --- W alakzat (Double Bottom) ---
    # Két közel azonos mélységű minimum, köztük csúcs
    if len(minima) >= 2:
        for i in range(len(minima) - 1):
            b1, b2 = minima[i], minima[i + 1]
            if b2 - b1 < order * 2:
                continue
            l1, l2 = arr[b1], arr[b2]
            if abs(l1 - l2) / max(l1, l2) > 0.03:
                continue
            peak = arr[b1:b2 + 1].max()
            avg_bot = (l1 + l2) / 2
            if (peak - avg_bot) / avg_bot < 0.015:
                continue
            patterns.append({
                "type": "W",
                "label": "W (Double Bottom)",
                "emoji": "🟢",
                "desc": (
                    f"W alakzat (Double Bottom): két közel azonos mélypont "
                    f"({l1 * mult:.2f} / {l2 * mult:.2f}). "
                    "Bullish jel — emelkedés várható."
                ),
                "start_idx": b1,
                "end_idx": b2,
                "direction": "bullish",
                "color": "#22c55e",
            })

    # --- V alakzat (Sharp Reversal Up) ---
    # Gyors esés, majd gyors visszapattanás az utolsó 20 gyertyán
    window = min(20, n)
    seg = arr[-window:]
    bot_i = int(np.argmin(seg))
    if 2 <= bot_i <= window - 3:
        left_drop  = (seg[0] - seg[bot_i]) / seg[0] if seg[0] > 0 else 0
        right_rise = (seg[-1] - seg[bot_i]) / seg[bot_i] if seg[bot_i] > 0 else 0
        if left_drop > 0.02 and right_rise > 0.02:
            abs_bot = n - window + bot_i
            patterns.append({
                "type": "V",
                "label": "V (Éles megfordulás fel)",
                "emoji": "⬆️",
                "desc": (
                    f"V alakzat: gyors esés ({left_drop * 100:.1f}%) majd visszapattanás "
                    f"({right_rise * 100:.1f}%). Bullish megfordulás jel."
                ),
                "start_idx": max(0, abs_bot - bot_i),
                "end_idx": n - 1,
                "direction": "bullish",
                "color": "#22c55e",
            })

    # --- Fordított V (Sharp Reversal Down) ---
    top_i = int(np.argmax(seg))
    if 2 <= top_i <= window - 3:
        left_rise = (seg[top_i] - seg[0]) / seg[0] if seg[0] > 0 else 0
        right_drop = (seg[top_i] - seg[-1]) / seg[top_i] if seg[top_i] > 0 else 0
        if left_rise > 0.02 and right_drop > 0.02:
            abs_top = n - window + top_i
            patterns.append({
                "type": "inv_V",
                "label": "∧ (Éles megfordulás le)",
                "emoji": "⬇️",
                "desc": (
                    f"Fordított V alakzat: gyors emelkedés ({left_rise * 100:.1f}%) majd esés "
                    f"({right_drop * 100:.1f}%). Bearish megfordulás jel."
                ),
                "start_idx": max(0, abs_top - top_i),
                "end_idx": n - 1,
                "direction": "bearish",
                "color": "#ef4444",
            })

    # Deduplikáció: ha ugyanolyan típusú alakzat van, csak az utolsót tartjuk
    seen = {}
    for p in reversed(patterns):
        if p["type"] not in seen:
            seen[p["type"]] = p
    return list(reversed(list(seen.values())))


def format_result(result, currency="HUF"):
    rec = result["recommendation"]
    text = f"{result['name']}\n"
    dcp = result.get("day_change_pct")
    if dcp is not None:
        text += f"Napi / regular piaci valtozas: {dcp:+.2f}%\n"
    so = result.get("session_open")
    pzc = result.get("previous_close")
    if so is not None:
        text += f"Mai / aktuális session nyitás: {int(so):,} {currency}\n"
    if pzc is not None:
        text += f"Előző záró: {int(pzc):,} {currency}\n"
    text += f"Most: {int(result['current']):,} {currency}\n"
    text += f"AI célár (1 óra): {int(result['future']):,} {currency}\n"
    text += f"AI esély fel: {result['next_up_prob'] * 100:.1f}%\n"
    text += f"AI validáció pontosság: {result['accuracy'] * 100:.1f}%\n"
    text += f"RSI: {result['rsi']:.2f}\n"
    text += f"MA: {int(result['ma']):,}\n"
    m = result.get("metrics") or {}
    if m:
        text += "Indikatorok / kockazat (90 napos oras sav):\n"
        if m.get("macd_hist") is not None:
            text += (
                f"- MACD: vonal {m['macd_line']:.4f}, jel {m['macd_signal']:.4f}, "
                f"histogram {m['macd_hist']:.4f}\n"
            )
        if m.get("bb_mid") is not None:
            text += (
                f"- Bollinger (20, 2σ): fel {m['bb_upper']:.2f}, kozep {m['bb_mid']:.2f}, "
                f"al {m['bb_lower']:.2f}\n"
            )
        vl, vr = m.get("volume_last"), m.get("volume_vs_sma")
        if vl is not None and vl > 0 and vr is not None:
            text += f"- Forgalom: utolso {vl:,.0f}, arany 20-as atlaghoz: {vr:.2f}x\n"
        elif vl is not None and vl > 0:
            text += f"- Forgalom (utolso sav): {vl:,.0f}\n"
        if m.get("realized_vol_annual_pct") is not None:
            text += f"- Realizalt volatilitas (evesitett, kb): {m['realized_vol_annual_pct']:.1f}%\n"
        if m.get("max_drawdown_pct") is not None:
            text += f"- Max. visszaeses (idosoron): {m['max_drawdown_pct']:.2f}%\n"
    text += f"Döntés: {result['decision']}\n"
    text += "Ajánlás:\n"
    text += f"- Irány: {rec['action']} ({rec['side']})\n"
    text += f"- Bizalom: {rec['confidence'] * 100:.1f}%\n"
    if rec["side"] != "NEUTRAL":
        text += f"- Belépő: {int(rec['entry']):,} {currency}\n"
        text += f"- Stop-loss: {int(rec['stop']):,} {currency}\n"
        text += f"- Take-profit: {int(rec['take_profit']):,} {currency}\n"
    text += f"- Indok: {', '.join(rec['reasons'])}\n"
    if result.get("investment"):
        inv = result["investment"]
        text += "\nBefektetés (megadott összeg):\n"
        text += f"- Tőke: {int(inv['amount']):,} {currency}\n"
        text += f"- Ma érdemes-e nagyobb tét: {inv['verdict']}\n"
        if inv.get("fx_note"):
            text += f"- Árfolyam (USD/HUF): {inv['fx_note']}\n"
        text += (
            f"- Javasolt tét ma: ~{int(inv['deploy_amount']):,} {currency} "
            f"({inv['deploy_frac'] * 100:.0f}% a megadott összegből)\n"
        )
    return text


if QT_AVAILABLE:
    from PySide6.QtWidgets import QSizePolicy

    class CandlestickWidget(QWidget):
        """
        Egyedi QPainter-alapú gyertyadiagram alakzatfelismeréssel.
        Gyertyák: zöld = emelkedő (close >= open), piros = eső (close < open).
        Alakzatok: kiemelő overlay + szöveges panel alul.
        """
        MARGIN_L = 72
        MARGIN_R = 20
        MARGIN_T = 36
        MARGIN_B = 28
        PATTERN_PANEL_H = 64

        def __init__(self, parent=None):
            super().__init__(parent)
            self._candles = []       # list of (ts_ms, open, high, low, close)
            self._patterns = []      # list of pattern dicts
            self._title = ""
            self._currency = "HUF"
            self._x_labels = []      # list of (candle_idx, label_str)
            self.setMinimumHeight(360)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.setStyleSheet("background: #0d1117;")

        def set_data(self, candles, patterns, title="", currency="HUF", x_labels=None):
            self._candles  = candles
            self._patterns = patterns
            self._title    = title
            self._currency = currency
            self._x_labels = x_labels or []
            self.update()

        # ---------- Paint ----------
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw(painter)
            painter.end()

        def _draw(self, painter):
            w = self.width()
            h = self.height()

            # ---- background ----
            painter.fillRect(0, 0, w, h, QColor("#0d1117"))

            candles = self._candles
            if not candles:
                painter.setPen(QPen(QColor("#8b949e")))
                painter.drawText(
                    self.rect(), Qt.AlignmentFlag.AlignCenter,
                    "Nincs gyertya adat — válassz eszközt"
                )
                return

            n = len(candles)
            ml = self.MARGIN_L
            mr = self.MARGIN_R
            mt = self.MARGIN_T
            panel_h = self.PATTERN_PANEL_H if self._patterns else 0
            mb = self.MARGIN_B + panel_h
            plot_w = w - ml - mr
            plot_h = h - mt - mb

            if plot_w < 10 or plot_h < 10:
                return

            # ---- price range ----
            highs  = [c[2] for c in candles]
            lows   = [c[3] for c in candles]
            y_max  = max(highs)
            y_min  = min(lows)
            y_span = y_max - y_min or max(abs(y_max) * 0.01, 1e-8)
            pad    = y_span * 0.06
            y_max += pad
            y_min -= pad
            y_span = y_max - y_min

            def to_y(price):
                return mt + plot_h * (1.0 - (price - y_min) / y_span)

            def to_x(idx):
                return ml + (idx + 0.5) * plot_w / n

            candle_w = max(1.0, plot_w / n * 0.7)
            half_w   = candle_w / 2.0

            # ---- grid lines ----
            grid_pen = QPen(QColor("#21262d"))
            grid_pen.setWidthF(0.8)
            painter.setPen(grid_pen)
            n_grid = 6
            for i in range(n_grid + 1):
                price = y_min + y_span * i / n_grid
                yy = to_y(price)
                painter.drawLine(int(ml), int(yy), int(w - mr), int(yy))
                # price label
                painter.setPen(QPen(QColor("#484f58")))
                if self._currency and max(abs(y_max), abs(y_min)) >= 500:
                    lbl = f"{price:,.0f}"
                elif max(abs(y_max), abs(y_min)) >= 1.0:
                    lbl = f"{price:.2f}"
                else:
                    lbl = f"{price:.5f}"
                painter.drawText(
                    2, int(yy) - 8, ml - 4, 18,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    lbl,
                )
                painter.setPen(grid_pen)

            # ---- pattern overlays (shaded region + top border) ----
            for pat in self._patterns:
                si = pat["start_idx"]
                ei = pat["end_idx"]
                if si < 0 or ei >= n or si > ei:
                    continue
                x1 = to_x(si) - half_w
                x2 = to_x(ei) + half_w
                col = QColor(pat["color"])
                shade = QColor(col)
                shade.setAlphaF(0.08)
                painter.fillRect(
                    int(x1), int(mt), int(x2 - x1), int(plot_h), shade
                )
                border_pen = QPen(col)
                border_pen.setWidthF(1.5)
                border_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(border_pen)
                painter.drawLine(int(x1), int(mt), int(x1), int(mt + plot_h))
                painter.drawLine(int(x2), int(mt), int(x2), int(mt + plot_h))
                # label at top
                painter.setPen(QPen(col))
                painter.setFont(self.font())
                painter.drawText(
                    int(x1) + 3, int(mt) + 2, int(x2 - x1) - 6, 20,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                    f"{pat['emoji']} {pat['label']}",
                )

            # ---- candles ----
            col_bull = QColor("#22c55e")
            col_bear = QColor("#ef4444")
            col_doji = QColor("#8b949e")

            for i, (ts, op, hi, lo, cl) in enumerate(candles):
                x = to_x(i)
                y_open  = to_y(op)
                y_close = to_y(cl)
                y_high  = to_y(hi)
                y_low   = to_y(lo)

                if cl > op:
                    color = col_bull
                elif cl < op:
                    color = col_bear
                else:
                    color = col_doji

                # wick
                wick_pen = QPen(color)
                wick_pen.setWidthF(1.0)
                painter.setPen(wick_pen)
                painter.drawLine(int(x), int(y_high), int(x), int(y_low))

                # body
                body_top    = min(y_open, y_close)
                body_bottom = max(y_open, y_close)
                body_h      = max(1.0, body_bottom - body_top)
                if cl >= op:
                    painter.fillRect(
                        int(x - half_w), int(body_top),
                        int(candle_w), int(body_h), color
                    )
                else:
                    painter.fillRect(
                        int(x - half_w), int(body_top),
                        int(candle_w), int(body_h), color
                    )
                    # hollow border for dark candles (optional style)
                    border = QPen(color)
                    border.setWidthF(0.6)
                    painter.setPen(border)
                    painter.drawRect(
                        int(x - half_w), int(body_top),
                        int(candle_w), int(body_h)
                    )

            # ---- x-axis labels ----
            painter.setPen(QPen(QColor("#484f58")))
            for idx, lbl in self._x_labels:
                if 0 <= idx < n:
                    xx = int(to_x(idx))
                    painter.drawText(
                        xx - 32, h - mb + 4, 64, 20,
                        Qt.AlignmentFlag.AlignCenter,
                        lbl,
                    )

            # ---- title ----
            title_pen = QPen(QColor("#c9d1d9"))
            painter.setPen(title_pen)
            from PySide6.QtGui import QFont
            f = QFont()
            f.setBold(True)
            f.setPointSize(10)
            painter.setFont(f)
            painter.drawText(
                ml, 4, plot_w, mt - 4,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._title,
            )

            # ---- pattern panel ----
            if self._patterns:
                panel_y = h - panel_h
                painter.fillRect(0, panel_y, w, panel_h, QColor("#0d1117"))
                sep_pen = QPen(QColor("#30363d"))
                sep_pen.setWidthF(1.0)
                painter.setPen(sep_pen)
                painter.drawLine(0, panel_y, w, panel_y)

                f2 = QFont()
                f2.setPointSize(9)
                painter.setFont(f2)
                x_cur = ml
                for pat in self._patterns:
                    col = QColor(pat["color"])
                    painter.setPen(QPen(col))
                    text = f"{pat['emoji']}  {pat['label']}: {pat['desc']}"
                    painter.drawText(
                        x_cur, panel_y + 8, w - x_cur - mr, panel_h - 12,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                        | Qt.TextFlag.TextWordWrap,
                        text,
                    )
                    # Only one pattern description fits; stack them vertically
                    x_cur = ml  # reset; we'll break lines below
                    break  # draw first pattern; rest shown stacked

                # Stack remaining patterns below
                if len(self._patterns) > 1:
                    y_txt = panel_y + 8
                    line_h = 18
                    for pat in self._patterns:
                        col = QColor(pat["color"])
                        painter.setPen(QPen(col))
                        painter.drawText(
                            ml, y_txt, w - ml - mr, line_h,
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                            f"{pat['emoji']}  {pat['label']}: {pat['desc']}",
                        )
                        y_txt += line_h
                        if y_txt + line_h > h:
                            break


if QT_AVAILABLE:
    # ---- GUI ----
    class App(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("AI Eszkozelemzo Pro")
            self.setGeometry(100, 100, 1280, 780)
            self.apply_styles()
            self.invest_amount = None
            self.live_interval_sec = 30
            self.alert_threshold_pct = 0.8
            self.auto_clear_analysis = True
            self.sound_alerts_enabled = True
            self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
            # Load persisted config if env vars not set
            if not self.telegram_bot_token or not self.telegram_chat_id:
                saved_token, saved_chat = load_telegram_config()
                if not self.telegram_bot_token and saved_token:
                    self.telegram_bot_token = saved_token
                if not self.telegram_chat_id and saved_chat:
                    self.telegram_chat_id = saved_chat
            self.telegram_enabled = bool(self.telegram_bot_token and self.telegram_chat_id)
            self.ai_commentary_enabled = False
            self.ai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
            self.ai_model = OPENAI_MODEL_DEFAULT
            self.csv_autosave_enabled = True
            self.csv_path = str(Path.cwd() / "live_history.csv")
            self.last_prices_live = {}
            self.live_timer = QTimer(self)
            self.live_timer.timeout.connect(self.run_live_tick)
            self.favorite_names = set(load_favorites())
            self.custom_rules = load_custom_alert_rules()
            self._rule_cooldown = {}
            self._last_results = []
            self._last_scheduled_run_date = None

            layout = QHBoxLayout()
            layout.setContentsMargins(14, 14, 14, 14)
            layout.setSpacing(12)

            left_col = QVBoxLayout()
            self.asset_search = QLineEdit()
            self.asset_search.setPlaceholderText("Keresés eszköz névre…")
            self.asset_search.textChanged.connect(self.filter_asset_list)
            left_col.addWidget(self.asset_search)

            fav_row = QHBoxLayout()
            self.cb_favorites_only = QCheckBox("Csak kedvencek")
            self.cb_favorites_only.toggled.connect(self.on_favorites_filter_toggled)
            fav_row.addWidget(self.cb_favorites_only)
            self.btn_fav_toggle = QPushButton("Kedvenc ☆ váltás")
            self.btn_fav_toggle.clicked.connect(self.toggle_favorite_selection)
            fav_row.addWidget(self.btn_fav_toggle)
            left_col.addLayout(fav_row)

            cur_row = QHBoxLayout()
            cur_row.addWidget(QLabel("Megjelenítés:"))
            self.currency_combo = QComboBox()
            self.currency_combo.addItems(["Auto (HUF ha elérhető)", "Mindig USD"])
            self.currency_combo.currentIndexChanged.connect(self.on_display_currency_changed)
            cur_row.addWidget(self.currency_combo, 1)
            left_col.addLayout(cur_row)

            self.list_widget = QListWidget()
            self.list_widget.setSelectionMode(
                QAbstractItemView.SelectionMode.ExtendedSelection
            )
            for name in ASSETS:
                self.list_widget.addItem(name)
            self.list_widget.setCurrentRow(0)
            self.list_widget.setMinimumWidth(280)
            left_col.addWidget(self.list_widget, 1)
            left_panel = QWidget()
            left_panel.setLayout(left_col)
            layout.addWidget(left_panel)

            right = QVBoxLayout()
            right.setSpacing(10)

            self.label = QLabel("🤖 AI + Indikátor Elemző Pro")
            self.label.setObjectName("title_label")
            right.addWidget(self.label)

            stats_grid = QGridLayout()
            self.stats_assets = QLabel("Kivalasztva: 0")
            self.stats_decisions = QLabel("Jelzesek: Vetel 0 | Eladas 0 | Varj 0")
            self.stats_update = QLabel("Utolso frissites: -")
            stats_grid.addWidget(self.stats_assets, 0, 0)
            stats_grid.addWidget(self.stats_decisions, 0, 1)
            stats_grid.addWidget(self.stats_update, 1, 0, 1, 2)
            right.addLayout(stats_grid)

            action_row = QHBoxLayout()

            self.btn_select_all = QPushButton("Összes kijelölése")
            self.btn_select_all.clicked.connect(self.select_all_assets)
            action_row.addWidget(self.btn_select_all)

            self.btn_clear = QPushButton("Kimenet törlése")
            self.btn_clear.clicked.connect(self.output_clear)
            action_row.addWidget(self.btn_clear)

            self.btn_set_amount = QPushButton("Összeg beállítása")
            self.btn_set_amount.clicked.connect(self.set_invest_amount)
            action_row.addWidget(self.btn_set_amount)

            right.addLayout(action_row)

            self.tabs = QTabWidget()

            analysis_tab = QWidget()
            analysis_layout = QVBoxLayout()
            out_row = QHBoxLayout()
            self.btn_copy_output = QPushButton("Kimenet vágólapra")
            self.btn_copy_output.clicked.connect(self.copy_output_to_clipboard)
            out_row.addWidget(self.btn_copy_output)
            out_row.addStretch(1)
            analysis_layout.addLayout(out_row)
            self.output = QTextEdit()
            self.output.setReadOnly(True)
            self.output.setPlaceholderText("Az elemzes eredmenye itt fog megjelenni...")
            analysis_layout.addWidget(self.output)
            analysis_tab.setLayout(analysis_layout)
            self.tabs.addTab(analysis_tab, "Elemzes")

            chart_tab = QWidget()
            chart_outer = QVBoxLayout()
            self._chart_range = ("1d", "5m")
            chart_btn_row = QHBoxLayout()
            self.chart_range_specs = [
                ("1 nap (élő)", "1d", "5m"),
                ("5 nap", "5d", "15m"),
                ("1 hó", "1mo", "1h"),
                ("3 hó", "3mo", "1d"),
            ]
            for label, rng, iv in self.chart_range_specs:

                def _make_chart_handler(r, i):
                    return lambda: self.set_chart_interval(r, i)

                b = QPushButton(label)
                b.clicked.connect(_make_chart_handler(rng, iv))
                chart_btn_row.addWidget(b)
            chart_btn_row.addStretch(1)
            chart_outer.addLayout(chart_btn_row)

            chart_opts_row = QHBoxLayout()
            self.cb_compare_chart = QCheckBox("2 eszköz összehasonlítás (index 100 = indulás)")
            self.cb_compare_chart.toggled.connect(self.refresh_price_chart)
            chart_opts_row.addWidget(self.cb_compare_chart)
            self.cb_bb_chart = QCheckBox("Bollinger sávok")
            self.cb_bb_chart.toggled.connect(self.refresh_price_chart)
            chart_opts_row.addWidget(self.cb_bb_chart)
            self.cb_pattern_detect = QCheckBox("Alakzatfelismerés (M / W / V / ∧)")
            self.cb_pattern_detect.setChecked(True)
            self.cb_pattern_detect.toggled.connect(self.refresh_price_chart)
            chart_opts_row.addWidget(self.cb_pattern_detect)
            chart_opts_row.addStretch(1)
            chart_outer.addLayout(chart_opts_row)

            self.chart_subtitle = QLabel("Válassz eszközt; az első kijelölt sor árfolyama jelenik meg.")
            self.chart_subtitle.setWordWrap(True)
            chart_outer.addWidget(self.chart_subtitle)

            # Gyertyadiagram widget (QPainter)
            self.candle_widget = CandlestickWidget()
            self.candle_widget.setMinimumHeight(380)
            chart_outer.addWidget(self.candle_widget, 1)

            # Összehasonlító nézet (eredeti QChartView marad, rejtve ha nem kell)
            self.chart_view = QChartView()
            self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.chart_view.setMinimumHeight(320)
            self.chart_view.setVisible(False)   # gyertya módban rejtve
            chart_outer.addWidget(self.chart_view, 1)

            chart_tab.setLayout(chart_outer)
            self.tabs.addTab(chart_tab, "📈 Árfolyam diagram")

            alerts_tab = QWidget()
            alerts_layout = QVBoxLayout()
            self.alert_output = QTextEdit()
            self.alert_output.setReadOnly(True)
            self.alert_output.setPlaceholderText("Elo riasztasok es esemenyek...")
            alerts_layout.addWidget(self.alert_output)
            self.btn_clear_alerts = QPushButton("Ertesitesi naplo torlese")
            self.btn_clear_alerts.clicked.connect(self.clear_alerts)
            alerts_layout.addWidget(self.btn_clear_alerts)
            alerts_tab.setLayout(alerts_layout)
            self.tabs.addTab(alerts_tab, "Ertesitesek")

            portfolio_tab = QWidget()
            portfolio_layout = QVBoxLayout()
            self.portfolio_output = QTextEdit()
            self.portfolio_output.setReadOnly(True)
            self.portfolio_output.setPlaceholderText("Portfolio osszegzes itt jelenik meg...")
            portfolio_layout.addWidget(self.portfolio_output)
            portfolio_tab.setLayout(portfolio_layout)
            self.tabs.addTab(portfolio_tab, "Portfolio")

            corr_tab = QWidget()
            corr_layout = QVBoxLayout()
            self.btn_correlation = QPushButton("Korreláció frissítése (kijelölt eszközök)")
            self.btn_correlation.clicked.connect(self.refresh_correlation_view)
            corr_layout.addWidget(self.btn_correlation)
            self.corr_output = QTextEdit()
            self.corr_output.setReadOnly(True)
            self.corr_output.setPlaceholderText("Log-hozam korrelációs mátrix…")
            corr_layout.addWidget(self.corr_output)
            corr_tab.setLayout(corr_layout)
            self.tabs.addTab(corr_tab, "Korreláció")

            hist_tab = QWidget()
            hist_layout = QVBoxLayout()
            hist_row = QHBoxLayout()
            self.history_filter = QLineEdit()
            self.history_filter.setPlaceholderText("Szűrés eszköz névre…")
            self.btn_history_load = QPushButton("Előzmények betöltése (SQLite)")
            self.btn_history_load.clicked.connect(self.load_history_table)
            hist_row.addWidget(self.history_filter)
            hist_row.addWidget(self.btn_history_load)
            hist_layout.addLayout(hist_row)
            self.history_table = QTableWidget()
            self.history_table.setColumnCount(9)
            self.history_table.setHorizontalHeaderLabels(
                ["Idő", "Eszköz", "Dev", "Most", "Célár", "Döntés", "RSI", "AI fel %", "Pontosság"]
            )
            hist_layout.addWidget(self.history_table)
            hist_tab.setLayout(hist_layout)
            self.tabs.addTab(hist_tab, "Előzmények")

            news_tab = QWidget()
            news_layout = QVBoxLayout()
            self.btn_news = QPushButton("Yahoo hírcsatorna (első kijelölt)")
            self.btn_news.clicked.connect(self.load_news_for_selection)
            news_layout.addWidget(self.btn_news)
            self.news_output = QTextEdit()
            self.news_output.setReadOnly(True)
            news_layout.addWidget(self.news_output)
            news_tab.setLayout(news_layout)
            self.tabs.addTab(news_tab, "Hírek")

            settings_tab = QWidget()
            settings_layout = QVBoxLayout()
            self.auto_clear_checkbox = QCheckBox("Elemzes torlese minden frissites elott")
            self.auto_clear_checkbox.setChecked(self.auto_clear_analysis)
            self.auto_clear_checkbox.toggled.connect(self.toggle_auto_clear)
            settings_layout.addWidget(self.auto_clear_checkbox)

            self.sound_alert_checkbox = QCheckBox("Hangriasztas engedelyezve")
            self.sound_alert_checkbox.setChecked(self.sound_alerts_enabled)
            self.sound_alert_checkbox.toggled.connect(self.toggle_sound_alerts)
            settings_layout.addWidget(self.sound_alert_checkbox)

            self.csv_autosave_checkbox = QCheckBox("CSV automatikus mentes eloben")
            self.csv_autosave_checkbox.setChecked(self.csv_autosave_enabled)
            self.csv_autosave_checkbox.toggled.connect(self.toggle_csv_autosave)
            settings_layout.addWidget(self.csv_autosave_checkbox)

            self.btn_csv_path = QPushButton("CSV fajl: live_history.csv")
            self.btn_csv_path.clicked.connect(self.set_csv_path)
            settings_layout.addWidget(self.btn_csv_path)

            self.btn_alert_threshold = QPushButton("Riasztasi kuszob: 0.80%")
            self.btn_alert_threshold.clicked.connect(self.set_alert_threshold)
            settings_layout.addWidget(self.btn_alert_threshold)

            self.btn_telegram = QPushButton("⚙️  Telegram beállítás (token + chat ID)")
            self.btn_telegram.setObjectName("telegram_btn")
            self.btn_telegram.clicked.connect(self.configure_telegram)
            settings_layout.addWidget(self.btn_telegram)

            tg_action_row = QHBoxLayout()
            self.btn_telegram_test = QPushButton("📨  Telegram tesztüzenet")
            self.btn_telegram_test.setObjectName("telegram_btn")
            self.btn_telegram_test.clicked.connect(self.send_telegram_test)
            tg_action_row.addWidget(self.btn_telegram_test)

            self.btn_telegram_report = QPushButton("📊  Riport küldése Telegramra")
            self.btn_telegram_report.setObjectName("telegram_btn")
            self.btn_telegram_report.clicked.connect(self.send_telegram_full_report)
            tg_action_row.addWidget(self.btn_telegram_report)
            settings_layout.addLayout(tg_action_row)

            self.telegram_status = QLabel("📵  Telegram: kikapcsolva")
            settings_layout.addWidget(self.telegram_status)

            self.ai_checkbox = QCheckBox("Felho AI magyarazat engedelyezve")
            self.ai_checkbox.setChecked(self.ai_commentary_enabled)
            self.ai_checkbox.toggled.connect(self.toggle_ai_commentary)
            settings_layout.addWidget(self.ai_checkbox)

            self.btn_ai_config = QPushButton("AI beallitas (API kulcs + modell)")
            self.btn_ai_config.clicked.connect(self.configure_ai)
            settings_layout.addWidget(self.btn_ai_config)

            self.ai_status = QLabel("AI: kikapcsolva")
            settings_layout.addWidget(self.ai_status)

            self.btn_export_html = QPushButton("HTML riport mentése…")
            self.btn_export_html.clicked.connect(self.export_html_report)
            settings_layout.addWidget(self.btn_export_html)

            self.btn_edit_alert_rules = QPushButton("Egyedi ár/RSI szabályok (JSON)…")
            self.btn_edit_alert_rules.clicked.connect(self.edit_alert_rules_dialog)
            settings_layout.addWidget(self.btn_edit_alert_rules)

            sched_row = QHBoxLayout()
            self.cb_schedule_analysis = QCheckBox("Napi ütemezett elemzés:")
            self.time_schedule = QTimeEdit()
            self.time_schedule.setDisplayFormat("HH:mm")
            self.time_schedule.setTime(QTime(9, 0))
            sched_row.addWidget(self.cb_schedule_analysis)
            sched_row.addWidget(self.time_schedule)
            settings_layout.addLayout(sched_row)
            self.schedule_timer = QTimer(self)
            self.schedule_timer.timeout.connect(self.schedule_tick)
            self.schedule_timer.start(30_000)

            settings_layout.addStretch(1)
            settings_tab.setLayout(settings_layout)
            self.tabs.addTab(settings_tab, "Beallitasok")

            right.addWidget(self.tabs)

            live_row = QHBoxLayout()

            self.btn = QPushButton("▶  Elemzés")
            self.btn.setObjectName("primary_btn")
            self.btn.clicked.connect(self.run_analysis)
            live_row.addWidget(self.btn)

            self.btn_live = QPushButton("📡  Élő mód indítása")
            self.btn_live.setObjectName("live_btn")
            self.btn_live.clicked.connect(self.toggle_live_mode)
            live_row.addWidget(self.btn_live)

            self.btn_interval = QPushButton("⏱  Időköz: 30s")
            self.btn_interval.clicked.connect(self.set_live_interval)
            live_row.addWidget(self.btn_interval)

            right.addLayout(live_row)

            self.live_status = QLabel("🔴  Élő mód: kikapcsolva")
            right.addWidget(self.live_status)

            layout.addLayout(right)
            self.setLayout(layout)
            self.list_widget.itemSelectionChanged.connect(self.update_selected_count)
            self.list_widget.itemSelectionChanged.connect(self.refresh_price_chart)
            self.update_selected_count()
            self.refresh_telegram_status()
            self.refresh_ai_status()
            self.refresh_price_chart()

        def apply_styles(self):
            self.setStyleSheet(
                """
                QWidget {
                    background-color: #0d1117;
                    color: #c9d1d9;
                    font-family: 'Segoe UI', 'Inter', Arial, sans-serif;
                    font-size: 13px;
                }
                QLabel {
                    font-size: 13px;
                    color: #c9d1d9;
                }
                QLabel#title_label {
                    font-size: 18px;
                    font-weight: 700;
                    color: #58a6ff;
                    padding: 4px 0px;
                }
                QTabWidget::pane {
                    border: 1px solid #30363d;
                    border-radius: 10px;
                    background-color: #161b22;
                    margin-top: -1px;
                }
                QTabBar::tab {
                    background: #0d1117;
                    color: #8b949e;
                    padding: 9px 16px;
                    border: 1px solid #30363d;
                    border-bottom: none;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    margin-right: 3px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QTabBar::tab:selected {
                    background: #1f6feb;
                    color: #ffffff;
                    border-color: #1f6feb;
                }
                QTabBar::tab:hover:!selected {
                    background: #21262d;
                    color: #e6edf3;
                }
                QListWidget, QTextEdit {
                    background-color: #161b22;
                    border: 1px solid #30363d;
                    border-radius: 8px;
                    padding: 6px;
                    color: #c9d1d9;
                    selection-background-color: #1f6feb;
                    selection-color: #ffffff;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 12px;
                    line-height: 1.5;
                }
                QListWidget::item {
                    padding: 4px 6px;
                    border-radius: 4px;
                }
                QListWidget::item:selected {
                    background-color: #1f6feb;
                    color: #ffffff;
                }
                QListWidget::item:hover:!selected {
                    background-color: #21262d;
                }
                QPushButton {
                    background-color: #21262d;
                    color: #c9d1d9;
                    border: 1px solid #30363d;
                    border-radius: 8px;
                    padding: 8px 14px;
                    font-weight: 600;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #30363d;
                    color: #e6edf3;
                    border-color: #8b949e;
                }
                QPushButton:pressed {
                    background-color: #161b22;
                }
                QPushButton#primary_btn {
                    background-color: #238636;
                    color: #ffffff;
                    border-color: #2ea043;
                    font-size: 13px;
                    padding: 9px 18px;
                }
                QPushButton#primary_btn:hover {
                    background-color: #2ea043;
                    border-color: #3fb950;
                }
                QPushButton#live_btn {
                    background-color: #1f6feb;
                    color: #ffffff;
                    border-color: #388bfd;
                    font-size: 13px;
                    padding: 9px 18px;
                }
                QPushButton#live_btn:hover {
                    background-color: #388bfd;
                }
                QPushButton#live_btn_active {
                    background-color: #da3633;
                    color: #ffffff;
                    border-color: #f85149;
                    font-size: 13px;
                    padding: 9px 18px;
                }
                QPushButton#live_btn_active:hover {
                    background-color: #f85149;
                }
                QPushButton#telegram_btn {
                    background-color: #1e3a5f;
                    color: #58a6ff;
                    border-color: #1f6feb;
                }
                QPushButton#telegram_btn:hover {
                    background-color: #1f6feb;
                    color: #ffffff;
                }
                QPushButton#danger_btn {
                    background-color: #3d1a1a;
                    color: #f85149;
                    border-color: #da3633;
                }
                QPushButton#danger_btn:hover {
                    background-color: #da3633;
                    color: #ffffff;
                }
                QCheckBox {
                    font-size: 13px;
                    color: #c9d1d9;
                    spacing: 8px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border: 1px solid #30363d;
                    border-radius: 4px;
                    background-color: #21262d;
                }
                QCheckBox::indicator:checked {
                    background-color: #1f6feb;
                    border-color: #388bfd;
                }
                QComboBox, QTimeEdit {
                    background-color: #21262d;
                    color: #c9d1d9;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 5px 10px;
                    selection-background-color: #1f6feb;
                }
                QComboBox::drop-down {
                    border: none;
                    padding-right: 8px;
                }
                QComboBox QAbstractItemView {
                    background-color: #21262d;
                    border: 1px solid #30363d;
                    color: #c9d1d9;
                    selection-background-color: #1f6feb;
                }
                QTableWidget {
                    background-color: #161b22;
                    gridline-color: #21262d;
                    border: 1px solid #30363d;
                    border-radius: 8px;
                    color: #c9d1d9;
                    alternate-background-color: #1a2030;
                }
                QTableWidget::item:selected {
                    background-color: #1f4068;
                }
                QHeaderView::section {
                    background-color: #21262d;
                    color: #8b949e;
                    padding: 7px 6px;
                    border: none;
                    border-right: 1px solid #30363d;
                    border-bottom: 1px solid #30363d;
                    font-weight: 600;
                    font-size: 11px;
                    text-transform: uppercase;
                }
                QScrollBar:vertical {
                    background: #0d1117;
                    width: 8px;
                    border-radius: 4px;
                }
                QScrollBar::handle:vertical {
                    background: #30363d;
                    border-radius: 4px;
                    min-height: 24px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #8b949e;
                }
                QScrollBar:horizontal {
                    background: #0d1117;
                    height: 8px;
                    border-radius: 4px;
                }
                QScrollBar::handle:horizontal {
                    background: #30363d;
                    border-radius: 4px;
                    min-width: 24px;
                }
                QLineEdit {
                    background-color: #21262d;
                    color: #c9d1d9;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-size: 12px;
                }
                QLineEdit:focus {
                    border-color: #1f6feb;
                }
                QLineEdit::placeholder {
                    color: #484f58;
                }
                QSplitter::handle {
                    background: #30363d;
                }
                """
            )

        def resolve_rate_currency(self):
            if self.currency_combo.currentIndex() == 1:
                return 1.0, "USD", "Kézi USD megjelenítés"
            return get_effective_rate()

        def on_display_currency_changed(self, _index=None):
            self.refresh_price_chart()

        def on_favorites_filter_toggled(self, _checked=False):
            self.filter_asset_list(self.asset_search.text())

        def toggle_favorite_selection(self):
            for it in self.list_widget.selectedItems():
                n = it.text()
                if n in self.favorite_names:
                    self.favorite_names.discard(n)
                else:
                    self.favorite_names.add(n)
            save_favorites(sorted(self.favorite_names))
            self.log_alert(f"Kedvencek frissítve: {len(self.favorite_names)} db")

        def schedule_tick(self):
            if not self.cb_schedule_analysis.isChecked():
                return
            if self.invest_amount is None:
                return
            now = QDateTime.currentDateTime()
            tt = self.time_schedule.time()
            if now.time().hour() != tt.hour() or now.time().minute() != tt.minute():
                return
            dkey = now.toString("yyyy-MM-dd")
            if self._last_scheduled_run_date == dkey:
                return
            self._last_scheduled_run_date = dkey
            self.log_alert(f"Ütemezett elemzés: {dkey} {tt.toString('HH:mm')}")
            self.run_analysis(prompt_amount=False)

        def edit_alert_rules_dialog(self):
            raw = json.dumps(self.custom_rules, ensure_ascii=False, indent=2)
            txt, ok = QInputDialog.getMultiLineText(
                self,
                "Egyedi riasztási szabályok",
                'JSON lista. Mezők: asset (vagy "*"), rule: price_above|price_below|rsi_above|rsi_below, value (szám).\n'
                "Példa: [{\"asset\": \"Apple\", \"rule\": \"rsi_below\", \"value\": 30}]",
                raw,
            )
            if not ok:
                return
            try:
                data = json.loads(txt)
                if not isinstance(data, list):
                    raise ValueError("A gyökérnek listanek kell lennie.")
                self.custom_rules = data
                save_custom_alert_rules(data)
                self.log_alert("Riasztási szabályok elmentve.")
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                self.log_alert(f"Szabály JSON hiba: {e}")

        def export_html_report(self):
            if not self._last_results:
                self.log_alert("Nincs mit menteni — futtass előbb elemzést.")
                return
            path, _sel = QFileDialog.getSaveFileName(
                self,
                "HTML riport",
                str(Path.home() / "ai_tracker_riport.html"),
                "HTML (*.html)",
            )
            if not path:
                return
            _, cur, _ = self.resolve_rate_currency()
            doc = build_html_report(self._last_results, cur)
            try:
                Path(path).write_text(doc, encoding="utf-8")
                self.log_alert(f"HTML mentve: {path}")
            except OSError as e:
                self.log_alert(f"HTML mentési hiba: {e}")

        def refresh_correlation_view(self):
            items = self.selected_asset_items()
            rate, cur, rw = self.resolve_rate_currency()
            mat, names = correlation_matrix_log_returns(items, rate, cur)
            txt = format_correlation_table(mat, names)
            if rw:
                txt += f"\n\nMegjegyzés: {rw}"
            self.corr_output.setPlainText(txt)

        def load_history_table(self):
            needle = self.history_filter.text().strip()
            rows = db_search_history(needle, limit=500)
            self.history_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    disp = "" if val is None else str(val)
                    self.history_table.setItem(i, j, QTableWidgetItem(disp))

        def load_news_for_selection(self):
            name, sym = self.chart_target_symbol()
            if not sym:
                self.news_output.setPlainText("Válassz eszközt a listában.")
                return
            items = fetch_yahoo_headlines(sym, limit=12)
            if not items:
                self.news_output.setPlainText(
                    f"Nincs hír, vagy az RSS nem elérhető ({sym}). Próbáld újra később."
                )
                return
            lines = [f"{name} ({sym})", ""]
            for it in items:
                lines.append(it.get("title", ""))
                if it.get("link"):
                    lines.append(f"  {it['link']}")
                lines.append("")
            self.news_output.setPlainText("\n".join(lines))

        def select_all_assets(self):
            self.list_widget.selectAll()

        def filter_asset_list(self, text):
            needle = (text or "").strip().lower()
            selected_names = {i.text() for i in self.list_widget.selectedItems()}
            self.list_widget.clear()
            for name in ASSETS:
                if self.cb_favorites_only.isChecked() and name not in self.favorite_names:
                    continue
                if not needle or needle in name.lower():
                    self.list_widget.addItem(name)
            for i in range(self.list_widget.count()):
                it = self.list_widget.item(i)
                if it.text() in selected_names:
                    it.setSelected(True)
            self.update_selected_count()

        def copy_output_to_clipboard(self):
            QApplication.clipboard().setText(self.output.toPlainText())

        def set_chart_interval(self, rng, interval):
            self._chart_range = (rng, interval)
            self.refresh_price_chart()

        def chart_target_symbol(self):
            names = [i.text() for i in self.list_widget.selectedItems()]
            if names:
                n = names[0]
                return n, ASSETS.get(n)
            row = self.list_widget.currentRow()
            if row >= 0:
                it = self.list_widget.item(row)
                if it:
                    n = it.text()
                    return n, ASSETS.get(n)
            return None, None

        def refresh_price_chart(self):
            rng, interval = self._chart_range

            def _x_format(r):
                if r == "1d":
                    return "HH:mm"
                if r == "5d":
                    return "ddd HH:mm"
                if r == "1mo":
                    return "d MMM"
                return "yyyy-MM-dd"

            try:
                rate, currency, rate_warning = self.resolve_rate_currency()
                fx_note = f" FX: {rate_warning}" if rate_warning else ""

                # ---- Összehasonlítás mód (marad QChart vonaldiagramm) ----
                if self.cb_compare_chart.isChecked():
                    self.candle_widget.setVisible(False)
                    self.chart_view.setVisible(True)
                    empty = QChart()
                    sel = [i.text() for i in self.list_widget.selectedItems()]
                    if len(sel) < 2:
                        self.chart_view.setChart(empty)
                        self.chart_subtitle.setText(
                            "Összehasonlításhoz jelölj ki legalább két eszközt a listában."
                        )
                        return
                    n1, s1 = sel[0], ASSETS[sel[0]]
                    n2, s2 = sel[1], ASSETS[sel[1]]
                    m1 = yahoo_price_display_multiplier(s1, rate, currency)
                    m2 = yahoo_price_display_multiplier(s2, rate, currency)
                    snap1 = fetch_chart_series(s1, rng, interval)
                    snap2 = fetch_chart_series(s2, rng, interval)
                    d1 = {int(t): float(p) * m1 for t, p in snap1["points"]}
                    d2 = {int(t): float(p) * m2 for t, p in snap2["points"]}
                    common = sorted(set(d1.keys()) & set(d2.keys()))
                    if len(common) < 2:
                        self.chart_view.setChart(empty)
                        self.chart_subtitle.setText("Nincs elég közös időbélyeg a két eszközhöz.")
                        return
                    base1 = d1[common[0]]
                    base2 = d2[common[0]]
                    if base1 == 0 or base2 == 0:
                        self.chart_view.setChart(empty)
                        self.chart_subtitle.setText("Nulla bázisár — nem rajzolható index.")
                        return
                    ser1 = QLineSeries()
                    ser1.setName(n1[:18])
                    ser2 = QLineSeries()
                    ser2.setName(n2[:18])
                    for t in common:
                        ser1.append(float(t), 100.0 * d1[t] / base1)
                        ser2.append(float(t), 100.0 * d2[t] / base2)
                    p1 = QPen(QColor("#22c55e"))
                    p1.setWidthF(2.0)
                    ser1.setPen(p1)
                    p2 = QPen(QColor("#38bdf8"))
                    p2.setWidthF(2.0)
                    ser2.setPen(p2)
                    chart = QChart()
                    chart.addSeries(ser1)
                    chart.addSeries(ser2)
                    chart.legend().setVisible(True)
                    chart.setBackgroundBrush(QBrush(QColor("#161b22")))
                    chart.setTitleBrush(QBrush(QColor("#c9d1d9")))
                    chart.setPlotAreaBackgroundVisible(True)
                    chart.setPlotAreaBackgroundBrush(QBrush(QColor("#0d1117")))
                    chart.setTitle(f"Relatív teljesítmény (100 = első közös pont) — {currency}")
                    dt_min = QDateTime.fromMSecsSinceEpoch(int(common[0]))
                    dt_max = QDateTime.fromMSecsSinceEpoch(int(common[-1]))
                    axis_x = QDateTimeAxis()
                    axis_x.setFormat(_x_format(rng))
                    axis_x.setTitleText("Idő")
                    axis_x.setRange(dt_min, dt_max)
                    axis_y = QValueAxis()
                    axis_y.setTitleText("Index")
                    axis_y.setLabelFormat("%.1f")
                    vals = [100.0 * d1[t] / base1 for t in common] + [
                        100.0 * d2[t] / base2 for t in common
                    ]
                    ymin, ymax = min(vals), max(vals)
                    pad = (ymax - ymin) * 0.08 if ymax > ymin else 1.0
                    axis_y.setRange(ymin - pad, ymax + pad)
                    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
                    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
                    ser1.attachAxis(axis_x)
                    ser1.attachAxis(axis_y)
                    ser2.attachAxis(axis_x)
                    ser2.attachAxis(axis_y)
                    self.chart_view.setChart(chart)
                    self.chart_subtitle.setText(
                        f"{n1} vs {n2} | {rng}/{interval}. Élő módban frissül.{fx_note}"
                    )
                    return

                # ---- Gyertyadiagram mód ----
                self.candle_widget.setVisible(True)
                self.chart_view.setVisible(False)

                name, symbol = self.chart_target_symbol()
                if not symbol or not name:
                    self.candle_widget.set_data([], [], "Válassz eszközt a listában")
                    self.chart_subtitle.setText(
                        "Válassz eszközt; az első kijelölt sor árfolyama jelenik meg."
                    )
                    return

                mult = yahoo_price_display_multiplier(symbol, rate, currency)
                snap = fetch_ohlc_series(symbol, rng, interval)
                raw_candles = snap["candles"]

                # Szorzó alkalmazása minden árra
                candles = [
                    (ts, o * mult, h * mult, l * mult, c * mult)
                    for ts, o, h, l, c in raw_candles
                ]

                # Alakzatfelismerés
                patterns = []
                if self.cb_pattern_detect.isChecked() and len(candles) >= 10:
                    patterns = detect_patterns(raw_candles, mult=mult)

                # Bollinger overlay → jelzőpontok a gyertyadiagramon felett (szöveges)
                bb_note = ""
                if self.cb_bb_chart.isChecked() and len(candles) >= 21:
                    closes_arr = np.array([c[4] for c in candles], dtype=float)
                    mu = float(np.mean(closes_arr[-20:]))
                    sd = float(np.std(closes_arr[-20:]))
                    bb_note = (
                        f" | BB: fel {(mu + 2*sd):,.2f}  közép {mu:,.2f}  al {(mu - 2*sd):,.2f} {currency}"
                    )

                # X tengelycímkék generálása (max 8 db egyenletesen elosztva)
                n = len(candles)
                x_labels = []
                fmt = _x_format(rng)
                label_count = min(8, n)
                step = max(1, n // label_count)
                for i in range(0, n, step):
                    ts_ms = candles[i][0]
                    dt = QDateTime.fromMSecsSinceEpoch(ts_ms)
                    x_labels.append((i, dt.toString(fmt)))

                chg = regular_market_change_pct(snap["meta"])
                title_str = f"{name}  |  {currency}"
                if chg is not None:
                    arrow = "▲" if chg >= 0 else "▼"
                    title_str += f"  {arrow} {chg:+.2f}%"
                title_str += f"  |  {rng}/{interval}"

                self.candle_widget.set_data(
                    candles, patterns, title=title_str,
                    currency=currency, x_labels=x_labels
                )

                # Subtitle: alakzatösszefoglaló
                if patterns:
                    pat_texts = "  |  ".join(
                        f"{p['emoji']} {p['label']}" for p in patterns
                    )
                    pat_summary = f"  ●  Alakzatok: {pat_texts}"
                else:
                    pat_summary = "  ●  Alakzat: nincs egyértelmű"

                self.chart_subtitle.setText(
                    f"Gyertyadiagram — {rng}/{interval}{bb_note}{pat_summary}{fx_note}"
                )

            except Exception as e:
                self.candle_widget.set_data([], [], f"Diagram hiba: {e}")
                self.chart_subtitle.setText(f"⚠ Diagram hiba — {e}")

        def output_clear(self):
            self.output.clear()

        def clear_alerts(self):
            self.alert_output.clear()

        def update_selected_count(self):
            selected = len(self.list_widget.selectedItems())
            if selected == 0:
                selected = len(ASSETS)
            self.stats_assets.setText(f"Kivalasztva: {selected}")

        def toggle_auto_clear(self, checked):
            self.auto_clear_analysis = bool(checked)

        def toggle_sound_alerts(self, checked):
            self.sound_alerts_enabled = bool(checked)

        def toggle_csv_autosave(self, checked):
            self.csv_autosave_enabled = bool(checked)

        def toggle_ai_commentary(self, checked):
            self.ai_commentary_enabled = bool(checked)
            self.refresh_ai_status()

        def refresh_ai_status(self):
            if self.ai_commentary_enabled and self.ai_api_key:
                self.ai_status.setText(f"AI: aktiv ({self.ai_model})")
            elif self.ai_api_key:
                self.ai_status.setText(f"AI: kulcs beallitva ({self.ai_model})")
            else:
                self.ai_status.setText("AI: kikapcsolva")

        def configure_ai(self):
            key, ok_key = QInputDialog.getText(
                self,
                "AI API kulcs",
                "OpenAI API key:",
                text=self.ai_api_key,
            )
            if not ok_key:
                return
            model, ok_model = QInputDialog.getText(
                self,
                "AI modell",
                "Model:",
                text=self.ai_model,
            )
            if not ok_model:
                return
            self.ai_api_key = key.strip()
            self.ai_model = model.strip() if model.strip() else OPENAI_MODEL_DEFAULT
            self.refresh_ai_status()
            if self.ai_api_key:
                self.log_alert(f"AI beallitva: {self.ai_model}")

        def set_csv_path(self):
            value, ok = QInputDialog.getText(
                self,
                "CSV mentesi utvonal",
                "Fajl eleresi ut:",
                text=self.csv_path,
            )
            if ok and value.strip():
                self.csv_path = value.strip()
                self.btn_csv_path.setText(f"CSV fajl: {Path(self.csv_path).name}")
                self.log_alert(f"CSV mentesi utvonal: {self.csv_path}")

        def set_alert_threshold(self):
            value, ok = QInputDialog.getDouble(
                self,
                "Riasztasi kuszob",
                "Szazalek:",
                self.alert_threshold_pct,
                0.05,
                50.0,
                2,
            )
            if ok:
                self.alert_threshold_pct = value
                self.btn_alert_threshold.setText(f"Riasztasi kuszob: {value:.2f}%")

        def refresh_telegram_status(self):
            if self.telegram_enabled and self.telegram_bot_token and self.telegram_chat_id:
                short_id = self.telegram_chat_id[:12] + ("…" if len(self.telegram_chat_id) > 12 else "")
                self.telegram_status.setText(f"🟢  Telegram: aktív (chat: {short_id})")
            elif self.telegram_bot_token or self.telegram_chat_id:
                self.telegram_status.setText("🟡  Telegram: részben beállítva")
            else:
                self.telegram_status.setText("📵  Telegram: kikapcsolva")

        def configure_telegram(self):
            token, ok_token = QInputDialog.getText(
                self,
                "Telegram bot token",
                "Bot token (BotFather által adott):",
                text=self.telegram_bot_token,
            )
            if not ok_token:
                return
            chat_id, ok_chat = QInputDialog.getText(
                self,
                "Telegram chat ID",
                "Chat ID (pl. @csatornád vagy numerikus):",
                text=self.telegram_chat_id,
            )
            if not ok_chat:
                return
            self.telegram_bot_token = token.strip()
            self.telegram_chat_id = chat_id.strip()
            self.telegram_enabled = bool(self.telegram_bot_token and self.telegram_chat_id)
            # Persist to disk so it survives restarts
            if self.telegram_bot_token or self.telegram_chat_id:
                save_telegram_config(self.telegram_bot_token, self.telegram_chat_id)
            self.refresh_telegram_status()
            if self.telegram_enabled:
                ok, err = send_telegram_message(
                    self.telegram_bot_token,
                    self.telegram_chat_id,
                    "🤖 <b>AI Eszközelemző Pro</b>\n✅ Telegram kapcsolat aktív és működik!",
                )
                if ok:
                    self.log_alert("✅ Telegram tesztüzenet elküldve.")
                else:
                    self.log_alert(f"❌ Telegram hiba: {err}")

        def send_telegram_test(self):
            """Send a standalone test message to Telegram."""
            if not self.telegram_enabled:
                self.log_alert("❌ Telegram nincs beállítva. Először konfiguráld.")
                return
            msg = (
                "🤖 <b>AI Eszközelemző Pro – Tesztüzenet</b>\n"
                f"🕐 {QDateTime.currentDateTime().toString('yyyy-MM-dd HH:mm:ss')}\n"
                "✅ Kapcsolat rendben."
            )
            ok, err = send_telegram_message(self.telegram_bot_token, self.telegram_chat_id, msg)
            if ok:
                self.log_alert("✅ Telegram tesztüzenet elküldve.")
            else:
                self.log_alert(f"❌ Telegram hiba: {err}")

        def send_telegram_full_report(self):
            """Send the last analysis results to Telegram as formatted messages."""
            if not self.telegram_enabled:
                self.log_alert("❌ Telegram nincs beállítva. Először konfiguráld.")
                return
            if not self._last_results:
                self.log_alert("❌ Nincs elemzési eredmény. Futtass elemzést előbb.")
                return
            _, currency, _ = self.resolve_rate_currency()
            header = (
                f"📊 <b>AI Eszközelemző Pro – Elemzési Riport</b>\n"
                f"🕐 {QDateTime.currentDateTime().toString('yyyy-MM-dd HH:mm:ss')}\n"
                f"💱 Deviza: <b>{html.escape(currency)}</b>\n"
                f"📋 Eszközök: <b>{len(self._last_results)}</b>"
            )
            ok, err = send_telegram_message(self.telegram_bot_token, self.telegram_chat_id, header)
            if not ok:
                self.log_alert(f"❌ Telegram fejléc hiba: {err}")
                return
            sent, failed = 0, 0
            for result in self._last_results:
                msg = format_telegram_result(result, currency)
                ok, err = send_telegram_message(self.telegram_bot_token, self.telegram_chat_id, msg)
                if ok:
                    sent += 1
                else:
                    failed += 1
                    self.log_alert(f"❌ Telegram küldési hiba ({result.get('name')}): {err}")
                time.sleep(0.3)  # Telegram rate limit
            self.log_alert(f"📊 Riport elküldve: {sent} sikeres, {failed} hibás.")

        def trigger_alert_channels(self, message):
            notify_price_change("Pro riasztás", message)
            if self.sound_alerts_enabled:
                QApplication.beep()
            if self.telegram_enabled:
                tg_msg = format_telegram_alert(message)
                ok, err = send_telegram_message(
                    self.telegram_bot_token,
                    self.telegram_chat_id,
                    tg_msg,
                )
                if not ok:
                    self.log_alert(f"❌ Telegram küldés sikertelen: {err}")

        def log_alert(self, text):
            now_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
            self.alert_output.append(f"[{now_text}] {text}")

        def update_decision_stats(self, results):
            def normalize(text):
                return (
                    text.upper()
                    .replace("É", "E")
                    .replace("Á", "A")
                    .replace("Ó", "O")
                    .replace("Ö", "O")
                    .replace("Ő", "O")
                    .replace("Ú", "U")
                    .replace("Ü", "U")
                    .replace("Ű", "U")
                )

            buy = sum(1 for r in results if "VETEL" in normalize(r["decision"]))
            sell = sum(1 for r in results if "ELADAS" in normalize(r["decision"]))
            wait = max(0, len(results) - buy - sell)
            self.stats_decisions.setText(
                f"Jelzesek: Vetel {buy} | Eladas {sell} | Varj {wait}"
            )
            if buy > sell:
                color = "#22c55e"
            elif sell > buy:
                color = "#ef4444"
            else:
                color = "#f59e0b"
            self.stats_decisions.setStyleSheet(f"color: {color}; font-weight: 700;")

        def update_portfolio_tab(self, results, currency):
            if not results:
                self.portfolio_output.setPlainText("Nincs portfolio adat.")
                return
            total_current = sum(float(r["current"]) for r in results)
            total_future = sum(float(r["future"]) for r in results)
            avg_prob = sum(float(r["next_up_prob"]) for r in results) / len(results)
            total_deploy = sum(float(r["investment"]["deploy_amount"]) for r in results if r.get("investment"))
            total_input = sum(float(r["investment"]["amount"]) for r in results if r.get("investment"))
            lines = [
                "Portfolio osszegzes",
                "=" * 40,
                f"Eszkozok szama: {len(results)}",
                f"Ossz jelenlegi ertek (indikativ): {total_current:,.2f} {currency}",
                f"Ossz AI celar (1 ora): {total_future:,.2f} {currency}",
                f"Atlagos AI fel-valoszinuseg: {avg_prob * 100:.1f}%",
                f"Osszesitett javasolt tet: {total_deploy:,.2f} {currency}",
            ]
            if total_input > 0:
                lines.append(f"Kitettseg arany: {(total_deploy / total_input) * 100:.1f}%")
            lines.append("")
            lines.append("Eszkozonkenti gyorsnezet:")
            for r in results:
                lines.append(
                    f"- {r['name']}: {r['decision']} | Most: {r['current']:,.2f} {currency} | "
                    f"AI fel: {r['next_up_prob'] * 100:.1f}%"
                )
            self.portfolio_output.setPlainText("\n".join(lines))

        def set_invest_amount(self):
            rate, currency, _ = self.resolve_rate_currency()
            amount, ok = QInputDialog.getDouble(
                self,
                "Befektetés",
                f"Mennyit szeretnél befektetni? ({currency})",
                self.invest_amount if self.invest_amount is not None else 100_000.0,
                0.0,
                1e15,
                0,
            )
            if ok:
                self.invest_amount = amount
                self.output.append(f"Befektetési összeg beállítva: {int(amount):,} {currency}\n")

        def ensure_invest_amount(self):
            if self.invest_amount is None:
                self.set_invest_amount()
            return self.invest_amount is not None

        def set_live_interval(self):
            value, ok = QInputDialog.getInt(
                self,
                "Élő frissítés időköze",
                "Másodperc:",
                self.live_interval_sec,
                5,
                3600,
                1,
            )
            if ok:
                self.live_interval_sec = value
                self.btn_interval.setText(f"⏱  Időköz: {value}s")
                if self.live_timer.isActive():
                    self.live_timer.start(self.live_interval_sec * 1000)

        def toggle_live_mode(self):
            if self.live_timer.isActive():
                self.live_timer.stop()
                self.btn_live.setText("📡  Élő mód indítása")
                self.btn_live.setObjectName("live_btn")
                self.btn_live.setStyle(self.btn_live.style())
                self.live_status.setText("🔴  Élő mód: kikapcsolva")
                return

            if not self.ensure_invest_amount():
                self.output.append("Élő mód nem indult: nincs befektetési összeg.\n")
                return

            self.run_analysis(prompt_amount=False)
            self.live_timer.start(self.live_interval_sec * 1000)
            self.btn_live.setText("⏹  Élő mód leállítása")
            self.btn_live.setObjectName("live_btn_active")
            self.btn_live.setStyle(self.btn_live.style())
            self.live_status.setText(f"🟢  Élő mód: fut ({self.live_interval_sec}s)")

        def run_live_tick(self):
            self.run_analysis(prompt_amount=False)

        def selected_asset_items(self):
            names = [i.text() for i in self.list_widget.selectedItems()]
            if names:
                return [(n, ASSETS[n]) for n in names if n in ASSETS]
            return list(ASSETS.items())

        def run_analysis(self, prompt_amount=True):
            if self.auto_clear_analysis:
                self.output.clear()

            manual_usd = self.currency_combo.currentIndex() == 1
            rate, currency, rate_warning = self.resolve_rate_currency()
            if not manual_usd and rate_warning:
                self.output.append(
                    f"Figyelem: árfolyam hiba, USD módra váltva. ({rate_warning})\n"
                )

            if prompt_amount:
                amount, ok = QInputDialog.getDouble(
                    self,
                    "Befektetés",
                    f"Mennyit szeretnél ma befektetni? ({currency})",
                    self.invest_amount if self.invest_amount is not None else 100_000.0,
                    0.0,
                    1e15,
                    0,
                )
                if not ok:
                    self.output.append("Elemzés megszakítva (nincs megadott összeg).\n")
                    return
                self.invest_amount = amount

            if self.invest_amount is None:
                self.output.append("Nincs befektetési összeg beállítva.\n")
                return

            has_huf = rate_warning is None and currency == "HUF"
            fx_ctx = get_usdhuf_vs_ma20()
            now_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
            self.output.append(f"Frissítve: {now_text} | Deviza: {currency}\n")
            self.output.append("=" * 64 + "\n")
            self.stats_update.setText(f"Utolso frissites: {now_text}")

            results = []
            csv_rows = []
            db_batch = []

            for name, symbol in self.selected_asset_items():
                try:
                    result = analyze_asset(name, symbol, rate, currency)
                    result["investment"] = evaluate_today_investment(
                        self.invest_amount,
                        currency,
                        has_huf,
                        fx_ctx,
                        result,
                    )
                    results.append(result)
                    for msg in fire_custom_rules_if_needed(
                        self.custom_rules, result, self._rule_cooldown
                    ):
                        self.log_alert(msg)
                        self.trigger_alert_channels(msg)
                    self.output.append(format_result(result, currency=currency) + "\n")
                    if self.ai_commentary_enabled and self.ai_api_key:
                        ai_text, ai_err = get_ai_commentary(
                            result=result,
                            currency=currency,
                            api_key=self.ai_api_key,
                            model=self.ai_model,
                        )
                        if ai_text:
                            self.output.append("AI magyarazat:\n" + ai_text + "\n")
                        elif ai_err:
                            self.output.append(f"AI magyarazat hiba: {ai_err}\n")
                    csv_rows.append(
                        {
                            "timestamp": now_text,
                            "asset": name,
                            "currency": currency,
                            "current": f"{float(result['current']):.6f}",
                            "future": f"{float(result['future']):.6f}",
                            "decision": str(result["decision"]),
                            "next_up_prob": f"{float(result['next_up_prob']):.6f}",
                            "model_accuracy": f"{float(result['accuracy']):.6f}",
                            "confidence": f"{float(result['recommendation']['confidence']):.6f}",
                            "invest_amount": f"{float(self.invest_amount):.6f}",
                            "deploy_amount": f"{float(result['investment']['deploy_amount']):.6f}",
                            "deploy_frac": f"{float(result['investment']['deploy_frac']):.6f}",
                        }
                    )
                    met = result.get("metrics") or {}
                    db_batch.append(
                        (
                            now_text,
                            name,
                            currency,
                            float(result["current"]),
                            float(result["future"]),
                            str(result["decision"]),
                            float(result["rsi"]),
                            float(result["next_up_prob"]),
                            float(result["accuracy"]),
                            met.get("macd_hist"),
                            met.get("realized_vol_annual_pct"),
                            met.get("max_drawdown_pct"),
                        )
                    )

                    current = float(result["current"])
                    prev = self.last_prices_live.get(name)
                    if prev and prev != 0:
                        change_pct = ((current / prev) - 1.0) * 100.0
                        if abs(change_pct) >= self.alert_threshold_pct and self.live_timer.isActive():
                            direction = "emelkedes" if change_pct > 0 else "eses"
                            msg = (
                                f"{name}: {direction} {change_pct:+.2f}% | "
                                f"{prev:,.2f} -> {current:,.2f} {currency}"
                            )
                            self.log_alert(msg)
                            self.trigger_alert_channels(msg)
                    self.last_prices_live[name] = current
                except (requests.RequestException, ValueError, KeyError) as e:
                    self.output.append(f"{name}: hiba — {e}\n\n")
            if results:
                self._last_results = results
                self.update_decision_stats(results)
                self.update_portfolio_tab(results, currency)
                if self.live_timer.isActive() and self.csv_autosave_enabled:
                    try:
                        append_live_csv(self.csv_path, csv_rows)
                    except Exception as e:
                        self.log_alert(f"CSV mentesi hiba: {e}")
                try:
                    db_insert_rows(db_batch)
                except Exception as e:
                    self.log_alert(f"SQLite mentési hiba: {e}")
            self.refresh_price_chart()


def prompt_invest_amount(currency):
    if not sys.stdin.isatty():
        return None
    try:
        raw = input(f"Befektetendő összeg ({currency}): ").strip().replace(" ", "")
        raw = raw.replace(",", ".")
        return float(raw)
    except ValueError:
        return None


def run_cli(selected_assets, invest_amount=None):
    rate, currency, rate_warning = get_effective_rate()
    if rate_warning:
        print(f"Figyelem: árfolyam hiba, USD módra váltva. ({rate_warning})")
        print("-" * 40)

    amount = invest_amount
    if amount is None:
        amount = prompt_invest_amount(currency)
    if amount is None:
        print("Nincs befektetési összeg. Add meg: --osszeg 500000")
        return 1

    has_huf = rate_warning is None and currency == "HUF"
    fx_ctx = get_usdhuf_vs_ma20()

    had_error = False
    for name, symbol in selected_assets:
        try:
            result = analyze_asset(name, symbol, rate, currency)
            result["investment"] = evaluate_today_investment(
                amount,
                currency,
                has_huf,
                fx_ctx,
                result,
            )
            print(format_result(result, currency=currency))
            print("-" * 40)
        except (requests.RequestException, ValueError, KeyError) as e:
            had_error = True
            print(f"{name}: hiba — {e}")
            print("-" * 40)
    return 1 if had_error else 0


def parse_args():
    parser = argparse.ArgumentParser(description="AI alapú eszközelemző (GUI + CLI).")
    parser.add_argument("--cli", action="store_true", help="Futtatás terminál módban.")
    parser.add_argument(
        "--osszeg",
        type=float,
        default=None,
        help="Befektetendő összeg (HUF vagy USD, az aktuális megjelenítés szerint).",
    )
    parser.add_argument(
        "--asset",
        action="append",
        choices=list(ASSETS.keys()),
        help="Elemzendő eszköz neve. Többször is megadható.",
    )
    parser.add_argument("--all", action="store_true", help="Minden eszköz elemzése.")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Folyamatos árfigyelés és értesítés árfolyamváltozásra.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Figyelés lekérdezési időköze másodpercben (alap: 60).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="Értesítési küszöb százalékban, pl. 1.5 (alap: 1.0).",
    )
    return parser.parse_args()


def resolve_selected_assets(args):
    if args.all:
        return list(ASSETS.items())
    if args.asset:
        return [(name, ASSETS[name]) for name in args.asset]
    return list(ASSETS.items())


def main():
    configure_cross_platform_stdio()
    args = parse_args()
    selected_assets = resolve_selected_assets(args)

    if args.cli:
        if args.watch:
            sys.exit(
                monitor_price_changes(
                    selected_assets,
                    interval_sec=args.interval,
                    threshold_pct=max(0.01, abs(args.threshold)),
                )
            )
        sys.exit(run_cli(selected_assets, invest_amount=args.osszeg))

    if not QT_AVAILABLE:
        print(
            f"GUI nem indítható (PySide6 hiányzik/hibás: {QT_IMPORT_ERROR}). "
            "Használd: --cli"
        )
        sys.exit(1)

    if sys.platform == "win32":
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
