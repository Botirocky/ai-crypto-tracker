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
import colorsys
import math
import random
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
    from PySide6.QtCore import (
        QTimer, QDateTime, Qt, QTime,
        QPropertyAnimation, QEasingCurve, QPoint, QRect,
        QVariantAnimation,
    )
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
        QGroupBox,
        QScrollArea,
        QFrame,
        QProgressBar,
        QSplitter,
        QGraphicsDropShadowEffect,
        QGraphicsOpacityEffect,
        QSizePolicy,
    )
    from PySide6.QtGui import (
        QShortcut, QKeySequence,
        QBrush, QColor, QPainter, QPen,
        QLinearGradient, QRadialGradient,
        QFont,
    )
    from PySide6.QtCharts import QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis
    QT_AVAILABLE = True
    QT_IMPORT_ERROR = None

    # ── Animated widgets ─────────────────────────────────────────────────────

    class AnimatedButton(QPushButton):
        """QPushButton with hover-glow + press-bounce via shadow animation."""
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._shadow = QGraphicsDropShadowEffect(self)
            self._shadow.setBlurRadius(0)
            self._shadow.setColor(QColor(99, 102, 241, 200))
            self._shadow.setOffset(0, 0)
            self.setGraphicsEffect(self._shadow)
            self._anim = QPropertyAnimation(self._shadow, b"blurRadius")
            self._anim.setDuration(180)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _glow_to(self, val):
            self._anim.stop()
            self._anim.setStartValue(int(self._shadow.blurRadius()))
            self._anim.setEndValue(val)
            self._anim.start()

        def set_glow_color(self, r, g, b):
            self._shadow.setColor(QColor(r, g, b, 200))

        def enterEvent(self, e):
            self._glow_to(20)
            super().enterEvent(e)

        def leaveEvent(self, e):
            self._glow_to(0)
            super().leaveEvent(e)

        def mousePressEvent(self, e):
            self._shadow.setBlurRadius(30)
            super().mousePressEvent(e)

        def mouseReleaseEvent(self, e):
            self._glow_to(20)
            super().mouseReleaseEvent(e)


    class RGBTitleLabel(QLabel):
        """QLabel whose text is painted with a live-shifting rainbow gradient."""
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._stops = [
                (0.0, QColor(88, 166, 255)),
                (0.5, QColor(63, 185, 80)),
                (1.0, QColor(88, 166, 255)),
            ]
            self.setMinimumHeight(30)
            from PySide6.QtGui import QFont as _QFont
            f = _QFont("Segoe UI", 13)
            f.setBold(True)
            self.setFont(f)

        def set_stops(self, stops):
            self._stops = stops
            self.update()

        def paintEvent(self, _event):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            grad = QLinearGradient(0, 0, max(self.width(), 1), 0)
            for pos, col in self._stops:
                grad.setColorAt(pos, col)
            p.setPen(QPen(QBrush(grad), 0))
            p.setFont(self.font())
            p.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self.text(),
            )
            p.end()


    class RGBBorderBar(QFrame):
        """A thin horizontal bar that shows a shifting RGB gradient – top accent."""
        def __init__(self, h=4, parent=None):
            super().__init__(parent)
            self.setFixedHeight(h)
            self._stops = [
                (0.0, QColor(88, 166, 255)),
                (0.5, QColor(63, 185, 80)),
                (1.0, QColor(88, 166, 255)),
            ]

        def set_stops(self, stops):
            self._stops = stops
            self.update()

        def paintEvent(self, event):
            p = QPainter(self)
            grad = QLinearGradient(0, 0, self.width(), 0)
            for pos, col in self._stops:
                grad.setColorAt(pos, col)
            p.fillRect(self.rect(), QBrush(grad))
            p.end()

    # ── ParticleOverlay ──────────────────────────────────────────────────────

    class ParticleOverlay(QWidget):
        """Transparent floating-particle constellation layer behind the main UI."""

        N = 30
        LINK = 120

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self._dark = True
            self._pts = []
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(40)
            self._init_pts()

        def _init_pts(self):
            w = max(self.width(), 900)
            h = max(self.height(), 600)
            self._pts = [
                {
                    "x": random.random() * w,
                    "y": random.random() * h,
                    "vx": (random.random() - 0.5) * 0.45,
                    "vy": (random.random() - 0.5) * 0.45,
                    "r": 1.3 + random.random() * 1.7,
                }
                for _ in range(self.N)
            ]

        def set_dark(self, dark: bool):
            self._dark = dark

        def resizeEvent(self, e):
            super().resizeEvent(e)
            self._init_pts()

        def _tick(self):
            w, h = self.width(), self.height()
            if w < 1 or h < 1:
                return
            for p in self._pts:
                p["x"] = (p["x"] + p["vx"]) % w
                p["y"] = (p["y"] + p["vy"]) % h
            self.update()

        def paintEvent(self, _event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pts = self._pts
            if self._dark:
                dr, dg, db = 88, 166, 255
            else:
                dr, dg, db = 37, 99, 235

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(dr, dg, db, 70))
            for p in pts:
                r = int(p["r"])
                painter.drawEllipse(QPoint(int(p["x"]), int(p["y"])), r, r)

            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    dx = pts[i]["x"] - pts[j]["x"]
                    dy = pts[i]["y"] - pts[j]["y"]
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < self.LINK:
                        alpha = int(38 * (1 - d / self.LINK))
                        painter.setPen(QPen(QColor(dr, dg, db, alpha), 0.8))
                        painter.drawLine(
                            int(pts[i]["x"]), int(pts[i]["y"]),
                            int(pts[j]["x"]), int(pts[j]["y"]),
                        )
            painter.end()

    # ── PulsingDot ───────────────────────────────────────────────────────────

    class PulsingDot(QWidget):
        """Animated pulsing status indicator dot."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFixedSize(14, 14)
            self._active = False
            self._pulse = 0.0
            self._dir = 1
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(28)

        def set_active(self, active: bool):
            self._active = active
            self.update()

        def _tick(self):
            self._pulse += 0.055 * self._dir
            if self._pulse >= 1.0:
                self._pulse = 1.0
                self._dir = -1
            elif self._pulse <= 0.0:
                self._pulse = 0.0
                self._dir = 1
            self.update()

        def paintEvent(self, _event):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            cx = cy = 7
            if self._active:
                core = QColor(34, 197, 94)
            else:
                core = QColor(239, 68, 68)
            ring = QColor(core.red(), core.green(), core.blue(),
                          int(70 * self._pulse))
            ring_r = int(5 + self._pulse * 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ring)
            p.drawEllipse(QPoint(cx, cy), ring_r, ring_r)
            p.setBrush(core)
            p.drawEllipse(QPoint(cx, cy), 4, 4)
            p.end()

    # ── ShimmerBar ───────────────────────────────────────────────────────────

    class ShimmerBar(QWidget):
        """Animated gradient shimmer loading bar."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFixedHeight(4)
            self._pos = 0.0
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self.hide()

        def start(self):
            self._pos = 0.0
            self._timer.start(16)
            self.show()

        def stop(self):
            self._timer.stop()
            self.hide()

        def _tick(self):
            self._pos = (self._pos + 0.010) % 1.0
            self.update()

        def paintEvent(self, _event):
            p = QPainter(self)
            w = self.width()
            p.fillRect(self.rect(), QColor(30, 41, 59))
            grad = QLinearGradient(0, 0, w, 0)
            pos = self._pos
            w2 = 0.30
            grad.setColorAt(max(0.0, pos - w2), QColor(30, 41, 59, 0))
            grad.setColorAt(pos,                  QColor(99, 102, 241, 230))
            grad.setColorAt(min(1.0, pos + w2), QColor(30, 41, 59, 0))
            p.fillRect(self.rect(), QBrush(grad))
            p.end()

    # ── NumberTickLabel ──────────────────────────────────────────────────────

    class NumberTickLabel(QLabel):
        """QLabel that animates smoothly from one numeric value to another."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._anim = None
            self._fmt = "{:.0f}"
            self._cur_val = 0.0

        def tick_to(self, new_val: float, fmt: str = "{:.0f}", duration: int = 700):
            self._fmt = fmt
            if self._anim and self._anim.state() == QVariantAnimation.State.Running:
                self._anim.stop()
            anim = QVariantAnimation(self)
            anim.setStartValue(self._cur_val)
            anim.setEndValue(float(new_val))
            anim.setDuration(duration)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.valueChanged.connect(self._on_value)
            anim.start()
            self._anim = anim
            self._cur_val = float(new_val)

        def _on_value(self, v):
            self.setText(self._fmt.format(v))

except Exception as e:
    QT_AVAILABLE = False
    QT_IMPORT_ERROR = e


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
    # További ismert kriptók (Yahoo *-USD)
    "Bitcoin Cash": "BCH-USD",
    "Polygon": "MATIC-USD",
    "Toncoin": "TON11419-USD",
    "Sui": "SUI20947-USD",
    "Internet Computer": "ICP-USD",
    "Monero": "XMR-USD",
    "Ethereum Classic": "ETC-USD",
    "Maker": "MKR-USD",
    "Aave": "AAVE-USD",
    "Injective": "INJ-USD",
    "Tezos": "XTZ-USD",
    "Theta Network": "THETA-USD",
    "The Graph": "GRT-USD",
    "Kaspa": "KAS-USD",
    "Celestia": "TIA-USD",
    "THORChain": "RUNE-USD",
    "Quant": "QNT-USD",
    "MultiversX": "EGLD-USD",
    "Immutable": "IMX-USD",
    "Fetch.ai": "FET-USD",
    "Ethena": "ENA-USD",
    "Ondo": "ONDO-USD",
    "Sei": "SEI-USD",
    "Gala": "GALA-USD",
    "Wrapped Bitcoin": "WBTC-USD",
    "Tether (USDT)": "USDT-USD",
    # Memecoinok
    "Pepe": "PEPE-USD",
    "dogwifhat": "WIF-USD",
    "Bonk": "BONK-USD",
    "Floki": "FLOKI-USD",
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
    # További US blue chip részvények
    "Broadcom": "AVGO",
    "Eli Lilly": "LLY",
    "Johnson & Johnson": "JNJ",
    "Walmart": "WMT",
    "Mastercard": "MA",
    "ExxonMobil": "XOM",
    "Procter & Gamble": "PG",
    "Home Depot": "HD",
    "Oracle": "ORCL",
    "Adobe": "ADBE",
    "Salesforce": "CRM",
    "Pfizer": "PFE",
    "Boeing": "BA",
    "Starbucks": "SBUX",
    "PayPal": "PYPL",
    "Uber": "UBER",
    "Qualcomm": "QCOM",
    "Cisco": "CSCO",
    "Nike": "NKE",
    "Bank of America": "BAC",
    "Costco": "COST",
    "PepsiCo": "PEP",
    "Palantir": "PLTR",
    # Globális részvények (USD-ben jegyzett ADR / NYSE)
    "ASML": "ASML",
    "Novo Nordisk": "NVO",
    "TSMC": "TSM",
    "Alibaba": "BABA",
    "Toyota": "TM",
    "Ferrari": "RACE",
    "Shell": "SHEL",
    # Devizák (Forex, Yahoo XXXUSD=X – 1 egység az adott devizában USD-ben).
    # HUF nézetben a USD/HUF árfolyammal felszorozva a XXX/HUF keresztárfolyamot adja.
    "Euró (EUR)": "EURUSD=X",
    "Brit font (GBP)": "GBPUSD=X",
    "Japán jen (JPY)": "JPYUSD=X",
    "Svájci frank (CHF)": "CHFUSD=X",
    "Kanadai dollár (CAD)": "CADUSD=X",
    "Ausztrál dollár (AUD)": "AUDUSD=X",
    "Új-zélandi dollár (NZD)": "NZDUSD=X",
    "Kínai jüan (CNY)": "CNYUSD=X",
    "Hongkongi dollár (HKD)": "HKDUSD=X",
    "Szingapúri dollár (SGD)": "SGDUSD=X",
    "Svéd korona (SEK)": "SEKUSD=X",
    "Norvég korona (NOK)": "NOKUSD=X",
    "Lengyel złoty (PLN)": "PLNUSD=X",
    "Cseh korona (CZK)": "CZKUSD=X",
    "Román lej (RON)": "RONUSD=X",
    "Török líra (TRY)": "TRYUSD=X",
    "Mexikói peso (MXN)": "MXNUSD=X",
    "Dél-afrikai rand (ZAR)": "ZARUSD=X",
    "Indiai rúpia (INR)": "INRUSD=X",
    "Brazil real (BRL)": "BRLUSD=X",
}

ASSET_CATEGORIES = {
    "All": list(ASSETS.keys()),
    "Crypto": [
        "Bitcoin", "Ethereum", "BNB", "Solana", "XRP", "Cardano", "Dogecoin", "TRON",
        "Polkadot", "Avalanche", "Chainlink", "Litecoin", "Stellar", "Cosmos",
        "NEAR Protocol", "Uniswap", "Algorand", "Filecoin", "Hedera", "VeChain",
        "Shiba Inu", "Aptos", "Arbitrum", "Optimism",
        "Bitcoin Cash", "Polygon", "Toncoin", "Sui", "Internet Computer", "Monero",
        "Ethereum Classic", "Maker", "Aave", "Injective", "Tezos", "Theta Network",
        "The Graph", "Kaspa", "Celestia", "THORChain", "Quant", "MultiversX",
        "Immutable", "Fetch.ai", "Ethena", "Ondo", "Sei", "Gala", "Wrapped Bitcoin",
        "Tether (USDT)", "Pepe", "dogwifhat", "Bonk", "Floki",
    ],
    "NFT": [
        "ApeCoin (NFT)", "Decentraland (NFT/Metaverse)", "The Sandbox (NFT/Metaverse)",
        "Enjin Coin (NFT)", "Flow (NFT infrastruktúra)",
    ],
    "Commodity": ["Arany", "Kőolaj", "Földgáz"],
    "US Stock": [
        "Apple", "Microsoft", "NVIDIA", "Amazon", "Meta", "Alphabet (Google)", "Tesla",
        "AMD", "Netflix", "JPMorgan Chase", "Visa", "Coca-Cola", "SAP", "McDonald's",
        "Walt Disney", "Spotify", "Berkshire Hathaway", "Intel",
        "Broadcom", "Eli Lilly", "Johnson & Johnson", "Walmart", "Mastercard",
        "ExxonMobil", "Procter & Gamble", "Home Depot", "Oracle", "Adobe", "Salesforce",
        "Pfizer", "Boeing", "Starbucks", "PayPal", "Uber", "Qualcomm", "Cisco", "Nike",
        "Bank of America", "Costco", "PepsiCo", "Palantir",
    ],
    "World Stock": [
        "ASML", "Novo Nordisk", "TSMC", "Alibaba", "Toyota", "Ferrari", "Shell",
    ],
    "HU Stock": [
        "OTP Bank", "MOL", "Richter Gedeon", "Magyar Telekom", "4iG", "Opus Global",
        "Waberer's", "Masterplast", "AKKO Invest", "Appeninn",
    ],
    "Forex": [
        "Euró (EUR)", "Brit font (GBP)", "Japán jen (JPY)", "Svájci frank (CHF)",
        "Kanadai dollár (CAD)", "Ausztrál dollár (AUD)", "Új-zélandi dollár (NZD)",
        "Kínai jüan (CNY)", "Hongkongi dollár (HKD)", "Szingapúri dollár (SGD)",
        "Svéd korona (SEK)", "Norvég korona (NOK)", "Lengyel złoty (PLN)",
        "Cseh korona (CZK)", "Román lej (RON)", "Török líra (TRY)",
        "Mexikói peso (MXN)", "Dél-afrikai rand (ZAR)", "Indiai rúpia (INR)",
        "Brazil real (BRL)",
    ],
}

FX_URL = "https://api.exchangerate-api.com/v4/latest/USD"
# Megjelenítési valuták a HUF-auto és a "Mindig USD" opción felül.
# (Az exchangerate-api mind támogatja; kód → szimbólum a chip/label-hez.)
EXTRA_DISPLAY_CURRENCIES = [
    ("EUR", "€"),
    ("GBP", "£"),
    ("CHF", "CHF"),
    ("JPY", "¥"),
    ("PLN", "zł"),
    ("CZK", "Kč"),
]
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL_DEFAULT = "gpt-4o-mini"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_MODEL_DEFAULT = "claude-sonnet-4-6"
# NVIDIA NIM (build.nvidia.com) – OpenAI-kompatibilis chat completions végpont
NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL_DEFAULT = "meta/llama-3.3-70b-instruct"
REQUEST_TIMEOUT = 15
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AssetTracker/1.0)",
}

APP_STATE_DIR = Path.home() / ".config" / "ai-cripto-tracker"
FAVORITES_PATH = APP_STATE_DIR / "favorites.json"
CUSTOM_ALERTS_PATH = APP_STATE_DIR / "custom_alerts.json"
TELEGRAM_CONFIG_PATH = APP_STATE_DIR / "telegram_config.json"
DISCORD_CONFIG_PATH = APP_STATE_DIR / "discord_config.json"
APP_CONFIG_PATH = APP_STATE_DIR / "app_config.json"
HOLDINGS_PATH  = APP_STATE_DIR / "holdings.json"
SESSION_STATE_PATH = APP_STATE_DIR / "session.json"

_current_lang = "hu"  # module-level so format_result can use it

TRANSLATIONS = {
    "hu": {
        "window_title": "AI Eszközelemző Pro",
        "title_label": "🤖 AI + Indikátor Elemző Pro",
        "search_placeholder": "Keresés eszköz névre…",
        "only_favorites": "Csak kedvencek",
        "fav_toggle": "Kedvenc ☆ váltás",
        "display_label": "Megjelenítés:",
        "currency_auto": "Auto (HUF ha elérhető)",
        "currency_usd": "Mindig USD",
        "selected": "Kiválasztva: {n}",
        "signals": "Jelzések: Vétel {b} | Eladás {s} | Várj {w}",
        "last_update_init": "Utolsó frissítés: -",
        "select_all": "Összes kijelölése",
        "clear_output": "Kimenet törlése",
        "set_amount": "Összeg beállítása",
        "tab_analysis": "Elemzés",
        "tab_chart": "📈 Árfolyam diagram",
        "tab_alerts": "Értesítések",
        "tab_portfolio": "Portfolio",
        "tab_correlation": "Korreláció",
        "tab_history": "Előzmények",
        "tab_news": "Hírek",
        "tab_settings": "Beállítások",
        "copy_output": "Kimenet vágólapra",
        "analysis_placeholder": "Az elemzés eredménye itt fog megjelenni...",
        "btn_run": "▶  Elemzés",
        "btn_live_start": "📡  Élő mód indítása",
        "btn_live_stop": "⏹  Élő mód leállítása",
        "btn_interval": "⏱  Időköz: {n}s",
        "live_off": "Élő mód: kikapcsolva",
        "live_on": "Élő mód: fut ({n}s)",
        "auto_clear": "Elemzés törlése minden frissítés előtt",
        "sound_alerts": "Hangriasztás engedélyezve",
        "csv_autosave": "CSV automatikus mentés élőben",
        "csv_btn": "CSV fájl: {name}",
        "alert_threshold_btn": "Riasztási küszöb: {v:.2f}%",
        "telegram_config": "⚙️  Telegram beállítás (token + chat ID)",
        "telegram_test": "📨  Telegram tesztüzenet",
        "telegram_report": "📊  Riport küldése Telegramra",
        "telegram_off": "📵  Telegram: kikapcsolva",
        "telegram_active": "🟢  Telegram: aktív (chat: {id})",
        "telegram_partial": "🟡  Telegram: részben beállítva",
        "discord_config": "⚙️  Discord beállítás (webhook URL)",
        "discord_test": "📨  Discord tesztüzenet",
        "discord_report": "📊  Riport küldése Discordra",
        "discord_off": "📵  Discord: kikapcsolva",
        "discord_active": "🟢  Discord: aktív",
        "ai_checkbox": "Felhő AI magyarázat engedélyezve",
        "ai_config_btn": "AI beállítás (API kulcs + modell)",
        "ai_off": "AI: kikapcsolva",
        "ai_active": "AI: aktív ({provider} / {model})",
        "ai_key_set": "AI: kulcs beállítva ({provider} / {model})",
        "export_html": "HTML riport mentése…",
        "alert_rules": "Egyedi ár/RSI szabályok (JSON)…",
        "sched_label": "Napi ütemezett elemzés:",
        "lang_label": "Nyelv:",
        "theme_label": "Téma:",
        "theme_dark": "Sötét",
        "theme_light": "Világos",
        "compare_chart": "2 eszköz összehasonlítás (index 100 = indulás)",
        "bb_chart": "Bollinger sávok",
        "pattern_detect": "Alakzatfelismerés (M / W / V / ∧)",
        "chart_placeholder": "Válassz eszközt; az első kijelölt sor árfolyama jelenik meg.",
        "load_news_btn": "Yahoo hírcsatorna (első kijelölt)",
        "history_filter_placeholder": "Szűrés eszköz névre…",
        "history_load_btn": "Előzmények betöltése (SQLite)",
        "history_headers": ["Idő", "Eszköz", "Dev", "Most", "Célár", "Döntés", "RSI", "AI fel %", "Pontosság"],
        "corr_refresh_btn": "Korreláció frissítése (kijelölt eszközök)",
        "corr_placeholder": "Log-hozam korrelációs mátrix…",
        "alerts_placeholder": "Élő riasztások és események...",
        "clear_alerts_btn": "Értesítési napló törlése",
        "portfolio_placeholder": "Portfolio összegzés itt jelenik meg...",
        "chart_ranges": ["1 nap (élő)", "5 nap", "1 hó", "3 hó"],
        # format_result labels
        "fr_daily_change": "Napi változás",
        "fr_session_open": "Mai nyitás",
        "fr_prev_close": "Előző záró",
        "fr_now": "Most",
        "fr_ai_target": "AI célár (1 óra)",
        "fr_ai_prob": "AI esély fel",
        "fr_ai_acc": "AI validáció pontosság",
        "fr_rsi": "RSI",
        "fr_ma": "MA",
        "fr_indicators": "Indikátorok / kockázat (90 napos óras sáv)",
        "fr_macd": "MACD",
        "fr_bollinger": "Bollinger (20, 2σ)",
        "fr_volume": "Forgalom",
        "fr_vol_ratio": "arány 20-as átlaghoz",
        "fr_realized_vol": "Realizált volatilitás (évesített, kb)",
        "fr_max_dd": "Max. visszaesés (idősoron)",
        "fr_top_features": "Top AI jellemzők (fontosság)",
        "fr_decision": "Döntés",
        "fr_recommendation": "Ajánlás",
        "fr_direction": "Irány",
        "fr_confidence": "Bizalom",
        "fr_entry": "Belépő",
        "fr_stop": "Stop-loss",
        "fr_tp": "Take-profit",
        "fr_reason": "Indok",
        "fr_investment": "Befektetés (megadott összeg)",
        "fr_capital": "Tőke",
        "fr_verdict": "Ma érdemes-e nagyobb tét",
        "fr_fx_note": "Árfolyam (USD/HUF)",
        "fr_suggested_bet": "Javasolt tét ma",
        "fr_of_amount": "a megadott összegből",
        "decision_buy": "VÉTEL 📈",
        "decision_sell": "ELADÁS ⚠️",
        "decision_wait": "VÁRJ ⏳",
        "rec_buy": "VÉTEL",
        "rec_sell": "ELADÁS",
        "rec_wait": "KIVÁRÁS",
        "rsi_overbought": "RSI túlvett",
        "rsi_oversold": "RSI túladott",
        "rsi_neutral": "RSI semleges",
        "price_above_ma": "Ár MA felett",
        "price_below_ma": "Ár MA alatt",
        "side_long": "LONG",
        "side_short": "SHORT",
        "side_neutral": "NEUTRAL",
        "quick_scanner_btn": "⚡ Gyors scanner",
        "edit_holdings_btn": "✏️  Mennyiségek szerkesztése",
        "refresh_portfolio_btn": "🔄  Frissítés",
        "portfolio_headers": ["Eszköz", "Mennyiség", "Jelenlegi ár", "Érték", "Napi %", "Döntés"],
    },
    "en": {
        "window_title": "AI Asset Analyzer Pro",
        "title_label": "🤖 AI + Indicator Analyzer Pro",
        "search_placeholder": "Search by asset name…",
        "only_favorites": "Favorites only",
        "fav_toggle": "Favorite ☆ toggle",
        "display_label": "Display:",
        "currency_auto": "Auto (HUF if available)",
        "currency_usd": "Always USD",
        "selected": "Selected: {n}",
        "signals": "Signals: Buy {b} | Sell {s} | Wait {w}",
        "last_update_init": "Last update: -",
        "select_all": "Select all",
        "clear_output": "Clear output",
        "set_amount": "Set amount",
        "tab_analysis": "Analysis",
        "tab_chart": "📈 Price chart",
        "tab_alerts": "Alerts",
        "tab_portfolio": "Portfolio",
        "tab_correlation": "Correlation",
        "tab_history": "History",
        "tab_news": "News",
        "tab_settings": "Settings",
        "copy_output": "Copy output",
        "analysis_placeholder": "Analysis results will appear here...",
        "btn_run": "▶  Analyze",
        "btn_live_start": "📡  Start live mode",
        "btn_live_stop": "⏹  Stop live mode",
        "btn_interval": "⏱  Interval: {n}s",
        "live_off": "Live mode: off",
        "live_on": "Live mode: running ({n}s)",
        "auto_clear": "Clear analysis before each refresh",
        "sound_alerts": "Sound alerts enabled",
        "csv_autosave": "CSV auto-save in live mode",
        "csv_btn": "CSV file: {name}",
        "alert_threshold_btn": "Alert threshold: {v:.2f}%",
        "telegram_config": "⚙️  Telegram settings (token + chat ID)",
        "telegram_test": "📨  Telegram test message",
        "telegram_report": "📊  Send report to Telegram",
        "telegram_off": "📵  Telegram: disabled",
        "telegram_active": "🟢  Telegram: active (chat: {id})",
        "telegram_partial": "🟡  Telegram: partially configured",
        "discord_config": "⚙️  Discord settings (webhook URL)",
        "discord_test": "📨  Discord test message",
        "discord_report": "📊  Send report to Discord",
        "discord_off": "📵  Discord: disabled",
        "discord_active": "🟢  Discord: active",
        "ai_checkbox": "Cloud AI commentary enabled",
        "ai_config_btn": "AI settings (API key + model)",
        "ai_off": "AI: disabled",
        "ai_active": "AI: active ({provider} / {model})",
        "ai_key_set": "AI: key set ({provider} / {model})",
        "export_html": "Save HTML report…",
        "alert_rules": "Custom price/RSI rules (JSON)…",
        "sched_label": "Daily scheduled analysis:",
        "lang_label": "Language:",
        "theme_label": "Theme:",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "compare_chart": "2-asset comparison (index 100 = start)",
        "bb_chart": "Bollinger Bands",
        "pattern_detect": "Pattern detection (M / W / V / ∧)",
        "chart_placeholder": "Select an asset; the first selected row is shown.",
        "load_news_btn": "Yahoo news feed (first selected)",
        "history_filter_placeholder": "Filter by asset name…",
        "history_load_btn": "Load history (SQLite)",
        "history_headers": ["Time", "Asset", "Curr", "Price", "Target", "Decision", "RSI", "AI up %", "Accuracy"],
        "corr_refresh_btn": "Refresh correlation (selected assets)",
        "corr_placeholder": "Log-return correlation matrix…",
        "alerts_placeholder": "Live alerts and events...",
        "clear_alerts_btn": "Clear notification log",
        "portfolio_placeholder": "Portfolio summary appears here...",
        "chart_ranges": ["1 day (live)", "5 days", "1 month", "3 months"],
        "fr_daily_change": "Daily change",
        "fr_session_open": "Today's open",
        "fr_prev_close": "Previous close",
        "fr_now": "Now",
        "fr_ai_target": "AI target (1h)",
        "fr_ai_prob": "AI prob up",
        "fr_ai_acc": "AI model accuracy",
        "fr_rsi": "RSI",
        "fr_ma": "MA",
        "fr_indicators": "Indicators / risk (90-day hourly)",
        "fr_macd": "MACD",
        "fr_bollinger": "Bollinger (20, 2σ)",
        "fr_volume": "Volume",
        "fr_vol_ratio": "ratio to 20-period avg",
        "fr_realized_vol": "Realized volatility (annualized, approx)",
        "fr_max_dd": "Max drawdown (series)",
        "fr_top_features": "Top AI features (importance)",
        "fr_decision": "Decision",
        "fr_recommendation": "Recommendation",
        "fr_direction": "Direction",
        "fr_confidence": "Confidence",
        "fr_entry": "Entry",
        "fr_stop": "Stop-loss",
        "fr_tp": "Take-profit",
        "fr_reason": "Reasons",
        "fr_investment": "Investment (given amount)",
        "fr_capital": "Capital",
        "fr_verdict": "Worth investing today",
        "fr_fx_note": "FX rate (USD/HUF)",
        "fr_suggested_bet": "Suggested stake today",
        "fr_of_amount": "of the given amount",
        "decision_buy": "BUY 📈",
        "decision_sell": "SELL ⚠️",
        "decision_wait": "WAIT ⏳",
        "rec_buy": "BUY",
        "rec_sell": "SELL",
        "rec_wait": "HOLD",
        "rsi_overbought": "RSI overbought",
        "rsi_oversold": "RSI oversold",
        "rsi_neutral": "RSI neutral",
        "price_above_ma": "Price above MA",
        "price_below_ma": "Price below MA",
        "side_long": "LONG",
        "side_short": "SHORT",
        "side_neutral": "NEUTRAL",
        "quick_scanner_btn": "⚡ Quick scanner",
        "edit_holdings_btn": "✏️  Edit holdings",
        "refresh_portfolio_btn": "🔄  Refresh",
        "portfolio_headers": ["Asset", "Qty", "Current price", "Value", "Daily %", "Decision"],
    },
    "de": {
        "window_title": "KI-Asset-Analyzer Pro",
        "title_label": "🤖 KI + Indikator-Analyzer Pro",
        "search_placeholder": "Asset-Name suchen…",
        "only_favorites": "Nur Favoriten",
        "fav_toggle": "Favorit ☆ umschalten",
        "display_label": "Anzeige:",
        "currency_auto": "Auto (HUF wenn verfügbar)",
        "currency_usd": "Immer USD",
        "selected": "Ausgewählt: {n}",
        "signals": "Signale: Kauf {b} | Verkauf {s} | Warten {w}",
        "last_update_init": "Letzte Aktualisierung: -",
        "select_all": "Alle auswählen",
        "clear_output": "Ausgabe löschen",
        "set_amount": "Betrag festlegen",
        "tab_analysis": "Analyse",
        "tab_chart": "📈 Kurschart",
        "tab_alerts": "Benachrichtigungen",
        "tab_portfolio": "Portfolio",
        "tab_correlation": "Korrelation",
        "tab_history": "Verlauf",
        "tab_news": "Nachrichten",
        "tab_settings": "Einstellungen",
        "copy_output": "Ausgabe kopieren",
        "analysis_placeholder": "Analyseergebnisse erscheinen hier...",
        "btn_run": "▶  Analysieren",
        "btn_live_start": "📡  Live-Modus starten",
        "btn_live_stop": "⏹  Live-Modus stoppen",
        "btn_interval": "⏱  Intervall: {n}s",
        "live_off": "Live-Modus: aus",
        "live_on": "Live-Modus: läuft ({n}s)",
        "auto_clear": "Analyse vor jeder Aktualisierung löschen",
        "sound_alerts": "Ton-Benachrichtigungen aktiviert",
        "csv_autosave": "CSV-Autospeicherung im Live-Modus",
        "csv_btn": "CSV-Datei: {name}",
        "alert_threshold_btn": "Alarmschwelle: {v:.2f}%",
        "telegram_config": "⚙️  Telegram-Einstellungen (Token + Chat-ID)",
        "telegram_test": "📨  Telegram-Testnachricht",
        "telegram_report": "📊  Bericht an Telegram senden",
        "telegram_off": "📵  Telegram: deaktiviert",
        "telegram_active": "🟢  Telegram: aktiv (Chat: {id})",
        "telegram_partial": "🟡  Telegram: teilweise konfiguriert",
        "discord_config": "⚙️  Discord-Einstellungen (Webhook-URL)",
        "discord_test": "📨  Discord-Testnachricht",
        "discord_report": "📊  Bericht an Discord senden",
        "discord_off": "📵  Discord: deaktiviert",
        "discord_active": "🟢  Discord: aktiv",
        "ai_checkbox": "Cloud-KI-Kommentar aktiviert",
        "ai_config_btn": "KI-Einstellungen (API-Schlüssel + Modell)",
        "ai_off": "KI: deaktiviert",
        "ai_active": "KI: aktiv ({provider} / {model})",
        "ai_key_set": "KI: Schlüssel gesetzt ({provider} / {model})",
        "export_html": "HTML-Bericht speichern…",
        "alert_rules": "Benutzerdefinierte Preis/RSI-Regeln (JSON)…",
        "sched_label": "Tägl. geplante Analyse:",
        "lang_label": "Sprache:",
        "theme_label": "Design:",
        "theme_dark": "Dunkel",
        "theme_light": "Hell",
        "compare_chart": "2-Asset-Vergleich (Index 100 = Start)",
        "bb_chart": "Bollinger-Bänder",
        "pattern_detect": "Mustererkennung (M / W / V / ∧)",
        "chart_placeholder": "Asset auswählen; erste markierte Zeile wird angezeigt.",
        "load_news_btn": "Yahoo-Newsfeed (erste Auswahl)",
        "history_filter_placeholder": "Nach Asset-Name filtern…",
        "history_load_btn": "Verlauf laden (SQLite)",
        "history_headers": ["Zeit", "Asset", "Währ.", "Kurs", "Ziel", "Entscheidung", "RSI", "KI aufwärts %", "Genauigkeit"],
        "corr_refresh_btn": "Korrelation aktualisieren (gewählte Assets)",
        "corr_placeholder": "Log-Rendite-Korrelationsmatrix…",
        "alerts_placeholder": "Live-Benachrichtigungen und Ereignisse...",
        "clear_alerts_btn": "Benachrichtigungsprotokoll löschen",
        "portfolio_placeholder": "Portfolio-Zusammenfassung erscheint hier...",
        "chart_ranges": ["1 Tag (live)", "5 Tage", "1 Monat", "3 Monate"],
        "fr_daily_change": "Tagesveränderung",
        "fr_session_open": "Heutiges Eröffnung",
        "fr_prev_close": "Vorheriger Schluss",
        "fr_now": "Aktuell",
        "fr_ai_target": "KI-Ziel (1 Std.)",
        "fr_ai_prob": "KI-Wahrsch. aufwärts",
        "fr_ai_acc": "KI-Modell-Genauigkeit",
        "fr_rsi": "RSI",
        "fr_ma": "MA",
        "fr_indicators": "Indikatoren / Risiko (90-Tage stündlich)",
        "fr_macd": "MACD",
        "fr_bollinger": "Bollinger (20, 2σ)",
        "fr_volume": "Volumen",
        "fr_vol_ratio": "Verhältnis zum 20er-Durchschnitt",
        "fr_realized_vol": "Realisierte Volatilität (annualisiert, ca.)",
        "fr_max_dd": "Max. Drawdown (Zeitreihe)",
        "fr_top_features": "Top-KI-Merkmale (Wichtigkeit)",
        "fr_decision": "Entscheidung",
        "fr_recommendation": "Empfehlung",
        "fr_direction": "Richtung",
        "fr_confidence": "Konfidenz",
        "fr_entry": "Einstieg",
        "fr_stop": "Stop-Loss",
        "fr_tp": "Take-Profit",
        "fr_reason": "Begründung",
        "fr_investment": "Investition (angegebener Betrag)",
        "fr_capital": "Kapital",
        "fr_verdict": "Heute investieren?",
        "fr_fx_note": "Wechselkurs (USD/HUF)",
        "fr_suggested_bet": "Empfohlener Einsatz heute",
        "fr_of_amount": "des angegebenen Betrags",
        "decision_buy": "KAUF 📈",
        "decision_sell": "VERKAUF ⚠️",
        "decision_wait": "WARTEN ⏳",
        "rec_buy": "KAUF",
        "rec_sell": "VERKAUF",
        "rec_wait": "HALTEN",
        "rsi_overbought": "RSI überkauft",
        "rsi_oversold": "RSI überverkauft",
        "rsi_neutral": "RSI neutral",
        "price_above_ma": "Kurs über MA",
        "price_below_ma": "Kurs unter MA",
        "side_long": "LONG",
        "side_short": "SHORT",
        "side_neutral": "NEUTRAL",
        "quick_scanner_btn": "⚡ Schnellscanner",
        "edit_holdings_btn": "✏️  Bestände bearbeiten",
        "refresh_portfolio_btn": "🔄  Aktualisieren",
        "portfolio_headers": ["Asset", "Menge", "Aktueller Kurs", "Wert", "Tägl. %", "Entscheidung"],
    },
}


def _tr(key, lang=None, **kwargs):
    l = lang or _current_lang
    val = TRANSLATIONS.get(l, TRANSLATIONS["hu"]).get(key) or TRANSLATIONS["hu"].get(key, key)
    if kwargs:
        try:
            return val.format(**kwargs)
        except (KeyError, ValueError):
            return val
    return val


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
# Legutóbb letöltött USD-alapú árfolyamok (USD→X). A BÉT (.BD, HUF-alapú)
# instrumentumok tetszőleges megjelenítési valutára váltásához kell a HUF-kulcs.
_LAST_FX_RATES = {}


def get_rate(currency="HUF", timeout=REQUEST_TIMEOUT, strict=True):
    """1 USD = ? a kért megjelenítési valutában (USD→currency)."""
    cur = (currency or "HUF").strip().upper()
    errors = []

    try:
        r = http_get(FX_URL, timeout=timeout)
        r.raise_for_status()
        rates = r.json()["rates"]
        _LAST_FX_RATES.clear()
        _LAST_FX_RATES.update(rates)
        return float(rates[cur])
    except (requests.RequestException, KeyError, ValueError, TypeError) as e:
        errors.append(f"exchangerate-api: {e}")

    # Fallback: Yahoo FX árfolyam (csak a HUF-ra van dedikált tartalék forrás)
    if cur == "HUF":
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
            val = float(closes[-1])
            _LAST_FX_RATES["HUF"] = val
            return val
        except (requests.RequestException, KeyError, ValueError, TypeError) as e:
            errors.append(f"yahoo-fx: {e}")

    error = RuntimeError(f"USD→{cur} árfolyam nem elérhető | " + " | ".join(errors))
    if strict:
        raise error
    return 1.0


def get_effective_rate(currency="HUF"):
    cur = (currency or "HUF").strip().upper()
    try:
        return get_rate(cur, strict=True), cur, None
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
    if not is_bet:
        # USD-alapú instrumentum (kripto, US/world részvény, forex): USD→cur szorzó.
        # USD megjelenítésnél r==1.0, HUF-nál r==USD/HUF — visszaadja a régi viselkedést.
        return r
    # BÉT (.BD) instrumentum HUF-ban jegyezve → HUF-ból váltunk a megjelenítési valutára.
    if cur == "HUF":
        return 1.0
    huf = _LAST_FX_RATES.get("HUF")
    try:
        huf = float(huf)
    except (TypeError, ValueError):
        huf = None
    if not huf or huf <= 0:
        # Nincs gyorsítótárazott HUF-árfolyam: USD esetén a régi 1/r tartalék.
        return 1.0 / r if cur == "USD" else 1.0
    # HUF→cur = (USD→cur) / (USD→HUF)
    return r / huf


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


def load_discord_config():
    ensure_app_state_dir()
    if not DISCORD_CONFIG_PATH.is_file():
        return ""
    try:
        data = json.loads(DISCORD_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("webhook_url", "")
    except (OSError, ValueError, TypeError):
        pass
    return ""


def save_discord_config(webhook_url):
    ensure_app_state_dir()
    DISCORD_CONFIG_PATH.write_text(
        json.dumps({"webhook_url": webhook_url}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_app_config():
    ensure_app_state_dir()
    if not APP_CONFIG_PATH.is_file():
        return "hu", "dark"
    try:
        data = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            lang = data.get("lang", "hu")
            if lang not in TRANSLATIONS:
                lang = "hu"
            theme = data.get("theme", "dark")
            if theme not in ("dark", "light"):
                theme = "dark"
            return lang, theme
    except (OSError, ValueError, TypeError):
        pass
    return "hu", "dark"


def save_app_config(lang, theme):
    ensure_app_state_dir()
    APP_CONFIG_PATH.write_text(
        json.dumps({"lang": lang, "theme": theme}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_session_state():
    ensure_app_state_dir()
    if not SESSION_STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(SESSION_STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {}


def save_session_state(data: dict):
    ensure_app_state_dir()
    SESSION_STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_holdings():
    ensure_app_state_dir()
    if not HOLDINGS_PATH.is_file():
        return {}
    try:
        data = json.loads(HOLDINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {k: float(v) for k, v in data.items() if k in ASSETS and float(v) > 0}
    except (OSError, ValueError, TypeError):
        pass
    return {}


def save_holdings(holdings):
    ensure_app_state_dir()
    HOLDINGS_PATH.write_text(
        json.dumps({k: v for k, v in holdings.items() if v > 0},
                   ensure_ascii=False, indent=2),
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


def rolling_bollinger(closes, window=20, n_std=2.0):
    """Gördülő Bollinger-sávok. Visszaad: (upper, mid, lower) np.array-ek,
    NaN-nal ahol még nincs elég adat — diagram overlay-hez."""
    arr = np.asarray(closes, dtype=float)
    n = arr.size
    upper = np.full(n, np.nan)
    mid = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    if n < window:
        return upper, mid, lower
    for i in range(window - 1, n):
        w = arr[i - window + 1:i + 1]
        mu = float(np.mean(w))
        sd = float(np.std(w))
        mid[i] = mu
        upper[i] = mu + n_std * sd
        lower[i] = mu - n_std * sd
    return upper, mid, lower


def rolling_rsi(closes, period=14):
    """Wilder-simítású RSI idősor (NaN ahol még nincs elég adat)."""
    arr = np.asarray(closes, dtype=float)
    n = arr.size
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    def _rsi(ag, al):
        if al == 0:
            return 100.0 if ag > 0 else 50.0
        rs = ag / al
        return 100.0 - 100.0 / (1.0 + rs)

    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi(avg_gain, avg_loss)
    return out


def rolling_macd(closes):
    """MACD vonal / jelvonal / histogram teljes idősora."""
    arr = np.asarray(closes, dtype=float)
    n = arr.size
    if n < 35:
        nan = np.full(n, np.nan)
        return nan, nan.copy(), nan.copy()
    ema12 = ema_np(arr, 12)
    ema26 = ema_np(arr, 26)
    line = ema12 - ema26
    signal = ema_np(line, 9)
    hist = line - signal
    return line, signal, hist


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
def build_features_and_labels(prices, volumes=None):
    """
    Features on each hour:
    - short / medium / long returns
    - short volatility
    - moving average ratios (SMA + EMA)
    - RSI normalized
    - MACD histogram
    - Bollinger Band position
    - volume ratio vs SMA (if available)
    - price momentum (acceleration)
    Label: next-hour direction (1=up, 0=down/flat)
    """
    if prices.size < 120:
        raise ValueError("Túl kevés adat a modellhez (min. 120 pont kell).")

    X, y = [], []
    returns = np.diff(prices) / prices[:-1]
    lookback = 48  # longer lookback for more context

    for i in range(lookback, prices.size - 1):
        ret_1 = returns[i - 1]
        ret_3 = (prices[i] / prices[i - 3]) - 1.0
        ret_12 = (prices[i] / prices[i - 12]) - 1.0
        ret_24 = (prices[i] / prices[i - 24]) - 1.0
        ret_48 = (prices[i] / prices[i - 48]) - 1.0
        vol_12 = float(np.std(returns[i - 12:i]))
        vol_24 = float(np.std(returns[i - 24:i]))

        ma_10 = float(np.mean(prices[i - 10:i]))
        ma_30 = float(np.mean(prices[i - 30:i]))
        ma_ratio_10 = (prices[i] / ma_10) - 1.0
        ma_ratio_30 = (prices[i] / ma_30) - 1.0

        ema_12 = float(ema_np(prices[: i + 1], 12)[-1])
        ema_26 = float(ema_np(prices[: i + 1], 26)[-1])
        ema_ratio_12 = (prices[i] / ema_12) - 1.0 if ema_12 != 0 else 0.0

        macd_line_val = ema_12 - ema_26
        prev_ema_12 = float(ema_np(prices[:i], 12)[-1]) if i >= 12 else ema_12
        prev_ema_26 = float(ema_np(prices[:i], 26)[-1]) if i >= 26 else ema_26
        prev_macd = prev_ema_12 - prev_ema_26
        macd_accel = macd_line_val - prev_macd

        bb_mid = ma_30
        bb_std = float(np.std(prices[i - 20:i])) if i >= 20 else 1e-8
        bb_upper = bb_mid + 2.0 * bb_std
        bb_lower = bb_mid - 2.0 * bb_std
        bb_width = bb_upper - bb_lower
        bb_pos = (prices[i] - bb_lower) / bb_width if bb_width > 0 else 0.5

        rsi = calculate_rsi(prices[: i + 1]) / 100.0

        momentum = ret_1 - (returns[i - 4] if i >= 4 else 0.0)

        vol_ratio = 1.0
        if volumes is not None and i < len(volumes):
            v_slice = volumes[max(0, i - 20):i]
            v_sma = float(np.mean(v_slice)) if v_slice.size > 0 else 1.0
            if v_sma > 0:
                vol_ratio = float(volumes[i]) / v_sma

        X.append(
            [
                ret_1,
                ret_3,
                ret_12,
                ret_24,
                ret_48,
                vol_12,
                vol_24,
                ma_ratio_10,
                ma_ratio_30,
                ema_ratio_12,
                macd_line_val,
                macd_accel,
                bb_pos,
                bb_width / (prices[i] + 1e-8),
                rsi,
                momentum,
                min(vol_ratio, 5.0),
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


FEATURE_NAMES = [
    "ret_1h", "ret_3h", "ret_12h", "ret_24h", "ret_48h",
    "vol_12h", "vol_24h",
    "ma_ratio_10", "ma_ratio_30", "ema_ratio_12",
    "macd_line", "macd_accel",
    "bb_pos", "bb_width_rel",
    "rsi",
    "momentum",
    "volume_ratio",
]


def predict(prices, volumes=None):
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import train_test_split

    X, y = build_features_and_labels(prices, volumes=volumes)
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

    rf = RandomForestClassifier(
        n_estimators=300,
        max_features="sqrt",
        min_samples_leaf=3,
        random_state=42,
    )
    rf.fit(X_train, y_train)

    gb = GradientBoostingClassifier(
        n_estimators=150,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        random_state=42,
    )
    gb.fit(X_train, y_train)

    rf_acc = float((rf.predict(X_test) == y_test).mean()) if y_test.size else 0.0
    gb_acc = float((gb.predict(X_test) == y_test).mean()) if y_test.size else 0.0
    accuracy = (rf_acc + gb_acc) / 2.0

    rf_prob = random_forest_up_probability(rf, X[-1])
    last_row = np.asarray(X[-1], dtype=float).reshape(1, -1)
    gb_classes = list(gb.classes_)
    gb_proba = gb.predict_proba(last_row)[0]
    gb_prob = float(gb_proba[gb_classes.index(1)]) if 1 in gb_classes else 0.5
    next_up_prob = (rf_prob + gb_prob) / 2.0

    importances = rf.feature_importances_
    feat_imp = sorted(
        zip(FEATURE_NAMES, importances.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    current = float(prices[-1])
    tail = prices[-49:]
    recent_returns = np.diff(tail) / tail[:-1]
    recent_abs_move = float(np.mean(np.abs(recent_returns)))
    drift = (2.0 * next_up_prob - 1.0) * recent_abs_move
    future = current * (1.0 + drift)

    return current, future, next_up_prob, accuracy, feat_imp


# ---- KOMBINÁLT DÖNTÉS ----
def smart_decision(prices, volumes=None):
    current, future, next_up_prob, accuracy, feat_imp = predict(prices, volumes=volumes)

    rsi = calculate_rsi(prices)
    ma = moving_average(prices)

    macd_line, macd_signal, macd_hist = macd_bundle(prices)
    bb_upper, bb_lower, bb_mid = bollinger_last(prices)

    weighted_buy = 0.0
    weighted_sell = 0.0

    # AI ensemble signal (weight 2.0)
    if next_up_prob > 0.55:
        weighted_buy += 2.0 * (next_up_prob - 0.5) * 2
    elif next_up_prob < 0.45:
        weighted_sell += 2.0 * (0.5 - next_up_prob) * 2

    # RSI signal (weight 1.5)
    if rsi > 75:
        weighted_sell += 1.5
    elif rsi > 70:
        weighted_sell += 1.0
    elif rsi < 25:
        weighted_buy += 1.5
    elif rsi < 30:
        weighted_buy += 1.0

    # MA signal (weight 1.0)
    if current > ma:
        weighted_buy += 1.0
    else:
        weighted_sell += 1.0

    # MACD signal (weight 1.5)
    if macd_hist is not None:
        if macd_hist > 0 and macd_line > macd_signal:
            weighted_buy += 1.5
        elif macd_hist < 0 and macd_line < macd_signal:
            weighted_sell += 1.5

    # Bollinger Band signal (weight 1.0)
    if bb_upper is not None and bb_lower is not None and bb_upper > bb_lower:
        if current > bb_upper:
            weighted_sell += 1.0
        elif current < bb_lower:
            weighted_buy += 1.0

    if weighted_sell >= 3.0 and weighted_sell > weighted_buy:
        decision = _tr("decision_sell")
    elif weighted_buy >= 3.0 and weighted_buy > weighted_sell:
        decision = _tr("decision_buy")
    else:
        decision = _tr("decision_wait")

    return decision, current, future, rsi, ma, next_up_prob, accuracy, feat_imp, weighted_buy, weighted_sell


def build_recommendation(current, future, next_up_prob, accuracy, rsi, ma):
    edge = next_up_prob - 0.5
    confidence = max(0.0, min(1.0, (abs(edge) * 2.0) * (0.6 + 0.4 * accuracy)))

    # Volatilitás alapú kockázati távolság (minimum 1.5%)
    base_risk = max(0.015, abs((future / current) - 1.0))
    stop_distance = base_risk * 0.8
    tp_distance = base_risk * 1.6

    if next_up_prob >= 0.58:
        side = _tr("side_long")
        action = _tr("rec_buy")
        entry = current
        stop = entry * (1.0 - stop_distance)
        take_profit = entry * (1.0 + tp_distance)
    elif next_up_prob <= 0.42:
        side = _tr("side_short")
        action = _tr("rec_sell")
        entry = current
        stop = entry * (1.0 + stop_distance)
        take_profit = entry * (1.0 - tp_distance)
    else:
        side = _tr("side_neutral")
        action = _tr("rec_wait")
        entry = current
        stop = current
        take_profit = current

    reasons = []
    reasons.append(f"AI: {next_up_prob * 100:.1f}%")
    reasons.append(f"Acc: {accuracy * 100:.1f}%")
    reasons.append(_tr("rsi_overbought") if rsi > 70 else _tr("rsi_oversold") if rsi < 30 else _tr("rsi_neutral"))
    reasons.append(_tr("price_above_ma") if current > ma else _tr("price_below_ma"))

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
    decision, current, future, rsi, ma, next_up_prob, accuracy, feat_imp, sig_buy, sig_sell = smart_decision(
        prices, volumes=volumes_raw
    )
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
    support, resistance = find_support_resistance(prices)
    ma_cross = detect_ma_cross(prices)
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
        "feat_imp": feat_imp,
        "recommendation": recommendation,
        "day_change_pct": regular_market_change_pct(meta),
        "session_open": session_open,
        "previous_close": previous_close,
        "metrics": metrics,
        "support": support,
        "resistance": resistance,
        "ma_cross": ma_cross,
        "sig_buy": sig_buy,
        "sig_sell": sig_sell,
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
    # Toleráljuk a beillesztési hibákat: whitespace és felesleges "bot" előtag.
    token = (bot_token or "").strip()
    if token.lower().startswith("bot"):
        token = token[3:]
    chat = str(chat_id or "").strip()
    if not token or not chat:
        return False, "Hiányzó Telegram token/chat_id"
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def _send(pm):
        payload = {"chat_id": chat, "text": message, "disable_web_page_preview": True}
        if pm:
            payload["parse_mode"] = pm
        r = http_post(url, timeout=timeout, data=payload)
        try:
            return r, r.json()
        except ValueError:
            return r, {}

    try:
        r, data = _send(parse_mode)
        # Ha a HTML formázás miatt 400-at kapunk, próbáljuk sima szövegként.
        if r.status_code == 400 and parse_mode:
            r2, data2 = _send(None)
            if data2.get("ok"):
                return True, None
            desc = data.get("description") or (r.text or "")[:200]
            return False, f"Telegram 400: {desc}"
        if r.status_code == 401:
            return False, "Telegram 401: érvénytelen bot token."
        if r.status_code == 404:
            return False, "Telegram 404: a bot nem található (hibás token)."
        if not data.get("ok"):
            desc = data.get("description") if isinstance(data, dict) else None
            return False, desc or f"HTTP {r.status_code}: {(r.text or '')[:200]}"
        return True, None
    except (requests.RequestException, ValueError, TypeError) as e:
        return False, str(e)


def _fmt_price(value):
    """Format a price with appropriate decimal places regardless of magnitude."""
    v = float(value)
    if v == 0:
        return "0"
    abs_v = abs(v)
    if abs_v >= 1000:
        return f"{v:,.0f}"
    if abs_v >= 1:
        return f"{v:,.2f}"
    if abs_v >= 0.01:
        return f"{v:.4f}"
    if abs_v >= 0.0001:
        return f"{v:.6f}"
    return f"{v:.8f}"


def format_telegram_result(result, currency="HUF"):
    """Format a single asset result as a rich Telegram HTML message."""
    decision = str(result.get("decision", ""))
    # Match buy/sell signals across all supported languages (HU/EN/DE)
    _dec_up = decision.upper()
    if any(kw in _dec_up for kw in ("VÉTEL", "VETEL", "BUY", "KAUF")):
        signal_emoji = "📈"
        signal_color = "✅"
    elif any(kw in _dec_up for kw in ("ELADÁS", "ELADAS", "SELL", "VERKAUF")):
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
    lines.append(f"💰 Ár: <b>{_fmt_price(result['current'])} {currency}</b>")
    lines.append(f"🎯 AI célár (1h): <b>{_fmt_price(result['future'])} {currency}</b>")
    lines.append(f"🤖 AI valószínűség fel: <b>{result['next_up_prob'] * 100:.1f}%</b>")
    lines.append(f"📐 RSI: <b>{result['rsi']:.1f}</b>")
    lines.append(f"{signal_color} Döntés: <b>{html.escape(decision)}</b>")
    lines.append(f"💼 Ajánlás: <b>{html.escape(str(rec.get('action', '-')))}</b> ({html.escape(str(rec.get('side', '-')))})")
    lines.append(f"🎲 Bizalom: <b>{rec.get('confidence', 0) * 100:.1f}%</b>")
    if rec.get("side") not in ("NEUTRAL", "NEUTRAL"):
        stop_val = rec.get("stop", 0)
        tp_val = rec.get("take_profit", 0)
        if stop_val and stop_val != rec.get("entry"):
            lines.append(f"🚫 Stop-loss: {_fmt_price(stop_val)} {currency}")
            lines.append(f"✨ Take-profit: {_fmt_price(tp_val)} {currency}")
    inv = result.get("investment")
    if inv:
        lines.append(
            f"💵 Javasolt tét: <b>{_fmt_price(inv['deploy_amount'])} {currency}</b> "
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


# ---- Discord (webhook) ----
DISCORD_USERNAME = "AI Eszközelemző Pro"
# Embed színek (decimális RGB)
DISCORD_COLOR_BUY = 0x23E87A
DISCORD_COLOR_SELL = 0xFF5D73
DISCORD_COLOR_WAIT = 0xFFCB45
DISCORD_COLOR_INFO = 0x5865F2  # Discord "blurple"


def _discord_signal_meta(decision):
    """Map a decision string (HU/EN/DE) to (emoji, embed color)."""
    dec_up = str(decision or "").upper()
    if any(kw in dec_up for kw in ("VÉTEL", "VETEL", "BUY", "KAUF")) or "📈" in dec_up:
        return "📈", DISCORD_COLOR_BUY
    if any(kw in dec_up for kw in ("ELADÁS", "ELADAS", "SELL", "VERKAUF")) or "⚠️" in dec_up:
        return "📉", DISCORD_COLOR_SELL
    return "⏳", DISCORD_COLOR_WAIT


def send_discord_message(webhook_url, content=None, embeds=None, timeout=REQUEST_TIMEOUT):
    """Send a message to a Discord channel via incoming webhook.

    Returns (ok: bool, error: str|None).
    """
    url = (webhook_url or "").strip()
    if not url:
        return False, "Hiányzó Discord webhook URL"
    if "/webhooks/" not in url or not url.lower().startswith("http"):
        return False, "Érvénytelen Discord webhook URL (https://discord.com/api/webhooks/…)"

    payload = {"username": DISCORD_USERNAME, "allowed_mentions": {"parse": []}}
    if content:
        payload["content"] = content[:2000]
    if embeds:
        payload["embeds"] = embeds[:10]  # Discord max. 10 embed / üzenet
    if "content" not in payload and "embeds" not in payload:
        return False, "Üres Discord üzenet"

    try:
        r = http_post(url, timeout=timeout, json=payload)
        if r.status_code in (200, 204):
            return True, None
        if r.status_code == 401 or r.status_code == 403:
            return False, "Discord 401/403: érvénytelen vagy visszavont webhook."
        if r.status_code == 404:
            return False, "Discord 404: a webhook nem található (törölve vagy hibás URL)."
        if r.status_code == 429:
            try:
                retry = r.json().get("retry_after", "?")
            except ValueError:
                retry = "?"
            return False, f"Discord 429: rate limit (várj {retry}s)."
        return False, f"HTTP {r.status_code}: {(r.text or '')[:200]}"
    except (requests.RequestException, ValueError, TypeError) as e:
        return False, str(e)


def format_discord_result_embed(result, currency="HUF"):
    """Format a single asset result as a rich Discord embed dict."""
    decision = str(result.get("decision", ""))
    emoji, color = _discord_signal_meta(decision)
    rec = result.get("recommendation", {})
    name = str(result.get("name", ""))
    symbol = str(result.get("symbol", ""))

    fields = []
    dcp = result.get("day_change_pct")
    if dcp is not None:
        arrow = "▲" if dcp >= 0 else "▼"
        fields.append({"name": "📊 Napi változás", "value": f"{arrow} {dcp:+.2f}%", "inline": True})
    fields.append({"name": "💰 Ár", "value": f"{_fmt_price(result['current'])} {currency}", "inline": True})
    fields.append({"name": "🎯 AI célár (1h)", "value": f"{_fmt_price(result['future'])} {currency}", "inline": True})
    fields.append({"name": "🤖 Valószínűség fel", "value": f"{result['next_up_prob'] * 100:.1f}%", "inline": True})
    fields.append({"name": "📐 RSI", "value": f"{result['rsi']:.1f}", "inline": True})
    fields.append({"name": "🎲 Bizalom", "value": f"{rec.get('confidence', 0) * 100:.1f}%", "inline": True})
    fields.append({
        "name": "💼 Ajánlás",
        "value": f"{rec.get('action', '-')} ({rec.get('side', '-')})",
        "inline": False,
    })
    if rec.get("side") not in ("NEUTRAL",):
        stop_val = rec.get("stop", 0)
        tp_val = rec.get("take_profit", 0)
        if stop_val and stop_val != rec.get("entry"):
            fields.append({"name": "🚫 Stop-loss", "value": f"{_fmt_price(stop_val)} {currency}", "inline": True})
            fields.append({"name": "✨ Take-profit", "value": f"{_fmt_price(tp_val)} {currency}", "inline": True})
    inv = result.get("investment")
    if inv:
        fields.append({
            "name": "💵 Javasolt tét",
            "value": f"{_fmt_price(inv['deploy_amount'])} {currency} ({inv['deploy_frac'] * 100:.0f}%)",
            "inline": False,
        })

    return {
        "title": f"{emoji} {name} ({symbol})",
        "description": f"**Döntés:** {decision}",
        "color": color,
        "fields": fields,
        "footer": {"text": "AI Eszközelemző Pro"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def format_discord_alert_embed(message, asset_name=""):
    """Format a price alert as a Discord embed dict."""
    title = f"⚠️ Riasztás – {asset_name}" if asset_name else "⚠️ Árfolyam riasztás"
    return {
        "title": title,
        "description": str(message)[:4096],
        "color": DISCORD_COLOR_WAIT,
        "footer": {"text": "AI Eszközelemző Pro"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


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


def _build_ai_prompt(result, currency):
    """Build a rich market analysis prompt from an asset result dict."""
    rec = result.get("recommendation", {})
    m = result.get("metrics") or {}
    feat_imp = result.get("feat_imp") or []

    lines = [
        "Adj rovid, 3-5 pontos magyar piaci osszefoglalot ezek alapjan.",
        "Ne adj befektetesi garanciat, legyen ovatos hangnem.",
        "",
        f"Eszkoz: {result.get('name')} ({result.get('symbol', '')})",
    ]
    if result.get("session_open") is not None:
        lines.append(f"Mai nyitas: {float(result['session_open']):.2f} {currency}")
    if result.get("previous_close") is not None:
        lines.append(f"Elozo zaro: {float(result['previous_close']):.2f} {currency}")
    dcp = result.get("day_change_pct")
    if dcp is not None:
        lines.append(f"Napi valtozas: {dcp:+.2f}%")
    lines += [
        f"Most: {result.get('current'):.2f} {currency}",
        f"AI celar (1 ora): {result.get('future'):.2f} {currency}",
        f"AI ensemble eselye (fel): {result.get('next_up_prob', 0.0) * 100:.1f}%",
        f"Ensemble modell pontossag: {result.get('accuracy', 0.0) * 100:.1f}%",
        f"RSI: {result.get('rsi', 0.0):.2f}",
        f"Mozgoatlag (20): {result.get('ma', 0.0):.2f}",
    ]
    if m.get("macd_hist") is not None:
        lines.append(
            f"MACD: vonal {m['macd_line']:.4f}, jel {m['macd_signal']:.4f}, "
            f"histogram {m['macd_hist']:.4f}"
        )
    if m.get("bb_mid") is not None:
        lines.append(
            f"Bollinger: felso {m['bb_upper']:.2f}, kozep {m['bb_mid']:.2f}, "
            f"also {m['bb_lower']:.2f}"
        )
    if m.get("realized_vol_annual_pct") is not None:
        lines.append(f"Realizalt volatilitas (evesitett): {m['realized_vol_annual_pct']:.1f}%")
    if feat_imp:
        top = ", ".join(f"{n}({v*100:.1f}%)" for n, v in feat_imp[:3])
        lines.append(f"Legfontosabb AI jellemzok: {top}")
    lines += [
        f"Dontes: {result.get('decision')}",
        f"Javasolt irany: {rec.get('action', 'ismeretlen')} ({rec.get('side', '')})",
        f"Bizalom: {rec.get('confidence', 0.0) * 100:.1f}%",
    ]
    if rec.get("side") != "NEUTRAL":
        lines.append(f"Stop-loss: {rec.get('stop', 0):.2f} {currency}")
        lines.append(f"Take-profit: {rec.get('take_profit', 0):.2f} {currency}")
    return "\n".join(lines)


def get_claude_commentary(result, currency, api_key, model=ANTHROPIC_MODEL_DEFAULT, timeout=25):
    """Get AI commentary using the Anthropic Claude API."""
    if not api_key:
        return None, "Nincs Anthropic API kulcs."
    prompt = _build_ai_prompt(result, currency)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 512,
        "system": (
            "Te egy konzervativ penzugyi elemzo asszisztens vagy. "
            "Rovid, strukturalt, magyar nyelvu osszefoglalokat adsz. "
            "Soha nem garantalsz hozamot, es mindig felhivod a figyelmet a kockázatokra."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        r = http_post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=timeout)
        data = r.json()
        if r.status_code >= 400:
            err = data.get("error") if isinstance(data, dict) else None
            if isinstance(err, dict):
                msg = err.get("message") or str(err)
            else:
                msg = str(err) if err else r.text or r.reason
            return None, f"Anthropic API ({r.status_code}): {msg}"
        content_blocks = data.get("content") or []
        text = " ".join(
            b.get("text", "") for b in content_blocks if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
        if not text:
            return None, "Ures Claude valasz."
        return text, None
    except (requests.RequestException, ValueError, TypeError) as e:
        return None, str(e)


def get_ai_commentary(result, currency, api_key, model=OPENAI_MODEL_DEFAULT, timeout=20,
                      claude_api_key=None, claude_model=ANTHROPIC_MODEL_DEFAULT):
    """Get AI commentary; tries Claude first if claude_api_key is provided, then OpenAI."""
    if claude_api_key:
        text, err = get_claude_commentary(result, currency, claude_api_key, model=claude_model, timeout=timeout)
        if text:
            return text, None
        # fallback to OpenAI if Claude fails
        if not api_key:
            return None, f"Claude hiba: {err}"

    if not api_key:
        return None, "Nincs AI API kulcs."
    prompt = _build_ai_prompt(result, currency)
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


def get_nvidia_commentary(result, currency, api_key, model=NVIDIA_MODEL_DEFAULT, timeout=20):
    """AI kommentár az NVIDIA NIM (build.nvidia.com) OpenAI-kompatibilis API-jával."""
    if not api_key:
        return None, "Nincs NVIDIA API kulcs."
    prompt = _build_ai_prompt(result, currency)
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
        r = http_post(NVIDIA_API_URL, headers=headers, json=payload, timeout=timeout)
        data = r.json()
        if r.status_code >= 400:
            err = data.get("error") if isinstance(data, dict) else None
            if isinstance(err, dict):
                msg = err.get("message") or err.get("code") or str(err)
            else:
                msg = str(err) if err else (data.get("detail") if isinstance(data, dict) else None) or r.text or r.reason
            return None, f"NVIDIA API ({r.status_code}): {msg}"
        content = (((data.get("choices") or [None])[0] or {}).get("message") or {}).get("content")
        if not content:
            return None, "Ures NVIDIA valasz."
        return str(content).strip(), None
    except (requests.RequestException, ValueError, TypeError) as e:
        return None, str(e)


def get_claude_cli_commentary(result, currency, model=None, timeout=90):
    """AI kommentár a helyi 'claude' CLI-n (Claude Code) keresztül, headless módban.
    Az előfizetéses (OAuth) bejelentkezést használja — nem kell API-kulcs/kredit."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return None, "A 'claude' parancs nem található. Telepítsd/jelentkezz be a Claude Code-ba."
    prompt = _build_ai_prompt(result, currency)
    cmd = [claude_bin, "-p", prompt, "--output-format", "text"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.home()),  # semleges könyvtár, ne húzzon be projekt-kontextust
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "ismeretlen hiba").strip()
            return None, f"claude CLI hiba: {err[:300]}"
        out = (proc.stdout or "").strip()
        if not out:
            return None, "Üres válasz a claude CLI-től."
        return out, None
    except subprocess.TimeoutExpired:
        return None, f"Időtúllépés ({timeout}s) a claude CLI hívásakor."
    except Exception as e:
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
            # A két csúcs legyen közel azonos (max 5% különbség)
            if abs(h1 - h2) / max(h1, h2) > 0.05:
                continue
            # Köztük legyen egy völgy legalább 1.0%-kal lejjebb
            valley = arr[m1:m2 + 1].min()
            avg_top = (h1 + h2) / 2
            if (avg_top - valley) / avg_top < 0.010:
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
            if abs(l1 - l2) / max(l1, l2) > 0.05:
                continue
            peak = arr[b1:b2 + 1].max()
            avg_bot = (l1 + l2) / 2
            if (peak - avg_bot) / avg_bot < 0.010:
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
        if left_drop > 0.012 and right_rise > 0.012:
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
        if left_rise > 0.012 and right_drop > 0.012:
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

    # --- Fej-váll (Head & Shoulders, medvés) ---
    # Három maximum, ahol a középső (fej) magasabb, a két váll közel azonos.
    if len(maxima) >= 3:
        for i in range(len(maxima) - 2):
            a, b, c = maxima[i], maxima[i + 1], maxima[i + 2]
            ha, hb, hc = arr[a], arr[b], arr[c]
            if hb > ha and hb > hc and \
               abs(ha - hc) / max(ha, hc) < 0.04 and \
               (hb - max(ha, hc)) / hb > 0.012:
                patterns.append({
                    "type": "HS",
                    "label": "Fej-váll",
                    "emoji": "🔻",
                    "desc": (
                        f"Fej-váll alakzat: fej {hb * mult:.2f}, vállak "
                        f"{ha * mult:.2f} / {hc * mult:.2f}. Medvés fordulójel."
                    ),
                    "start_idx": a,
                    "end_idx": c,
                    "direction": "bearish",
                    "color": "#ef4444",
                })
                break

    # --- Fordított Fej-váll (Inverse H&S, bullish) ---
    if len(minima) >= 3:
        for i in range(len(minima) - 2):
            a, b, c = minima[i], minima[i + 1], minima[i + 2]
            la, lb, lc = arr[a], arr[b], arr[c]
            if lb < la and lb < lc and \
               abs(la - lc) / max(la, lc) < 0.04 and \
               (min(la, lc) - lb) / min(la, lc) > 0.012:
                patterns.append({
                    "type": "iHS",
                    "label": "Fordított fej-váll",
                    "emoji": "🔼",
                    "desc": (
                        f"Fordított fej-váll: fej {lb * mult:.2f}, vállak "
                        f"{la * mult:.2f} / {lc * mult:.2f}. Bullish fordulójel."
                    ),
                    "start_idx": a,
                    "end_idx": c,
                    "direction": "bullish",
                    "color": "#22c55e",
                })
                break

    # --- Háromszög formációk (a maximumok/minimumok meredeksége alapján) ---
    def _slope_pct(idxs):
        if len(idxs) < 2:
            return None
        xs = np.array(idxs, dtype=float)
        ys = arr[np.array(idxs)]
        base = float(np.mean(ys)) or 1.0
        return float(np.polyfit(xs, ys, 1)[0]) / base * 100.0  # %/gyertya

    recent_max = [m for m in maxima if m >= n * 0.4]
    recent_min = [m for m in minima if m >= n * 0.4]
    sl_max = _slope_pct(recent_max)
    sl_min = _slope_pct(recent_min)
    if sl_max is not None and sl_min is not None and len(recent_max) >= 2 and len(recent_min) >= 2:
        flat = 0.05  # %/gyertya alatti meredekség "vízszintes"
        tri_start = min(recent_max[0], recent_min[0])
        if abs(sl_max) < flat and sl_min > flat:
            patterns.append({
                "type": "tri_asc", "label": "Emelkedő háromszög", "emoji": "📐",
                "desc": "Emelkedő háromszög: lapos ellenállás, emelkedő mélypontok — bullish.",
                "start_idx": tri_start, "end_idx": n - 1,
                "direction": "bullish", "color": "#22c55e",
            })
        elif abs(sl_min) < flat and sl_max < -flat:
            patterns.append({
                "type": "tri_desc", "label": "Csökkenő háromszög", "emoji": "📐",
                "desc": "Csökkenő háromszög: lapos támasz, csökkenő csúcsok — bearish.",
                "start_idx": tri_start, "end_idx": n - 1,
                "direction": "bearish", "color": "#ef4444",
            })
        elif sl_max < -flat and sl_min > flat:
            patterns.append({
                "type": "tri_sym", "label": "Szimmetrikus háromszög", "emoji": "📐",
                "desc": "Szimmetrikus háromszög: szűkülő sáv — kitörés várható.",
                "start_idx": tri_start, "end_idx": n - 1,
                "direction": "neutral", "color": "#f59e0b",
            })

    # Deduplikáció: ha ugyanolyan típusú alakzat van, csak az utolsót tartjuk
    seen = {}
    for p in reversed(patterns):
        if p["type"] not in seen:
            seen[p["type"]] = p
    return list(reversed(list(seen.values())))


# ---- HOLDINGS ----
def load_holdings():
    ensure_app_state_dir()
    if not HOLDINGS_PATH.is_file():
        return {}
    try:
        data = json.loads(HOLDINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {k: float(v) for k, v in data.items() if k in ASSETS and float(v) > 0}
    except (OSError, ValueError, TypeError):
        pass
    return {}


def save_holdings(holdings):
    ensure_app_state_dir()
    HOLDINGS_PATH.write_text(
        json.dumps({k: v for k, v in holdings.items() if v > 0},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---- FEAR & GREED ----
def fetch_fear_greed_index(timeout=8):
    """Fetch current Crypto Fear & Greed Index from alternative.me (free)."""
    try:
        r = http_get("https://api.alternative.me/fng/?limit=1", timeout=timeout)
        r.raise_for_status()
        d = r.json()["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    except Exception:
        return None


# ---- SUPPORT / RESISTANCE ----
def find_support_resistance(prices, n=3):
    """Find key support and resistance price levels using histogram density."""
    if prices.size < 20:
        return [], []
    current = float(prices[-1])
    bins = min(60, prices.size // 2)
    hist, edges = np.histogram(prices, bins=bins)
    levels = []
    for i in range(1, len(hist) - 1):
        if hist[i] > hist[i - 1] and hist[i] > hist[i + 1] and hist[i] > np.mean(hist):
            levels.append(float((edges[i] + edges[i + 1]) / 2))
    if not levels:
        window = min(prices.size, 90)
        recent = prices[-window:]
        levels = [float(np.percentile(recent, p)) for p in [10, 25, 50, 75, 90]]
    support = sorted([l for l in levels if l < current * 1.005], reverse=True)[:n]
    resistance = sorted([l for l in levels if l > current * 0.995])[:n]
    return support, resistance


# ---- MA CROSS ----
def detect_ma_cross(prices):
    """Detect Golden/Death Cross (MA50 vs MA200, or MA20 vs MA50 if < 200 bars)."""
    if prices.size < 52:
        return None
    ma50 = float(np.mean(prices[-50:]))
    ma50_prev = float(np.mean(prices[-51:-1]))
    if prices.size >= 202:
        ma200 = float(np.mean(prices[-200:]))
        ma200_prev = float(np.mean(prices[-201:-1]))
        if ma50_prev <= ma200_prev and ma50 > ma200:
            return {"type": "golden_cross", "fast": ma50, "slow": ma200, "fast_n": 50, "slow_n": 200}
        if ma50_prev >= ma200_prev and ma50 < ma200:
            return {"type": "death_cross", "fast": ma50, "slow": ma200, "fast_n": 50, "slow_n": 200}
        if ma50 > ma200:
            return {"type": "above_slow", "fast": ma50, "slow": ma200, "fast_n": 50, "slow_n": 200}
        return {"type": "below_slow", "fast": ma50, "slow": ma200, "fast_n": 50, "slow_n": 200}
    if prices.size >= 22:
        ma20 = float(np.mean(prices[-20:]))
        ma20_prev = float(np.mean(prices[-21:-1]))
        if ma50_prev <= ma20_prev and ma50 > ma20:
            return {"type": "golden_cross", "fast": ma50, "slow": ma20, "fast_n": 50, "slow_n": 20}
        if ma50_prev >= ma20_prev and ma50 < ma20:
            return {"type": "death_cross", "fast": ma50, "slow": ma20, "fast_n": 50, "slow_n": 20}
    return None


# ---- RICH HTML RESULT ----
def _sig_colors(decision, dark=True):
    if "📈" in decision:
        return "#22c55e", "#0f2d1f" if dark else "#f0fdf4", "#22c55e"
    if "⚠️" in decision:
        return "#ef4444", "#2d0f0f" if dark else "#fef2f2", "#ef4444"
    return "#f59e0b", "#2d220f" if dark else "#fffbeb", "#f59e0b"


def format_result_html(result, currency="HUF", dark=True):
    """Részletes HTML kártya egy eszköz elemzéséhez — minden elérhető adattal."""
    decision = result.get("decision", "")
    rec      = result.get("recommendation", {})
    m        = result.get("metrics") or {}

    border, bg, badge = _sig_colors(decision, dark)
    text  = "#e5e7eb" if dark else "#1f2937"
    dim   = "#9ca3af" if dark else "#6b7280"
    tbord = "#374151" if dark else "#d0d7de"

    def L(hu, en, de=None):
        return {"hu": hu, "en": en, "de": de or en}.get(_current_lang, en)

    def fp(v):
        if v is None:
            return "–"
        return f"{_fmt_price(v)} {currency}"

    def fvol(v):
        if v is None:
            return "–"
        v = float(v)
        if abs(v) >= 1e9:
            return f"{v/1e9:.2f}B"
        if abs(v) >= 1e6:
            return f"{v/1e6:.2f}M"
        if abs(v) >= 1e3:
            return f"{v/1e3:.1f}K"
        return f"{v:,.0f}"

    def row(lbl, val, lbl2="", val2="", vc=text, vc2=None):
        vc2 = vc2 or text
        td2 = (f'<td style="color:{dim};padding:3px 10px 3px 0;font-size:11px;white-space:nowrap">{html.escape(str(lbl2))}</td>'
               f'<td style="color:{vc2};padding:3px 0"><b>{html.escape(str(val2))}</b></td>'
               if lbl2 else '<td colspan="2"></td>')
        return (f'<tr>'
                f'<td style="color:{dim};padding:3px 10px 3px 0;font-size:11px;white-space:nowrap">{html.escape(str(lbl))}</td>'
                f'<td style="color:{vc};padding:3px 20px 3px 0"><b>{html.escape(str(val))}</b></td>'
                f'{td2}</tr>')

    def section(title):
        return (f'<tr><td colspan="4" style="padding:7px 0 2px;border-top:1px solid {tbord};'
                f'color:{dim};font-size:10px;letter-spacing:.06em;text-transform:uppercase">'
                f'{html.escape(title)}</td></tr>')

    def fullrow(label, content_html, lbl_col=None):
        lc = lbl_col or dim
        return (f'<tr><td colspan="4" style="padding:3px 0;font-size:11px;color:{text}">'
                f'<span style="color:{lc}">{html.escape(label)}:</span> {content_html}</td></tr>')

    # ── header values ──
    dcp     = result.get("day_change_pct")
    dcp_str = (f"{'▲' if dcp >= 0 else '▼'} {dcp:+.2f}%" if dcp is not None else "")
    dcp_col = "#22c55e" if (dcp or 0) >= 0 else "#ef4444"

    rsi = float(result.get("rsi", 50))
    rsi_col = "#ef4444" if rsi > 70 else "#22c55e" if rsi < 30 else text
    rsi_tag = (" 🔴" if rsi > 70 else " 🟢" if rsi < 30 else "")

    macd_h   = m.get("macd_hist")
    macd_col = "#22c55e" if (macd_h or 0) > 0 else "#ef4444"
    macd_str = f"{macd_h:+.4f}" if macd_h is not None else "–"
    macd_line = m.get("macd_line")
    macd_sig  = m.get("macd_signal")
    macd_ls   = (f"{macd_line:+.4f} / {macd_sig:+.4f}"
                 if macd_line is not None and macd_sig is not None else "–")

    rvol = m.get("realized_vol_annual_pct")
    rvol_str = f"{rvol:.1f}%" if rvol is not None else "–"
    mdd = m.get("max_drawdown_pct")
    mdd_str = f"{mdd:.2f}%" if mdd is not None else "–"

    rec_side = rec.get("side", "")
    neutral  = _tr("side_neutral")

    # ── MA cross badge ──
    cross     = result.get("ma_cross") or {}
    cross_tag = ""
    if cross.get("type") == "golden_cross":
        cross_tag = '&nbsp;<span style="background:#22c55e;color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">✨ Golden Cross</span>'
    elif cross.get("type") == "death_cross":
        cross_tag = '&nbsp;<span style="background:#ef4444;color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">☠️ Death Cross</span>'

    # ── árszintek szekció ──
    so = result.get("session_open")
    pc = result.get("previous_close")
    open_prev_html = ""
    if so is not None or pc is not None:
        open_prev_html = row(L("Mai nyitás", "Open", "Eröffnung"), fp(so),
                             L("Előző záró", "Prev close", "Vortagesschluss"), fp(pc))

    # ── Bollinger ──
    bb_u, bb_m, bb_l = m.get("bb_upper"), m.get("bb_mid"), m.get("bb_lower")
    bb_html = ""
    if bb_u is not None:
        bb_html = row(L("BB felső", "BB upper", "BB oben"), fp(bb_u),
                      L("BB alsó", "BB lower", "BB unten"), fp(bb_l), "#818cf8", "#818cf8")
        bb_html += row(L("BB közép", "BB mid", "BB Mitte"), fp(bb_m))

    # ── forgalom ──
    vlast = m.get("volume_last")
    vratio = m.get("volume_vs_sma")
    vol_html = ""
    if vlast is not None and vlast > 0:
        vr_str = f"{vratio:.2f}×" if vratio is not None else "–"
        vr_col = "#22c55e" if (vratio or 0) >= 1 else dim
        vol_html = row(L("Forgalom", "Volume", "Volumen"), fvol(vlast),
                       L("vs 20-átlag", "vs 20-avg", "vs 20-Schnitt"), vr_str, text, vr_col)

    # ── MA kereszt szint ──
    cross_html = ""
    if cross.get("fast") is not None and cross.get("slow") is not None:
        cross_html = row(f"MA{cross.get('fast_n','')}", fp(cross.get("fast")),
                         f"MA{cross.get('slow_n','')}", fp(cross.get("slow")))

    # ── jelzéspontszámok ──
    sb, ss = result.get("sig_buy"), result.get("sig_sell")
    sig_html = ""
    if sb is not None and ss is not None:
        sig_html = row(L("Vételi pont", "Buy score", "Kaufpunkte"), f"{sb:.1f}",
                       L("Eladási pont", "Sell score", "Verkaufspunkte"), f"{ss:.1f}",
                       "#22c55e", "#ef4444")

    # ── top AI jellemzők ──
    feat = result.get("feat_imp") or []
    feat_html = ""
    if feat:
        chips = "  ".join(
            f'<span style="color:{text}">{html.escape(str(n))}</span> '
            f'<span style="color:{dim}">{v*100:.0f}%</span>'
            for n, v in feat[:5]
        )
        feat_html = fullrow(L("Top AI jellemzők", "Top AI features", "Top KI-Merkmale"), chips)

    # ── indokok ──
    reasons = rec.get("reasons") or []
    reasons_html = ""
    if reasons:
        reasons_html = fullrow(L("Indok", "Reasons", "Begründung"),
                               " · ".join(html.escape(str(r)) for r in reasons))

    # ── support / resistance ──
    supports   = result.get("support", [])
    resistance = result.get("resistance", [])
    sr_html = ""
    if supports or resistance:
        s_val = "  ".join(fp(s) for s in supports[:3]) or "–"
        r_val = "  ".join(fp(r) for r in resistance[:3]) or "–"
        sr_html = (row(L("Támasz", "Support", "Stütze"), s_val, "", "", "#22c55e")
                   + row(L("Ellenállás", "Resistance", "Widerstand"), r_val, "", "", "#ef4444"))

    # ── investment ──
    inv     = result.get("investment") or {}
    inv_html = ""
    if inv:
        cap = inv.get("amount")
        if cap is not None:
            inv_html += row(L("Tőke", "Capital", "Kapital"), fp(cap),
                            L("Javasolt tét", "Suggested", "Empfohlen"),
                            f'{fp(inv.get("deploy_amount"))} ({inv.get("deploy_frac",0)*100:.0f}%)',
                            text, border)
        if inv.get("verdict"):
            inv_html += fullrow(L("Vélemény", "Verdict", "Urteil"), html.escape(inv["verdict"]))
        if inv.get("fx_note"):
            inv_html += fullrow(L("Árfolyam", "FX", "FX"), html.escape(inv["fx_note"]))

    # ── holdings ──
    qty = result.get("holding_qty") or 0
    hold_html = ""
    if qty > 0:
        val = qty * float(result.get("current", 0))
        hold_html = fullrow(
            L("Portfólió", "Portfolio", "Portfolio"),
            f'<b style="color:#38bdf8">{qty:g} × {fp(result["current"])} = {fp(val)}</b>',
        )

    # ── AI commentary ──
    ai_text = result.get("ai_commentary", "")
    ai_html = ""
    if ai_text:
        ai_html = (f'<tr><td colspan="4" style="padding:6px 0 2px;border-top:1px solid {tbord};'
                   f'color:{dim};font-size:11px;font-style:italic">🤖 {html.escape(ai_text)}</td></tr>')

    return f"""
<div style="margin:5px 2px;padding:10px 14px;border-radius:8px;
            border-left:4px solid {border};background:{bg};
            font-family:'Segoe UI','Inter',Arial,sans-serif;font-size:12px;color:{text}">
  <table width="100%" cellspacing="0" cellpadding="0"><tr>
    <td>
      <b style="font-size:14px;color:{border}">{html.escape(result.get('name',''))}</b>
      <span style="color:{dim};font-size:11px"> {html.escape(result.get('symbol',''))}</span>
      {cross_tag}
    </td>
    <td align="right">
      <b style="color:{dcp_col}">{dcp_str}</b>&nbsp;&nbsp;
      <span style="background:{badge};color:#fff;padding:2px 10px;border-radius:4px;font-weight:700">{html.escape(decision)}</span>
    </td>
  </tr></table>
  <table width="100%" cellspacing="0" cellpadding="0">
    {section(L("Ár", "Price", "Kurs"))}
    {row(L("Most", "Now", "Aktuell"), fp(result.get("current")),
         L("AI célár (1h)", "AI target (1h)", "KI-Ziel (1h)"), fp(result.get("future")), text, "#38bdf8")}
    {open_prev_html}
    {row(L("MA(20)", "MA(20)", "MA(20)"), fp(result.get("ma")),
         L("Napi vált.", "Daily chg", "Tagesänd."),
         (f"{dcp:+.2f}%" if dcp is not None else "–"), text, dcp_col)}
    {section(L("AI modell", "AI model", "KI-Modell"))}
    {row(L("Esély fel", "Prob up", "Wahrsch. auf"), f"{result.get('next_up_prob',0)*100:.1f}%",
         L("Pontosság", "Accuracy", "Genauigkeit"), f"{result.get('accuracy',0)*100:.1f}%", "#38bdf8")}
    {feat_html}
    {section(L("Indikátorok / kockázat", "Indicators / risk", "Indikatoren / Risiko"))}
    {row(f"RSI", f"{rsi:.1f}{rsi_tag}",
         L("Volatilitás", "Volatility", "Volatilität"), rvol_str, rsi_col)}
    {row("MACD hist", macd_str, "MACD line/sig", macd_ls, macd_col)}
    {bb_html}
    {vol_html}
    {row(L("Max visszaesés", "Max drawdown", "Max Drawdown"), mdd_str, "", "", "#ef4444")}
    {cross_html}
    {sr_html}
    {section(L("Döntés / ajánlás", "Decision / recommendation", "Entscheidung / Empfehlung"))}
    {row(L("Ajánlás", "Action", "Empfehlung"),
         f"{rec.get('action','–')}  ({rec_side})",
         L("Bizalom", "Confidence", "Konfidenz"),
         f"{rec.get('confidence',0)*100:.1f}%")}
    {sig_html}
    {"" if rec_side == neutral else
     row(L("Belépő", "Entry", "Einstieg"), fp(rec.get("entry")), "", "", "#38bdf8")}
    {"" if rec_side == neutral else
     row("Stop-loss", fp(rec.get("stop")), "Take-profit", fp(rec.get("take_profit")), "#ef4444", "#22c55e")}
    {reasons_html}
    {(section(L("Befektetés", "Investment", "Investition")) + inv_html) if inv_html else ""}
    {hold_html}
    {ai_html}
  </table>
</div>"""


def format_result(result, currency="HUF"):
    t = _tr
    rec = result["recommendation"]
    text = f"{result['name']}\n"
    dcp = result.get("day_change_pct")
    if dcp is not None:
        text += f"{t('fr_daily_change')}: {dcp:+.2f}%\n"
    so = result.get("session_open")
    pzc = result.get("previous_close")
    if so is not None:
        text += f"{t('fr_session_open')}: {int(so):,} {currency}\n"
    if pzc is not None:
        text += f"{t('fr_prev_close')}: {int(pzc):,} {currency}\n"
    text += f"{t('fr_now')}: {int(result['current']):,} {currency}\n"
    text += f"{t('fr_ai_target')}: {int(result['future']):,} {currency}\n"
    text += f"{t('fr_ai_prob')}: {result['next_up_prob'] * 100:.1f}%\n"
    text += f"{t('fr_ai_acc')}: {result['accuracy'] * 100:.1f}%\n"
    text += f"{t('fr_rsi')}: {result['rsi']:.2f}\n"
    text += f"{t('fr_ma')}: {int(result['ma']):,}\n"
    m = result.get("metrics") or {}
    if m:
        text += f"{t('fr_indicators')}:\n"
        if m.get("macd_hist") is not None:
            text += (
                f"- {t('fr_macd')}: line {m['macd_line']:.4f}, sig {m['macd_signal']:.4f}, "
                f"hist {m['macd_hist']:.4f}\n"
            )
        if m.get("bb_mid") is not None:
            text += (
                f"- {t('fr_bollinger')}: up {m['bb_upper']:.2f}, mid {m['bb_mid']:.2f}, "
                f"lo {m['bb_lower']:.2f}\n"
            )
        vl, vr = m.get("volume_last"), m.get("volume_vs_sma")
        if vl is not None and vl > 0 and vr is not None:
            text += f"- {t('fr_volume')}: {vl:,.0f}, {t('fr_vol_ratio')}: {vr:.2f}x\n"
        elif vl is not None and vl > 0:
            text += f"- {t('fr_volume')}: {vl:,.0f}\n"
        if m.get("realized_vol_annual_pct") is not None:
            text += f"- {t('fr_realized_vol')}: {m['realized_vol_annual_pct']:.1f}%\n"
        if m.get("max_drawdown_pct") is not None:
            text += f"- {t('fr_max_dd')}: {m['max_drawdown_pct']:.2f}%\n"
    feat_imp = result.get("feat_imp") or []
    if feat_imp:
        text += f"{t('fr_top_features')}:\n"
        for fname, fval in feat_imp[:5]:
            text += f"- {fname}: {fval * 100:.1f}%\n"
    text += f"{t('fr_decision')}: {result['decision']}\n"
    text += f"{t('fr_recommendation')}:\n"
    text += f"- {t('fr_direction')}: {rec['action']} ({rec['side']})\n"
    text += f"- {t('fr_confidence')}: {rec['confidence'] * 100:.1f}%\n"
    neutral = _tr("side_neutral")
    if rec["side"] != neutral:
        text += f"- {t('fr_entry')}: {int(rec['entry']):,} {currency}\n"
        text += f"- {t('fr_stop')}: {int(rec['stop']):,} {currency}\n"
        text += f"- {t('fr_tp')}: {int(rec['take_profit']):,} {currency}\n"
    text += f"- {t('fr_reason')}: {', '.join(rec['reasons'])}\n"
    if result.get("investment"):
        inv = result["investment"]
        text += f"\n{t('fr_investment')}:\n"
        text += f"- {t('fr_capital')}: {int(inv['amount']):,} {currency}\n"
        text += f"- {t('fr_verdict')}: {inv['verdict']}\n"
        if inv.get("fx_note"):
            text += f"- {t('fr_fx_note')}: {inv['fx_note']}\n"
        text += (
            f"- {t('fr_suggested_bet')}: ~{int(inv['deploy_amount']):,} {currency} "
            f"({inv['deploy_frac'] * 100:.0f}% {t('fr_of_amount')})\n"
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
        INDICATOR_PANEL_H = 96

        def __init__(self, parent=None):
            super().__init__(parent)
            self._candles = []
            self._patterns = []
            self._title = ""
            self._currency = "HUF"
            self._x_labels = []
            self._dark_mode = True
            self._bb_bands = None      # (upper, mid, lower) np.array-ek vagy None
            self._indicator = None     # {"type": "rsi"/"macd", ...} vagy None
            self.setMinimumHeight(360)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.setStyleSheet("background: #0f172a; border-radius: 14px;")

        def set_dark_mode(self, dark):
            self._dark_mode = dark
            bg = "#0f172a" if dark else "#f4f7fc"
            self.setStyleSheet(f"background: {bg}; border-radius: 14px;")
            self.update()

        def set_data(self, candles, patterns, title="", currency="HUF", x_labels=None,
                     bb_bands=None, indicator=None):
            self._candles  = candles
            self._patterns = patterns
            self._title    = title
            self._currency = currency
            self._x_labels = x_labels or []
            self._bb_bands = bb_bands
            self._indicator = indicator
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

            bg_col = QColor("#0d1117") if self._dark_mode else QColor("#f6f8fa")
            fg_col = QColor("#8b949e") if self._dark_mode else QColor("#57606a")
            grid_col = QColor("#21262d") if self._dark_mode else QColor("#d0d7de")
            label_col = QColor("#484f58") if self._dark_mode else QColor("#8c959f")
            title_col = QColor("#c9d1d9") if self._dark_mode else QColor("#24292f")
            panel_bg = QColor("#0d1117") if self._dark_mode else QColor("#f6f8fa")
            sep_col = QColor("#30363d") if self._dark_mode else QColor("#d0d7de")

            painter.fillRect(0, 0, w, h, bg_col)

            candles = self._candles
            if not candles:
                painter.setPen(QPen(fg_col))
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
            ind_h = self.INDICATOR_PANEL_H if self._indicator else 0
            mb = self.MARGIN_B + panel_h
            plot_w = w - ml - mr
            plot_h = h - mt - mb - ind_h

            if plot_w < 10 or plot_h < 10:
                return

            # ---- price range ----
            highs  = [c[2] for c in candles]
            lows   = [c[3] for c in candles]
            y_max  = max(highs)
            y_min  = min(lows)
            # A Bollinger-sávok kilóghatnak a gyertyák sávjából — vegyük bele a skálába.
            if self._bb_bands is not None:
                up_b, _mid_b, lo_b = self._bb_bands
                fin_up = up_b[~np.isnan(up_b)] if up_b is not None else np.array([])
                fin_lo = lo_b[~np.isnan(lo_b)] if lo_b is not None else np.array([])
                if fin_up.size:
                    y_max = max(y_max, float(np.max(fin_up)))
                if fin_lo.size:
                    y_min = min(y_min, float(np.min(fin_lo)))
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
            grid_pen = QPen(grid_col)
            grid_pen.setWidthF(0.8)
            painter.setPen(grid_pen)
            n_grid = 6
            for i in range(n_grid + 1):
                price = y_min + y_span * i / n_grid
                yy = to_y(price)
                painter.drawLine(int(ml), int(yy), int(w - mr), int(yy))
                # price label
                painter.setPen(QPen(label_col))
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

            # ---- Bollinger-sávok overlay ----
            if self._bb_bands is not None:
                up_b, mid_b, lo_b = self._bb_bands

                def _poly(vals):
                    pts = []
                    for i in range(min(len(vals), n)):
                        v = vals[i]
                        if v is None or np.isnan(v):
                            continue
                        pts.append((to_x(i), to_y(float(v))))
                    return pts

                up_pts = _poly(up_b)
                lo_pts = _poly(lo_b)
                mid_pts = _poly(mid_b)

                # árnyékolt sáv (felső → alsó visszafelé)
                if len(up_pts) >= 2 and len(lo_pts) >= 2:
                    from PySide6.QtGui import QPolygonF
                    poly = QPolygonF()
                    for x, y in up_pts:
                        poly.append(QPoint(int(x), int(y)))
                    for x, y in reversed(lo_pts):
                        poly.append(QPoint(int(x), int(y)))
                    fill = QColor(99, 102, 241, 28)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(fill)
                    painter.drawPolygon(poly)

                def _draw_line(pts, color, width, dashed=False):
                    if len(pts) < 2:
                        return
                    pen = QPen(QColor(color))
                    pen.setWidthF(width)
                    if dashed:
                        pen.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    for k in range(1, len(pts)):
                        painter.drawLine(int(pts[k - 1][0]), int(pts[k - 1][1]),
                                         int(pts[k][0]), int(pts[k][1]))

                _draw_line(up_pts, "#818cf8", 1.2)
                _draw_line(lo_pts, "#818cf8", 1.2)
                _draw_line(mid_pts, "#a78bfa", 1.0, dashed=True)

            # ---- Indikátor alpanel (RSI / MACD) ----
            if self._indicator:
                self._draw_indicator_panel(painter, ml, mr, w, mt, plot_h, ind_h, n, to_x, fg_col, grid_col)

            # ---- x-axis labels ----
            painter.setPen(QPen(label_col))
            for idx, lbl in self._x_labels:
                if 0 <= idx < n:
                    xx = int(to_x(idx))
                    painter.drawText(
                        xx - 32, h - mb + 4, 64, 20,
                        Qt.AlignmentFlag.AlignCenter,
                        lbl,
                    )

            # ---- title ----
            title_pen = QPen(title_col)
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
                painter.fillRect(0, panel_y, w, panel_h, panel_bg)
                sep_pen = QPen(sep_col)
                sep_pen.setWidthF(1.0)
                painter.setPen(sep_pen)
                painter.drawLine(0, panel_y, w, panel_y)

                f2 = QFont()
                f2.setPointSize(9)
                painter.setFont(f2)
                line_h = 16
                y_txt = panel_y + 6
                for pat in self._patterns:
                    if y_txt + line_h > h:
                        break
                    painter.setPen(QPen(QColor(pat["color"])))
                    painter.drawText(
                        ml, int(y_txt), w - ml - mr, line_h,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        f"{pat['emoji']}  {pat['label']}: {pat['desc']}",
                    )
                    y_txt += line_h

        def _draw_indicator_panel(self, painter, ml, mr, w, mt, plot_h, ind_h, n, to_x, fg_col, grid_col):
            """RSI vagy MACD alpanel a gyertyadiagram alatt, közös x-tengellyel."""
            ind = self._indicator or {}
            top = mt + plot_h + 8
            bottom = mt + plot_h + ind_h - 4
            height = max(1.0, bottom - top)

            # háttér + keret
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 0))
            sep = QPen(grid_col)
            sep.setWidthF(0.8)
            painter.setPen(sep)
            painter.drawLine(int(ml), int(top), int(w - mr), int(top))

            itype = ind.get("type")
            if itype == "rsi":
                vals = ind.get("values")
                if vals is None:
                    return

                def ry(v):
                    return bottom - (max(0.0, min(100.0, v)) / 100.0) * height

                # 30 / 50 / 70 szintek
                for lvl, col, dash in ((70, "#ef4444", True), (50, "#6b7280", True), (30, "#22c55e", True)):
                    pen = QPen(QColor(col))
                    pen.setWidthF(0.8)
                    pen.setStyle(Qt.PenStyle.DashLine if dash else Qt.PenStyle.SolidLine)
                    painter.setPen(pen)
                    yy = ry(lvl)
                    painter.drawLine(int(ml), int(yy), int(w - mr), int(yy))
                    painter.drawText(2, int(yy) - 8, ml - 6, 16,
                                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                                     str(lvl))
                # RSI vonal
                pen = QPen(QColor("#38bdf8"))
                pen.setWidthF(1.4)
                painter.setPen(pen)
                prev = None
                for i in range(min(len(vals), n)):
                    v = vals[i]
                    if v is None or np.isnan(v):
                        prev = None
                        continue
                    cur = (to_x(i), ry(float(v)))
                    if prev is not None:
                        painter.drawLine(int(prev[0]), int(prev[1]), int(cur[0]), int(cur[1]))
                    prev = cur
                painter.setPen(QPen(fg_col))
                painter.drawText(int(ml) + 4, int(top) + 2, 80, 14,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "RSI (14)")

            elif itype == "macd":
                line = ind.get("line")
                signal = ind.get("signal")
                hist = ind.get("hist")
                if line is None:
                    return
                allv = []
                for a in (line, signal, hist):
                    if a is not None:
                        allv.append(a[~np.isnan(a)])
                allv = np.concatenate(allv) if allv else np.array([0.0])
                vmax = float(np.max(np.abs(allv))) or 1.0
                zero_y = (top + bottom) / 2.0

                def my(v):
                    return zero_y - (v / vmax) * (height / 2.0 * 0.9)

                # zéró vonal
                pen = QPen(QColor("#6b7280"))
                pen.setWidthF(0.8)
                painter.setPen(pen)
                painter.drawLine(int(ml), int(zero_y), int(w - mr), int(zero_y))
                # histogram oszlopok
                bar_w = max(1.0, (w - ml - mr) / n * 0.6)
                painter.setPen(Qt.PenStyle.NoPen)
                if hist is not None:
                    for i in range(min(len(hist), n)):
                        v = hist[i]
                        if v is None or np.isnan(v):
                            continue
                        x = to_x(i)
                        yv = my(float(v))
                        col = QColor("#22c55e") if v >= 0 else QColor("#ef4444")
                        col.setAlpha(150)
                        painter.setBrush(col)
                        y0, y1 = min(zero_y, yv), max(zero_y, yv)
                        painter.drawRect(int(x - bar_w / 2), int(y0), int(bar_w), int(max(1, y1 - y0)))

                def _line(arr, color):
                    pen = QPen(QColor(color))
                    pen.setWidthF(1.3)
                    painter.setPen(pen)
                    prev = None
                    for i in range(min(len(arr), n)):
                        v = arr[i]
                        if v is None or np.isnan(v):
                            prev = None
                            continue
                        cur = (to_x(i), my(float(v)))
                        if prev is not None:
                            painter.drawLine(int(prev[0]), int(prev[1]), int(cur[0]), int(cur[1]))
                        prev = cur

                _line(line, "#38bdf8")
                _line(signal, "#f59e0b")
                painter.setPen(QPen(fg_col))
                painter.drawText(int(ml) + 4, int(top) + 2, 120, 14,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "MACD (12,26,9)")


if QT_AVAILABLE:
    # ---- GUI ----
    class App(QWidget):
        def __init__(self):
            super().__init__()
            self._lang, self._theme = load_app_config()
            global _current_lang
            _current_lang = self._lang
            self.setWindowTitle("AI Asset Analyzer Pro")
            self.setGeometry(100, 100, 1280, 780)
            self.apply_theme()
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
            # Discord webhook (közvetlen push, bot nélkül)
            self.discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
            if not self.discord_webhook_url:
                self.discord_webhook_url = load_discord_config()
            self.discord_enabled = bool(self.discord_webhook_url)
            self.ai_commentary_enabled = False
            self.ai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
            self.ai_model = OPENAI_MODEL_DEFAULT
            self.claude_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
            self.claude_model = ANTHROPIC_MODEL_DEFAULT
            self.claude_cli_model = ""  # üres = a Claude Code alap modellje
            self.nvidia_api_key = os.getenv("NVIDIA_API_KEY", "").strip()
            self.nvidia_model = NVIDIA_MODEL_DEFAULT
            # Melyik szolgáltatót használja az AI kommentár:
            # "openai" | "claude" (API) | "claude_cli" (helyi előfizetés) | "nvidia"
            self.ai_provider = "claude" if self.claude_api_key else "openai"
            self.csv_autosave_enabled = True
            self.csv_path = str(Path.cwd() / "live_history.csv")
            self.holdings = load_holdings()
            self.last_prices_live = {}
            self.live_timer = QTimer(self)
            self.live_timer.timeout.connect(self.run_live_tick)
            self.favorite_names = set(load_favorites())
            self.custom_rules = load_custom_alert_rules()
            self._rule_cooldown = {}
            self._last_results = []
            self._last_scheduled_run_date = None
            self._fng_value = None
            self._fng_label = ""

            # ---- MAIN LAYOUT: vertical stack ----
            main_vbox = QVBoxLayout()
            main_vbox.setContentsMargins(12, 10, 12, 10)
            main_vbox.setSpacing(8)

            # RGB top accent bar
            self._rgb_bar = RGBBorderBar(h=4)
            main_vbox.addWidget(self._rgb_bar)

            # ---- TOP BAR ----
            top_bar = QHBoxLayout()
            top_bar.setSpacing(10)
            self.label = RGBTitleLabel("🤖 AI + Indikátor Elemző Pro")
            self.label.setObjectName("title_label")
            top_bar.addWidget(self.label)
            top_bar.addStretch(1)
            # stats inline
            self.stats_assets = QLabel("Kiválasztva: 0")
            self.stats_assets.setObjectName("stat_chip")
            self.stats_decisions = QLabel("Vétel 0 | Eladás 0 | Várj 0")
            self.stats_decisions.setObjectName("stat_chip")
            self.stats_update = QLabel("–")
            self.stats_update.setObjectName("stat_chip_dim")
            top_bar.addWidget(self.stats_assets)
            top_bar.addWidget(self.stats_decisions)
            top_bar.addWidget(self.stats_update)
            # primary action buttons in top bar
            self.btn = AnimatedButton("▶  Elemzés")
            self.btn.setObjectName("primary_btn")
            self.btn.clicked.connect(lambda: self.run_analysis())
            top_bar.addWidget(self.btn)
            self.btn_live = AnimatedButton("📡  Élő mód indítása")
            self.btn_live.setObjectName("live_btn")
            self.btn_live.clicked.connect(self.toggle_live_mode)
            top_bar.addWidget(self.btn_live)
            self.btn_interval = AnimatedButton("⏱  Időköz: 30s")
            self.btn_interval.clicked.connect(self.set_live_interval)
            top_bar.addWidget(self.btn_interval)
            self.live_status = QLabel("Élő mód: kikapcsolva")
            self.live_status.setObjectName("stat_chip_dim")
            self._pulse_dot = PulsingDot()
            top_bar.addWidget(self._pulse_dot)
            top_bar.addWidget(self.live_status)

            self.fng_label = QLabel("😐 F&G: –")
            self.fng_label.setObjectName("fng_chip")
            self.fng_label.setToolTip("Crypto Fear & Greed Index (alternative.me)")
            top_bar.addWidget(self.fng_label)

            main_vbox.addLayout(top_bar)

            # ---- CONTENT ROW ----
            content_row = QHBoxLayout()
            content_row.setSpacing(10)

            # ---- LEFT PANEL ----
            left_col = QVBoxLayout()
            left_col.setSpacing(6)

            # Category chips
            chip_row = QHBoxLayout()
            chip_row.setSpacing(4)
            self._active_category = "All"
            self._category_btns = {}
            for cat in ASSET_CATEGORIES:
                b = QPushButton(cat)
                b.setObjectName("chip_active" if cat == "All" else "chip")
                b.setCheckable(True)
                b.setChecked(cat == "All")
                b.clicked.connect(lambda checked, c=cat: self.set_category_filter(c))
                chip_row.addWidget(b)
                self._category_btns[cat] = b
            chip_row.addStretch(1)
            left_col.addLayout(chip_row)

            # Search
            self.asset_search = QLineEdit()
            self.asset_search.setPlaceholderText("Keresés eszköz névre…")
            self.asset_search.textChanged.connect(self.filter_asset_list)
            left_col.addWidget(self.asset_search)

            # Fav row
            fav_row = QHBoxLayout()
            self.cb_favorites_only = QCheckBox("Csak kedvencek")
            self.cb_favorites_only.toggled.connect(self.on_favorites_filter_toggled)
            fav_row.addWidget(self.cb_favorites_only)
            self.btn_fav_toggle = QPushButton("☆")
            self.btn_fav_toggle.setToolTip("Kedvenc váltás")
            self.btn_fav_toggle.setFixedWidth(32)
            self.btn_fav_toggle.clicked.connect(self.toggle_favorite_selection)
            fav_row.addWidget(self.btn_fav_toggle)
            left_col.addLayout(fav_row)

            # Currency + amount row
            cur_row = QHBoxLayout()
            self.cur_label = QLabel("Megjelenítés:")
            cur_row.addWidget(self.cur_label)
            self.currency_combo = QComboBox()
            self._populate_currency_combo()
            self.currency_combo.currentIndexChanged.connect(self.on_display_currency_changed)
            cur_row.addWidget(self.currency_combo, 1)
            left_col.addLayout(cur_row)

            # Asset list
            self.list_widget = QListWidget()
            self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            for name in ASSETS:
                self.list_widget.addItem(name)
            self.list_widget.setCurrentRow(0)
            self.list_widget.setMinimumWidth(240)
            self.list_widget.setMaximumWidth(300)
            left_col.addWidget(self.list_widget, 1)

            # Bottom left: select all, clear, amount
            bottom_left = QHBoxLayout()
            self.btn_select_all = QPushButton("☑ Összes")
            self.btn_select_all.clicked.connect(self.select_all_assets)
            bottom_left.addWidget(self.btn_select_all)
            self.btn_clear = QPushButton("🗑 Törlés")
            self.btn_clear.clicked.connect(self.output_clear)
            bottom_left.addWidget(self.btn_clear)
            self.btn_set_amount = QPushButton("💰 Összeg")
            self.btn_set_amount.clicked.connect(self.set_invest_amount)
            bottom_left.addWidget(self.btn_set_amount)
            left_col.addLayout(bottom_left)

            # ---- Összegző panel (áttekintés) ----
            self.summary_panel = QLabel()
            self.summary_panel.setObjectName("summary_panel")
            self.summary_panel.setWordWrap(True)
            self.summary_panel.setTextFormat(Qt.TextFormat.RichText)
            self.summary_panel.setMinimumHeight(132)
            self.summary_panel.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            left_col.addWidget(self.summary_panel)

            left_panel = QWidget()
            left_panel.setLayout(left_col)
            content_row.addWidget(left_panel)

            right = QVBoxLayout()
            right.setSpacing(8)

            layout = main_vbox  # alias so the rest of __init__ works

            # ---- NAV BAR (dropdown menu) ----
            from PySide6.QtWidgets import QStackedWidget
            nav_row = QHBoxLayout()
            nav_row.setSpacing(8)
            self.nav_combo = QComboBox()
            self.nav_combo.setObjectName("nav_combo")
            self.nav_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            self.nav_combo.setMinimumWidth(220)
            nav_row.addWidget(self.nav_combo)
            nav_row.addStretch(1)
            right.addLayout(nav_row)

            self.stacked = QStackedWidget()
            self.nav_combo.currentIndexChanged.connect(self.stacked.setCurrentIndex)

            # keep a tab-compatible alias so existing addTab calls work
            class _FakeTabs:
                def __init__(self, stacked, combo):
                    self._s = stacked
                    self._c = combo
                    self._labels = []
                def addTab(self, widget, label):
                    self._s.addWidget(widget)
                    self._labels.append(label)
                    self._c.addItem(label)
                def count(self):
                    return self._s.count()
                def setTabText(self, i, text):
                    self._labels[i] = text
            self.tabs = _FakeTabs(self.stacked, self.nav_combo)

            analysis_tab = QWidget()
            analysis_layout = QVBoxLayout()
            analysis_layout.setSpacing(6)

            out_row = QHBoxLayout()
            self.btn_copy_output = QPushButton("📋 Vágólapra")
            self.btn_copy_output.clicked.connect(self.copy_output_to_clipboard)
            out_row.addWidget(self.btn_copy_output)
            self.btn_scanner = QPushButton("⚡ Gyors scanner")
            self.btn_scanner.setToolTip("Összes kijelölt eszköz kompakt jelzéstáblája")
            self.btn_scanner.clicked.connect(self.run_quick_scanner)
            out_row.addWidget(self.btn_scanner)
            self.btn_export_csv = QPushButton("💾 CSV export")
            self.btn_export_csv.setToolTip("Az utolsó elemzés eredményeinek exportja CSV-be")
            self.btn_export_csv.clicked.connect(self.export_analysis_csv)
            out_row.addWidget(self.btn_export_csv)
            out_row.addStretch(1)
            self.analysis_info_label = QLabel("")
            self.analysis_info_label.setObjectName("stat_chip_dim")
            out_row.addWidget(self.analysis_info_label)
            analysis_layout.addLayout(out_row)

            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(False)
            self.progress_bar.setFixedHeight(5)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setObjectName("analysis_progress")
            analysis_layout.addWidget(self.progress_bar)
            self._shimmer = ShimmerBar()
            analysis_layout.addWidget(self._shimmer)

            self.output = QTextEdit()
            self.output.setReadOnly(True)
            self.output.setPlaceholderText("Az elemzés eredménye itt fog megjelenni…  (F5 = Elemzés)")
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
            self.chart_range_btns = []
            for label, rng, iv in self.chart_range_specs:

                def _make_chart_handler(r, i):
                    return lambda: self.set_chart_interval(r, i)

                b = QPushButton(label)
                b.clicked.connect(_make_chart_handler(rng, iv))
                chart_btn_row.addWidget(b)
                self.chart_range_btns.append(b)
            chart_btn_row.addStretch(1)
            chart_outer.addLayout(chart_btn_row)

            chart_opts_row = QHBoxLayout()
            self.cb_compare_chart = QCheckBox("2 eszköz összehasonlítás (index 100 = indulás)")
            self.cb_compare_chart.toggled.connect(self.refresh_price_chart)
            chart_opts_row.addWidget(self.cb_compare_chart)
            self.cb_bb_chart = QCheckBox("Bollinger sávok")
            self.cb_bb_chart.toggled.connect(self.refresh_price_chart)
            chart_opts_row.addWidget(self.cb_bb_chart)
            self.cb_pattern_detect = QCheckBox("Alakzatfelismerés (M / W / V / ∧ / fej-váll / háromszög)")
            self.cb_pattern_detect.setChecked(True)
            self.cb_pattern_detect.toggled.connect(self.refresh_price_chart)
            chart_opts_row.addWidget(self.cb_pattern_detect)
            self.indicator_combo = QComboBox()
            self.indicator_combo.addItems(["Alpanel: nincs", "Alpanel: RSI", "Alpanel: MACD"])
            self.indicator_combo.setToolTip("Indikátor alpanel a gyertyadiagram alatt")
            self.indicator_combo.currentIndexChanged.connect(self.refresh_price_chart)
            chart_opts_row.addWidget(self.indicator_combo)
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

            # ---- Riasztási szabály dashboard (vizuális szerkesztő) ----
            rules_group = QGroupBox("🔔  Riasztási szabályok")
            rules_group.setObjectName("settings_group")
            rules_v = QVBoxLayout()
            rules_v.setContentsMargins(10, 8, 10, 10)
            rule_form = QHBoxLayout()
            self.rule_asset_combo = QComboBox()
            self.rule_asset_combo.addItem("* (összes)")
            for _an in ASSETS:
                self.rule_asset_combo.addItem(_an)
            rule_form.addWidget(self.rule_asset_combo, 2)
            self._rule_conditions = [
                ("Ár ≥", "price_above"),
                ("Ár ≤", "price_below"),
                ("RSI ≥", "rsi_above"),
                ("RSI ≤", "rsi_below"),
            ]
            self.rule_cond_combo = QComboBox()
            for lbl, _k in self._rule_conditions:
                self.rule_cond_combo.addItem(lbl)
            rule_form.addWidget(self.rule_cond_combo, 1)
            self.rule_value_edit = QLineEdit()
            self.rule_value_edit.setPlaceholderText("érték")
            self.rule_value_edit.setFixedWidth(110)
            rule_form.addWidget(self.rule_value_edit)
            self.btn_add_rule = QPushButton("➕ Hozzáadás")
            self.btn_add_rule.clicked.connect(self.add_alert_rule_from_form)
            rule_form.addWidget(self.btn_add_rule)
            rules_v.addLayout(rule_form)

            self.rules_table = QTableWidget()
            self.rules_table.setColumnCount(3)
            self.rules_table.setHorizontalHeaderLabels(["Eszköz", "Feltétel", "Érték"])
            self.rules_table.setMaximumHeight(150)
            self.rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.rules_table.horizontalHeader().setStretchLastSection(True)
            rules_v.addWidget(self.rules_table)

            rules_btn_row = QHBoxLayout()
            self.btn_remove_rule = QPushButton("🗑 Kijelölt szabály törlése")
            self.btn_remove_rule.clicked.connect(self.remove_selected_rule)
            rules_btn_row.addWidget(self.btn_remove_rule)
            self.btn_edit_rules_json = QPushButton("📋 JSON szerkesztő")
            self.btn_edit_rules_json.clicked.connect(self.edit_alert_rules_dialog)
            rules_btn_row.addWidget(self.btn_edit_rules_json)
            rules_btn_row.addStretch(1)
            rules_v.addLayout(rules_btn_row)
            rules_group.setLayout(rules_v)
            alerts_layout.addWidget(rules_group)

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
            portfolio_layout.setSpacing(6)

            # Holdings editor toolbar
            ph_row = QHBoxLayout()
            self.btn_edit_holdings = QPushButton("✏️  Mennyiségek szerkesztése")
            self.btn_edit_holdings.clicked.connect(self.edit_holdings_dialog)
            ph_row.addWidget(self.btn_edit_holdings)
            self.btn_refresh_portfolio = QPushButton("🔄  Frissítés")
            self.btn_refresh_portfolio.clicked.connect(self.refresh_portfolio_live)
            ph_row.addWidget(self.btn_refresh_portfolio)
            ph_row.addStretch(1)
            self.portfolio_total_label = QLabel("")
            self.portfolio_total_label.setObjectName("stat_chip")
            ph_row.addWidget(self.portfolio_total_label)
            portfolio_layout.addLayout(ph_row)

            # Holdings table
            self.holdings_table = QTableWidget()
            self.holdings_table.setColumnCount(6)
            self.holdings_table.setHorizontalHeaderLabels(
                ["Eszköz", "Mennyiség", "Jelenlegi ár", "Érték", "Napi %", "Döntés"]
            )
            self.holdings_table.setAlternatingRowColors(True)
            self.holdings_table.horizontalHeader().setStretchLastSection(True)
            portfolio_layout.addWidget(self.holdings_table)

            # Summary text area
            self.portfolio_output = QTextEdit()
            self.portfolio_output.setReadOnly(True)
            self.portfolio_output.setMaximumHeight(140)
            self.portfolio_output.setPlaceholderText("Portfolio összegzés itt jelenik meg...")
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

            # ---- SETTINGS TAB (grouped, scrollable) ----
            settings_tab = QWidget()
            settings_outer = QVBoxLayout()
            settings_outer.setContentsMargins(0, 0, 0, 0)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll_content = QWidget()
            settings_layout = QVBoxLayout(scroll_content)
            settings_layout.setSpacing(12)
            settings_layout.setContentsMargins(10, 10, 10, 10)

            def make_group(title):
                gb = QGroupBox(title)
                gb.setObjectName("settings_group")
                inner = QVBoxLayout()
                inner.setSpacing(6)
                inner.setContentsMargins(10, 8, 10, 10)
                gb.setLayout(inner)
                return gb, inner

            # ── 1. Megjelenítés ──
            grp_appearance, lay_appearance = make_group("🎨  Megjelenítés")
            r1 = QHBoxLayout()
            self.lang_label_widget = QLabel("Nyelv:")
            r1.addWidget(self.lang_label_widget)
            self.lang_combo = QComboBox()
            self.lang_combo.addItems(["Magyar", "English", "Deutsch"])
            lang_map = {"hu": 0, "en": 1, "de": 2}
            self.lang_combo.setCurrentIndex(lang_map.get(self._lang, 0))
            self.lang_combo.currentIndexChanged.connect(self.on_lang_changed)
            r1.addWidget(self.lang_combo, 1)
            lay_appearance.addLayout(r1)
            r2 = QHBoxLayout()
            self.theme_label_widget = QLabel("Téma:")
            r2.addWidget(self.theme_label_widget)
            self.theme_combo = QComboBox()
            self.theme_combo.addItems(["Sötét", "Világos"])
            self.theme_combo.setCurrentIndex(0 if self._theme == "dark" else 1)
            self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
            r2.addWidget(self.theme_combo, 1)
            lay_appearance.addLayout(r2)
            settings_layout.addWidget(grp_appearance)

            # ── 2. Általános ──
            grp_general, lay_general = make_group("⚙️  Általános")
            self.auto_clear_checkbox = QCheckBox("Elemzés törlése minden frissítés előtt")
            self.auto_clear_checkbox.setChecked(self.auto_clear_analysis)
            self.auto_clear_checkbox.toggled.connect(self.toggle_auto_clear)
            lay_general.addWidget(self.auto_clear_checkbox)
            self.sound_alert_checkbox = QCheckBox("Hangriasztás engedélyezve")
            self.sound_alert_checkbox.setChecked(self.sound_alerts_enabled)
            self.sound_alert_checkbox.toggled.connect(self.toggle_sound_alerts)
            lay_general.addWidget(self.sound_alert_checkbox)
            self.csv_autosave_checkbox = QCheckBox("CSV automatikus mentés élőben")
            self.csv_autosave_checkbox.setChecked(self.csv_autosave_enabled)
            self.csv_autosave_checkbox.toggled.connect(self.toggle_csv_autosave)
            lay_general.addWidget(self.csv_autosave_checkbox)
            self.btn_csv_path = QPushButton("💾  CSV fájl: live_history.csv")
            self.btn_csv_path.clicked.connect(self.set_csv_path)
            lay_general.addWidget(self.btn_csv_path)
            sched_row = QHBoxLayout()
            self.cb_schedule_analysis = QCheckBox("Napi ütemezett elemzés:")
            self.time_schedule = QTimeEdit()
            self.time_schedule.setDisplayFormat("HH:mm")
            self.time_schedule.setTime(QTime(9, 0))
            sched_row.addWidget(self.cb_schedule_analysis)
            sched_row.addWidget(self.time_schedule)
            sched_row.addStretch(1)
            lay_general.addLayout(sched_row)
            settings_layout.addWidget(grp_general)
            self.schedule_timer = QTimer(self)
            self.schedule_timer.timeout.connect(self.schedule_tick)
            self.schedule_timer.start(30_000)

            # ── 3. Riasztások ──
            grp_alerts, lay_alerts = make_group("🔔  Riasztások")
            self.btn_alert_threshold = QPushButton("⚡  Küszöb: 0.80%")
            self.btn_alert_threshold.clicked.connect(self.set_alert_threshold)
            lay_alerts.addWidget(self.btn_alert_threshold)
            self.btn_edit_alert_rules = QPushButton("📋  Egyedi ár/RSI szabályok (JSON)…")
            self.btn_edit_alert_rules.clicked.connect(self.edit_alert_rules_dialog)
            lay_alerts.addWidget(self.btn_edit_alert_rules)
            settings_layout.addWidget(grp_alerts)

            # ── 4. Telegram ──
            grp_tg, lay_tg = make_group("📲  Telegram")
            self.btn_telegram = QPushButton("⚙️  Beállítás (token + chat ID)")
            self.btn_telegram.setObjectName("telegram_btn")
            self.btn_telegram.clicked.connect(self.configure_telegram)
            lay_tg.addWidget(self.btn_telegram)
            tg_action_row = QHBoxLayout()
            self.btn_telegram_test = QPushButton("📨  Tesztüzenet")
            self.btn_telegram_test.setObjectName("telegram_btn")
            self.btn_telegram_test.clicked.connect(self.send_telegram_test)
            tg_action_row.addWidget(self.btn_telegram_test)
            self.btn_telegram_report = QPushButton("📊  Riport küldése")
            self.btn_telegram_report.setObjectName("telegram_btn")
            self.btn_telegram_report.clicked.connect(self.send_telegram_full_report)
            tg_action_row.addWidget(self.btn_telegram_report)
            lay_tg.addLayout(tg_action_row)
            self.telegram_status = QLabel("📵  Telegram: kikapcsolva")
            self.telegram_status.setObjectName("status_label")
            lay_tg.addWidget(self.telegram_status)
            self.telegram_help = QLabel(
                '🔗 Hol találom? '
                '<a style="color:#60a5fa" href="https://t.me/BotFather">BotFather (token)</a> '
                '&nbsp;·&nbsp; '
                '<a style="color:#60a5fa" href="https://t.me/userinfobot">Chat ID (userinfobot)</a>'
            )
            self.telegram_help.setObjectName("status_label")
            self.telegram_help.setTextFormat(Qt.TextFormat.RichText)
            self.telegram_help.setOpenExternalLinks(True)
            self.telegram_help.setToolTip("Megnyitás a böngészőben")
            lay_tg.addWidget(self.telegram_help)
            settings_layout.addWidget(grp_tg)

            # ── 4b. Discord ──
            grp_dc, lay_dc = make_group("💬  Discord")
            self.btn_discord = QPushButton("⚙️  Beállítás (webhook URL)")
            self.btn_discord.setObjectName("discord_btn")
            self.btn_discord.clicked.connect(self.configure_discord)
            lay_dc.addWidget(self.btn_discord)
            dc_action_row = QHBoxLayout()
            self.btn_discord_test = QPushButton("📨  Tesztüzenet")
            self.btn_discord_test.setObjectName("discord_btn")
            self.btn_discord_test.clicked.connect(self.send_discord_test)
            dc_action_row.addWidget(self.btn_discord_test)
            self.btn_discord_report = QPushButton("📊  Riport küldése")
            self.btn_discord_report.setObjectName("discord_btn")
            self.btn_discord_report.clicked.connect(self.send_discord_full_report)
            dc_action_row.addWidget(self.btn_discord_report)
            lay_dc.addLayout(dc_action_row)
            self.discord_status = QLabel("📵  Discord: kikapcsolva")
            self.discord_status.setObjectName("status_label")
            lay_dc.addWidget(self.discord_status)
            self.discord_help = QLabel(
                '🔗 Hol találom? Discord szerver → Csatorna beállításai → '
                '<b>Integrációk → Webhookok → Új webhook → Webhook URL másolása</b>'
            )
            self.discord_help.setObjectName("status_label")
            self.discord_help.setTextFormat(Qt.TextFormat.RichText)
            self.discord_help.setWordWrap(True)
            lay_dc.addWidget(self.discord_help)
            settings_layout.addWidget(grp_dc)

            # ── 5. AI Kommentár ──
            grp_ai, lay_ai = make_group("🤖  AI Kommentár")
            self.ai_checkbox = QCheckBox("Felhő AI magyarázat engedélyezve")
            self.ai_checkbox.setChecked(self.ai_commentary_enabled)
            self.ai_checkbox.toggled.connect(self.toggle_ai_commentary)
            lay_ai.addWidget(self.ai_checkbox)
            self.btn_ai_config = QPushButton("🔑  API kulcs + modell beállítása")
            self.btn_ai_config.clicked.connect(self.configure_ai)
            lay_ai.addWidget(self.btn_ai_config)
            self.ai_status = QLabel("AI: kikapcsolva")
            self.ai_status.setObjectName("status_label")
            lay_ai.addWidget(self.ai_status)
            self.ai_help = QLabel(
                '🔑 API kulcs: '
                '<a style="color:#60a5fa" href="https://console.anthropic.com/settings/keys">Claude (Anthropic)</a> '
                '&nbsp;·&nbsp; '
                '<a style="color:#60a5fa" href="https://platform.openai.com/api-keys">OpenAI</a>'
                '<br>💡 Vagy ingyen: „Claude helyi (előfizetés, CLI)" — ha be vagy lépve a Claude Code-ba.'
            )
            self.ai_help.setObjectName("status_label")
            self.ai_help.setTextFormat(Qt.TextFormat.RichText)
            self.ai_help.setOpenExternalLinks(True)
            self.ai_help.setToolTip("Megnyitás a böngészőben")
            lay_ai.addWidget(self.ai_help)
            self.btn_export_html = QPushButton("📄  HTML riport mentése…")
            self.btn_export_html.clicked.connect(self.export_html_report)
            lay_ai.addWidget(self.btn_export_html)
            settings_layout.addWidget(grp_ai)

            settings_layout.addStretch(1)
            scroll.setWidget(scroll_content)
            settings_outer.addWidget(scroll)
            settings_tab.setLayout(settings_outer)
            self.tabs.addTab(settings_tab, "Beállítások")

            right.addWidget(self.stacked)
            content_row.addLayout(right)
            main_vbox.addLayout(content_row)
            self.setLayout(main_vbox)
            # ---- Restore session state ----
            session = load_session_state()
            if "invest_amount" in session and session["invest_amount"] is not None:
                self.invest_amount = session["invest_amount"]
            if "live_interval_sec" in session:
                self.live_interval_sec = int(session["live_interval_sec"])
            if "alert_threshold_pct" in session:
                self.alert_threshold_pct = float(session["alert_threshold_pct"])
            if "auto_clear_analysis" in session:
                self.auto_clear_analysis = bool(session["auto_clear_analysis"])
            if "sound_alerts_enabled" in session:
                self.sound_alerts_enabled = bool(session["sound_alerts_enabled"])
            if "csv_autosave_enabled" in session:
                self.csv_autosave_enabled = bool(session["csv_autosave_enabled"])
            if "csv_path" in session:
                self.csv_path = str(session["csv_path"])
            self.auto_clear_checkbox.setChecked(self.auto_clear_analysis)
            self.sound_alert_checkbox.setChecked(self.sound_alerts_enabled)
            self.csv_autosave_checkbox.setChecked(self.csv_autosave_enabled)
            if "schedule_enabled" in session:
                self.cb_schedule_analysis.setChecked(bool(session["schedule_enabled"]))
            if "schedule_time" in session:
                parts = str(session["schedule_time"]).split(":")
                if len(parts) == 2:
                    try:
                        self.time_schedule.setTime(QTime(int(parts[0]), int(parts[1])))
                    except (ValueError, TypeError):
                        pass
            if "geometry" in session:
                g = session["geometry"]
                try:
                    self.setGeometry(int(g["x"]), int(g["y"]), int(g["w"]), int(g["h"]))
                except (KeyError, TypeError, ValueError):
                    pass

            # Connect signals
            self.list_widget.itemSelectionChanged.connect(self.update_selected_count)
            self.list_widget.itemSelectionChanged.connect(self.refresh_price_chart)

            # Restore selected assets (block signals to avoid premature chart refresh)
            if "selected_assets" in session and session["selected_assets"]:
                saved_sel = set(session["selected_assets"])
                self.list_widget.blockSignals(True)
                self.list_widget.clearSelection()
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    if item and item.text() in saved_sel:
                        item.setSelected(True)
                self.list_widget.blockSignals(False)

            # Restore active tab
            if "active_tab" in session:
                self.stacked.setCurrentIndex(int(session.get("active_tab", 0)))

            self.update_selected_count()
            self.refresh_telegram_status()
            self.refresh_discord_status()
            self.refresh_ai_status()
            self.refresh_rules_table()
            self.update_summary_panel()
            self.retranslate_ui()

            # F5 shortcut
            sc = QShortcut(QKeySequence("F5"), self)
            sc.activated.connect(self.run_analysis)

            # Fear & Greed and chart: fetch async after window is shown
            self._fng_timer = QTimer(self)
            self._fng_timer.setSingleShot(True)
            self._fng_timer.timeout.connect(self._fetch_fng)
            self._fng_timer.start(800)

            self._startup_chart_timer = QTimer(self)
            self._startup_chart_timer.setSingleShot(True)
            self._startup_chart_timer.timeout.connect(self.refresh_price_chart)
            self._startup_chart_timer.start(400)

            # RGB animation
            self._rgb_hue = 0
            self._rgb_timer = QTimer(self)
            self._rgb_timer.timeout.connect(self._rgb_tick)
            self._rgb_timer.start(35)

            # Particle overlay (behind all widgets)
            self._particle_overlay = ParticleOverlay(self)
            self._particle_overlay.resize(self.size())
            self._particle_overlay.set_dark(self._theme == "dark")
            self._particle_overlay.lower()
            self._particle_overlay.show()

            # Output fade-in effect
            self._out_opacity = QGraphicsOpacityEffect(self.output)
            self._out_opacity.setOpacity(1.0)
            self.output.setGraphicsEffect(self._out_opacity)
            self._out_fade = QPropertyAnimation(self._out_opacity, b"opacity")
            self._out_fade.setDuration(400)
            self._out_fade.setEasingCurve(QEasingCurve.Type.InOutQuad)

        def closeEvent(self, event):
            self._save_session_state()
            super().closeEvent(event)

        def _save_session_state(self):
            data = {
                "invest_amount": self.invest_amount,
                "live_interval_sec": self.live_interval_sec,
                "alert_threshold_pct": self.alert_threshold_pct,
                "auto_clear_analysis": self.auto_clear_analysis,
                "sound_alerts_enabled": self.sound_alerts_enabled,
                "csv_autosave_enabled": self.csv_autosave_enabled,
                "csv_path": self.csv_path,
                "schedule_enabled": self.cb_schedule_analysis.isChecked(),
                "schedule_time": self.time_schedule.time().toString("HH:mm"),
                "selected_assets": [i.text() for i in self.list_widget.selectedItems()],
                "active_tab": self.stacked.currentIndex(),
                "geometry": {
                    "x": self.x(),
                    "y": self.y(),
                    "w": self.width(),
                    "h": self.height(),
                },
            }
            save_session_state(data)

        def resizeEvent(self, e):
            super().resizeEvent(e)
            if hasattr(self, "_particle_overlay"):
                self._particle_overlay.resize(e.size())

        def _fade_in_output(self):
            """Briefly fade-in the analysis output widget after update."""
            if not hasattr(self, "_out_fade"):
                return
            self._out_fade.stop()
            self._out_opacity.setOpacity(0.0)
            self._out_fade.setStartValue(0.0)
            self._out_fade.setEndValue(1.0)
            self._out_fade.start()

        def _rgb_tick(self):
            self._rgb_hue = (self._rgb_hue + 0.8) % 360
            h = self._rgb_hue / 360.0

            def hsv_col(hue_offset, s=0.88, v=1.0):
                r, g, b = colorsys.hsv_to_rgb((h + hue_offset) % 1.0, s, v)
                return QColor(int(r * 255), int(g * 255), int(b * 255))

            c0 = hsv_col(0.00)
            c1 = hsv_col(0.33)
            c2 = hsv_col(0.66)

            stops = [(0.0, c0), (0.5, c1), (1.0, c2)]

            # 1. RGB top bar
            if hasattr(self, "_rgb_bar"):
                self._rgb_bar.set_stops(stops)

            # 2. Gradient title text
            if hasattr(self, "label") and isinstance(self.label, RGBTitleLabel):
                self.label.set_stops(stops)

            # 3. Primary button glow cycles with RGB
            if hasattr(self, "btn") and isinstance(self.btn, AnimatedButton):
                self.btn.set_glow_color(c0.red(), c0.green(), c0.blue())

            # 4. Live button glow cycles with RGB (offset hue)
            if hasattr(self, "btn_live") and isinstance(self.btn_live, AnimatedButton):
                c_live = hsv_col(0.5)
                self.btn_live.set_glow_color(c_live.red(), c_live.green(), c_live.blue())

            # 5. Shimmer bar gradient tint follows hue
            if hasattr(self, "_shimmer") and self._shimmer.isVisible():
                self._shimmer.update()

            # 6. Particle overlay theme sync
            if hasattr(self, "_particle_overlay"):
                self._particle_overlay.set_dark(self._theme == "dark")

        def tr_(self, key, **kwargs):
            return _tr(key, lang=self._lang, **kwargs)

        def on_lang_changed(self, index):
            codes = ["hu", "en", "de"]
            self._lang = codes[index] if index < len(codes) else "hu"
            global _current_lang
            _current_lang = self._lang
            save_app_config(self._lang, self._theme)
            self.retranslate_ui()

        def on_theme_changed(self, index):
            self._theme = "dark" if index == 0 else "light"
            save_app_config(self._lang, self._theme)
            self.apply_theme()
            self.update_summary_panel()

        def retranslate_ui(self):
            t = self.tr_
            self.setWindowTitle(t("window_title"))
            self.label.setText(t("title_label"))
            self.asset_search.setPlaceholderText(t("search_placeholder"))
            self.cb_favorites_only.setText(t("only_favorites"))
            self.btn_fav_toggle.setText(t("fav_toggle"))
            self.cur_label.setText(t("display_label"))
            cur_idx = self.currency_combo.currentIndex()
            self.currency_combo.blockSignals(True)
            self._populate_currency_combo()
            self.currency_combo.setCurrentIndex(cur_idx)
            self.currency_combo.blockSignals(False)
            self.btn_select_all.setText(t("select_all"))
            self.btn_clear.setText(t("clear_output"))
            self.btn_set_amount.setText(t("set_amount"))
            # nav dropdown items
            tab_keys = ["tab_analysis", "tab_chart", "tab_alerts", "tab_portfolio",
                        "tab_correlation", "tab_history", "tab_news", "tab_settings"]
            cur_idx = self.nav_combo.currentIndex()
            self.nav_combo.blockSignals(True)
            self.nav_combo.clear()
            for k in tab_keys:
                self.nav_combo.addItem(t(k))
            self.nav_combo.setCurrentIndex(max(0, cur_idx))
            self.nav_combo.blockSignals(False)
            self.stacked.setCurrentIndex(max(0, cur_idx))
            self.btn_copy_output.setText(t("copy_output"))
            self.output.setPlaceholderText(t("analysis_placeholder"))
            # chart range buttons
            ranges = t("chart_ranges") if isinstance(t("chart_ranges"), list) else ["1d","5d","1mo","3mo"]
            for i, btn in enumerate(self.chart_range_btns):
                if i < len(ranges):
                    btn.setText(ranges[i])
            self.cb_compare_chart.setText(t("compare_chart"))
            self.cb_bb_chart.setText(t("bb_chart"))
            self.cb_pattern_detect.setText(t("pattern_detect"))
            self.chart_subtitle.setText(t("chart_placeholder"))
            self.alert_output.setPlaceholderText(t("alerts_placeholder"))
            self.btn_clear_alerts.setText(t("clear_alerts_btn"))
            self.portfolio_output.setPlaceholderText(t("portfolio_placeholder"))
            self.btn_correlation.setText(t("corr_refresh_btn"))
            self.corr_output.setPlaceholderText(t("corr_placeholder"))
            self.history_filter.setPlaceholderText(t("history_filter_placeholder"))
            self.btn_history_load.setText(t("history_load_btn"))
            hdrs = t("history_headers")
            if isinstance(hdrs, list):
                self.history_table.setHorizontalHeaderLabels(hdrs)
            self.btn_news.setText(t("load_news_btn"))
            self.auto_clear_checkbox.setText(t("auto_clear"))
            self.sound_alert_checkbox.setText(t("sound_alerts"))
            self.csv_autosave_checkbox.setText(t("csv_autosave"))
            self.btn_csv_path.setText(t("csv_btn", name=Path(self.csv_path).name))
            self.btn_alert_threshold.setText(t("alert_threshold_btn", v=self.alert_threshold_pct))
            self.btn_telegram.setText(t("telegram_config"))
            self.btn_telegram_test.setText(t("telegram_test"))
            self.btn_telegram_report.setText(t("telegram_report"))
            self.btn_discord.setText(t("discord_config"))
            self.btn_discord_test.setText(t("discord_test"))
            self.btn_discord_report.setText(t("discord_report"))
            self.ai_checkbox.setText(t("ai_checkbox"))
            self.btn_ai_config.setText(t("ai_config_btn"))
            self.btn_export_html.setText(t("export_html"))
            self.btn_edit_alert_rules.setText(t("alert_rules"))
            self.cb_schedule_analysis.setText(t("sched_label"))
            self.lang_label_widget.setText(t("lang_label"))
            self.theme_label_widget.setText(t("theme_label"))
            # theme combo items
            ti = self.theme_combo.currentIndex()
            self.theme_combo.blockSignals(True)
            self.theme_combo.clear()
            self.theme_combo.addItems([t("theme_dark"), t("theme_light")])
            self.theme_combo.setCurrentIndex(ti)
            self.theme_combo.blockSignals(False)
            self.btn.setText(t("btn_run"))
            if not self.live_timer.isActive():
                self.btn_live.setText(t("btn_live_start"))
                self.live_status.setText(t("live_off"))
            else:
                self.btn_live.setText(t("btn_live_stop"))
                self.live_status.setText(t("live_on", n=self.live_interval_sec))
            self.btn_interval.setText(t("btn_interval", n=self.live_interval_sec))
            self.stats_update.setText(t("last_update_init"))
            self.btn_scanner.setText(t("quick_scanner_btn"))
            self.btn_edit_holdings.setText(t("edit_holdings_btn"))
            self.btn_refresh_portfolio.setText(t("refresh_portfolio_btn"))
            hdrs2 = t("portfolio_headers")
            if isinstance(hdrs2, list):
                self.holdings_table.setHorizontalHeaderLabels(hdrs2)
            self.refresh_telegram_status()
            self.refresh_discord_status()
            self.refresh_ai_status()

        def _fetch_fng(self):
            fng = fetch_fear_greed_index()
            if fng:
                v = fng["value"]
                label = fng["label"]
                self._fng_value = v
                self._fng_label = label
                if v <= 25:
                    emoji, col = "😨", "#ef4444"
                elif v <= 45:
                    emoji, col = "😟", "#f97316"
                elif v <= 55:
                    emoji, col = "😐", "#f59e0b"
                elif v <= 75:
                    emoji, col = "😊", "#84cc16"
                else:
                    emoji, col = "🤑", "#22c55e"
                self.fng_label.setText(f"{emoji} F&G: {v} ({label})")
                self.fng_label.setStyleSheet(f"color: {col};")
                self.update_summary_panel()

        def run_quick_scanner(self):
            """Show a compact HTML table with signal for every selected asset."""
            rate, currency, _ = self.resolve_rate_currency()
            items = self.selected_asset_items()
            dark = self._theme == "dark"
            bg   = "#161b22" if dark else "#ffffff"
            text = "#c9d1d9" if dark else "#24292f"
            hdr  = "#21262d" if dark else "#f6f8fa"
            bord = "#30363d" if dark else "#d0d7de"

            html_parts = [
                f'<div style="font-family:monospace;font-size:12px;color:{text}">',
                f'<table width="100%" cellspacing="0" cellpadding="4" '
                f'style="border-collapse:collapse;border:1px solid {bord}">',
                f'<tr style="background:{hdr}">',
                f'<th style="border:1px solid {bord};text-align:left;padding:5px 8px">Eszköz</th>',
                f'<th style="border:1px solid {bord}">Ár</th>',
                f'<th style="border:1px solid {bord}">Napi %</th>',
                f'<th style="border:1px solid {bord}">RSI</th>',
                f'<th style="border:1px solid {bord}">AI fel%</th>',
                f'<th style="border:1px solid {bord}">Döntés</th>',
                '</tr>',
            ]
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            if hasattr(self, "_shimmer"):
                self._shimmer.start()
            QApplication.processEvents()
            total = len(items)
            for i, (name, sym) in enumerate(items):
                try:
                    r = analyze_asset(name, sym, rate, currency)
                    dec = r["decision"]
                    if "📈" in dec:
                        dec_col, row_bg = "#22c55e", "#0f2d1f" if dark else "#f0fdf4"
                    elif "⚠️" in dec:
                        dec_col, row_bg = "#ef4444", "#2d0f0f" if dark else "#fef2f2"
                    else:
                        dec_col, row_bg = "#f59e0b", "#2d220f" if dark else "#fffbeb"
                    dcp = r.get("day_change_pct")
                    dcp_str = f"{dcp:+.2f}%" if dcp is not None else "–"
                    dcp_col = "#22c55e" if (dcp or 0) >= 0 else "#ef4444"
                    cur = float(r["current"])
                    cur_str = f"{cur:,.0f}" if cur >= 100 else f"{cur:.4f}"
                    html_parts.append(
                        f'<tr style="background:{row_bg}">'
                        f'<td style="border:1px solid {bord};padding:4px 8px"><b>{html.escape(name)}</b></td>'
                        f'<td style="border:1px solid {bord};text-align:right;padding:4px 8px">{cur_str}</td>'
                        f'<td style="border:1px solid {bord};text-align:right;color:{dcp_col};padding:4px 8px">'
                        f'<b>{dcp_str}</b></td>'
                        f'<td style="border:1px solid {bord};text-align:right;padding:4px 8px">'
                        f'{r["rsi"]:.1f}</td>'
                        f'<td style="border:1px solid {bord};text-align:right;padding:4px 8px">'
                        f'{r["next_up_prob"]*100:.1f}%</td>'
                        f'<td style="border:1px solid {bord};text-align:center;color:{dec_col};'
                        f'padding:4px 8px"><b>{html.escape(dec)}</b></td>'
                        f'</tr>'
                    )
                except Exception as e:
                    html_parts.append(
                        f'<tr><td colspan="6" style="border:1px solid {bord};color:#ef4444;padding:4px 8px">'
                        f'{html.escape(name)}: hiba — {html.escape(str(e))}</td></tr>'
                    )
                self.progress_bar.setValue(int((i + 1) / total * 100))
                QApplication.processEvents()
            html_parts.append("</table></div>")
            self.output.setHtml("".join(html_parts))
            self.progress_bar.setVisible(False)
            if hasattr(self, "_shimmer"):
                self._shimmer.stop()
            self._fade_in_output()

        def edit_holdings_dialog(self):
            """Let user enter their holdings (qty per asset)."""
            raw = json.dumps(self.holdings, ensure_ascii=False, indent=2)
            txt, ok = QInputDialog.getMultiLineText(
                self,
                "Portfólió mennyiségek",
                'JSON szótár: {"Bitcoin": 0.5, "Ethereum": 2.0, ...}\n'
                'Csak a pozitív értékek számítanak.',
                raw,
            )
            if not ok:
                return
            try:
                data = json.loads(txt)
                if not isinstance(data, dict):
                    raise ValueError("JSON szótár kell.")
                self.holdings = {k: float(v) for k, v in data.items()
                                 if k in ASSETS and float(v) > 0}
                save_holdings(self.holdings)
                self.log_alert(f"Portfólió mentve: {len(self.holdings)} pozíció.")
                self.refresh_portfolio_live()
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                self.log_alert(f"Portfólió JSON hiba: {e}")

        def refresh_portfolio_live(self):
            """Fetch current prices for held assets and update portfolio table."""
            if not self.holdings:
                self.portfolio_output.setPlainText(
                    "Nincs beállított pozíció. Kattints a 'Mennyiségek szerkesztése' gombra."
                )
                self.holdings_table.setRowCount(0)
                return
            rate, currency, _ = self.resolve_rate_currency()
            rows = []
            total_value = 0.0
            self.holdings_table.setRowCount(0)
            for name, qty in self.holdings.items():
                sym = ASSETS.get(name)
                if not sym:
                    continue
                try:
                    price = get_current_price(sym, rate, currency)
                    value = qty * price
                    total_value += value
                    rows.append((name, qty, price, value, None, "–"))
                except Exception:
                    rows.append((name, qty, None, None, None, "–"))
            self.holdings_table.setRowCount(len(rows))
            for i, (name, qty, price, value, dcp, dec) in enumerate(rows):
                self.holdings_table.setItem(i, 0, QTableWidgetItem(name))
                self.holdings_table.setItem(i, 1, QTableWidgetItem(f"{qty:g}"))
                self.holdings_table.setItem(i, 2, QTableWidgetItem(
                    f"{price:,.2f} {currency}" if price else "–"))
                self.holdings_table.setItem(i, 3, QTableWidgetItem(
                    f"{value:,.2f} {currency}" if value else "–"))
                self.holdings_table.setItem(i, 4, QTableWidgetItem("–"))
                self.holdings_table.setItem(i, 5, QTableWidgetItem(dec))
            self.portfolio_total_label.setText(
                f"Összesen: {total_value:,.0f} {currency}"
            )

        def apply_theme(self):
            if self._theme == "light":
                self.apply_styles_light()
            else:
                self.apply_styles()
            if hasattr(self, "candle_widget"):
                self.candle_widget.set_dark_mode(self._theme == "dark")
            if hasattr(self, "btn"):
                self._primary_shadow = QGraphicsDropShadowEffect(self.btn)
                self._primary_shadow.setBlurRadius(0)
                self._primary_shadow.setOffset(0, 0)
                self._primary_shadow.setColor(QColor(34, 197, 94, 160))
                self.btn.setGraphicsEffect(self._primary_shadow)

        def apply_styles(self):
            self.setStyleSheet("""
/* ── DARK THEME · "Aurum" premium fintech (gold + violet, glass surfaces) ──
   Design-system tokens (ui-ux-pro-max › Fintech/Crypto):
     bg-deep #0f172a · surface #1a2336 · elevated #222b40 · glass-line rgba(255,255,255,.06)
     fg #f8fafc · muted-fg #94a3b8 · border #334155
     primary/gold #f59e0b · secondary #fbbf24 · accent/violet #8b5cf6
     danger #ef4444 · ring #f59e0b (3px focus). No pure black; hairline lit borders. */

/* Base */
QWidget {
    background-color: #0f172a;
    color: #e8edf6;
    font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
}
QWidget:disabled { color: #4a5772; }

/* Adat-widgetek monospace-e — tabuláris számjegyek (ár, %, idő nem ugrál) */
QListWidget, QTextEdit, QTableWidget, QLineEdit, QTimeEdit,
QLabel#stat_chip, QLabel#fng_chip {
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', 'DejaVu Sans Mono', monospace;
}

/* Labels */
QLabel { color: #e8edf6; font-size: 13px; }
QLabel#title_label { font-size: 17px; font-weight: 800; padding: 2px 0; color: #f8fafc; letter-spacing: 0.01em; }
QLabel#stat_chip {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #33290f, stop:1 #2a2411);
    border: 1px solid #7a5f22;
    border-radius: 11px;
    padding: 3px 11px;
    font-size: 11px;
    color: #fcd34d;
    font-weight: 700;
}
QLabel#stat_chip_dim { font-size: 11px; color: #94a3b8; padding: 3px 4px; }
QLabel#status_label  { font-size: 11px; color: #94a3b8; padding: 1px 4px; }
QLabel#fng_chip {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #33290f, stop:1 #2a2411);
    border: 1px solid #7a5f22;
    border-radius: 11px; padding: 3px 11px;
    font-size: 11px; font-weight: 800; color: #fcd34d;
}

/* Scrollable containers */
QScrollArea { border: none; background: transparent; }

/* List + Text — glass surface */
QListWidget, QTextEdit {
    background-color: #1a2336;
    border: 1px solid #2c374d;
    border-top: 1px solid #3a4a66;
    border-radius: 14px;
    padding: 6px;
    color: #e8edf6;
    selection-background-color: #8b5cf6;
    selection-color: #ffffff;
    font-size: 12px;
}
QListWidget::item { padding: 6px 9px; border-radius: 8px; margin: 1px 0; }
QListWidget::item:selected { background: #6d28d9; color: #fff; }
QListWidget::item:hover:!selected { background: #232f47; }

/* Inputs */
QLineEdit, QTimeEdit {
    background: #141d30;
    color: #e8edf6;
    border: 1px solid #2c374d;
    border-radius: 10px;
    padding: 7px 11px;
    font-size: 12px;
    selection-background-color: #8b5cf6;
    selection-color: #ffffff;
}
QLineEdit:focus, QTimeEdit:focus { border: 2px solid #f59e0b; }

/* ComboBox (generic) */
QComboBox {
    background: #141d30;
    color: #e8edf6;
    border: 1px solid #2c374d;
    border-radius: 10px;
    padding: 6px 11px;
}
QComboBox:hover { border-color: #64748b; }
QComboBox:focus { border: 2px solid #f59e0b; }
QComboBox::drop-down { border: none; padding-right: 6px; }
QComboBox QAbstractItemView {
    background: #1c2740;
    border: 1px solid #3b4d6b;
    border-radius: 10px;
    color: #e8edf6;
    padding: 4px;
    selection-background-color: #8b5cf6;
    outline: 0;
}

/* Nav ComboBox — elevated header pill */
QComboBox#nav_combo {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #222b40, stop:1 #172035);
    color: #f8fafc;
    border: 1px solid #3b4d6b;
    border-radius: 12px;
    padding: 8px 36px 8px 16px;
    font-size: 13px;
    font-weight: 800;
    min-height: 34px;
}
QComboBox#nav_combo:hover { border-color: #f59e0b; color: #fff; }
QComboBox#nav_combo::drop-down { border: none; width: 30px; }
QComboBox#nav_combo QAbstractItemView {
    background: #1c2740;
    border: 1px solid #3b4d6b;
    border-radius: 12px;
    color: #e8edf6;
    padding: 5px;
    selection-background-color: #f59e0b;
    selection-color: #0f172a;
    outline: 0;
}
QComboBox#nav_combo QAbstractItemView::item {
    padding: 9px 16px;
    border-radius: 8px;
    min-height: 28px;
}

/* Buttons — subtle glass */
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #232e46, stop:1 #1a2336);
    color: #e8edf6;
    border: 1px solid #33445f;
    border-radius: 10px;
    padding: 7px 15px;
    font-weight: 600;
    font-size: 12px;
}
QPushButton:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #2b3a58, stop:1 #202b42);
    color: #f8fafc;
    border-color: #566b8c;
}
QPushButton:pressed {
    background: #141d30;
    border-color: #f59e0b;
    color: #fcd34d;
}
QPushButton:focus { border: 2px solid #f59e0b; }

QPushButton#primary_btn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #15803d, stop:1 #22c55e);
    color: #fff;
    border: none;
    font-size: 13px;
    padding: 10px 24px;
    border-radius: 12px;
    font-weight: 800;
}
QPushButton#primary_btn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #22c55e, stop:1 #4ade80);
}
QPushButton#primary_btn:pressed { background: #166534; }
QPushButton#primary_btn:focus { border: 2px solid #86efac; }

QPushButton#live_btn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #b45309, stop:1 #f59e0b);
    color: #1a1206;
    border: none;
    font-size: 13px;
    padding: 10px 24px;
    border-radius: 12px;
    font-weight: 800;
}
QPushButton#live_btn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #f59e0b, stop:1 #fbbf24);
}
QPushButton#live_btn:pressed { background: #92400e; color: #fff; }
QPushButton#live_btn:focus { border: 2px solid #fde68a; }

QPushButton#live_btn_active {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #dc2626, stop:1 #ef4444);
    color: #fff;
    border: none;
    font-size: 13px;
    padding: 10px 24px;
    border-radius: 12px;
    font-weight: 800;
}
QPushButton#live_btn_active:hover { background: #ef4444; }

QPushButton#telegram_btn {
    background: #16273f; color: #7cc0ff; border-color: #2563eb;
}
QPushButton#telegram_btn:hover { background: #2563eb; color: #fff; }

QPushButton#discord_btn {
    background: #221f4a; color: #c1c6ff; border-color: #5865f2;
}
QPushButton#discord_btn:hover { background: #5865f2; color: #fff; }

QPushButton#danger_btn {
    background: #241019; color: #f87171; border-color: #991b1b;
}
QPushButton#danger_btn:hover { background: #991b1b; color: #fff; }

/* Category chips */
QPushButton#chip {
    background: #1a2336; color: #94a3b8;
    border: 1px solid #33445f;
    border-radius: 11px; padding: 5px 13px;
    font-size: 11px; font-weight: 600;
}
QPushButton#chip:hover { background: #232f47; color: #cbd5e1; }
QPushButton#chip_active {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #f59e0b, stop:1 #8b5cf6);
    color: #fff;
    border: none;
    border-radius: 11px; padding: 5px 13px;
    font-size: 11px; font-weight: 800;
}

/* CheckBox */
QCheckBox { color: #e8edf6; font-size: 13px; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #33445f;
    border-radius: 5px;
    background: #141d30;
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #f59e0b, stop:1 #8b5cf6);
    border-color: #f59e0b;
}

/* Table */
QTableWidget {
    background: #1a2336;
    gridline-color: #263248;
    border: 1px solid #2c374d;
    border-radius: 14px;
    color: #e8edf6;
    alternate-background-color: #1e2840;
}
QTableWidget::item:selected { background: #33290f; color: #fcd34d; }
QHeaderView::section {
    background: #222b40;
    color: #94a3b8;
    padding: 8px 9px;
    border: none;
    border-right: 1px solid #0f172a;
    border-bottom: 1px solid #0f172a;
    font-weight: 800;
    font-size: 11px;
    letter-spacing: 0.06em;
}

/* Scrollbar */
QScrollBar:vertical {
    background: transparent; width: 7px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #3a4a66; border-radius: 3px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #f59e0b; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent; height: 7px; margin: 0;
}
QScrollBar::handle:horizontal {
    background: #3a4a66; border-radius: 3px; min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #f59e0b; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* Splitter */
QSplitter::handle { background: #2c374d; }

/* Settings GroupBox — glass card */
QGroupBox#settings_group {
    border: 1px solid #2c374d;
    border-radius: 14px;
    margin-top: 8px;
    padding-top: 8px;
    background: #1a2336;
    font-size: 12px;
    font-weight: 800;
    color: #94a3b8;
}
QGroupBox#settings_group::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px; padding: 0 6px;
    color: #fcd34d;
}

/* Progress bar */
QProgressBar#analysis_progress {
    background: #222b40;
    border: none; border-radius: 3px;
    max-height: 5px; min-height: 5px;
}
QProgressBar#analysis_progress::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #f59e0b, stop:1 #8b5cf6);
    border-radius: 3px;
}

/* Frame separator */
QFrame[frameShape="4"] { color: #2c374d; }
            """)

        def apply_styles_light(self):
            self.setStyleSheet("""
/* ── LIGHT THEME · "Aurum" premium fintech (gold + violet, soft glass) ──
   Tokens: bg #f4f7fc · surface #ffffff · elevated #ffffff · border #e2e8f0
     fg #0f172a · muted-fg #64748b · primary/gold #f59e0b · accent/violet #8b5cf6
     danger #dc2626 · ring #f59e0b (2px focus). Soft shadows via layered borders. */

QWidget {
    background-color: #f4f7fc;
    color: #0f172a;
    font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
}
QWidget:disabled { color: #94a3b8; }

/* Adat-widgetek monospace-e — tabuláris számjegyek */
QListWidget, QTextEdit, QTableWidget, QLineEdit, QTimeEdit,
QLabel#stat_chip, QLabel#fng_chip {
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', 'DejaVu Sans Mono', monospace;
}

QLabel { color: #0f172a; font-size: 13px; }
QLabel#title_label { font-size: 17px; font-weight: 800; padding: 2px 0; color: #0f172a; letter-spacing: 0.01em; }
QLabel#stat_chip {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #fff9ec, stop:1 #fef6e7);
    border: 1px solid #f0cd7a;
    border-radius: 11px; padding: 3px 11px;
    font-size: 11px; color: #b45309; font-weight: 700;
}
QLabel#stat_chip_dim { font-size: 11px; color: #64748b; padding: 3px 4px; }
QLabel#status_label  { font-size: 11px; color: #64748b; padding: 1px 4px; }
QLabel#fng_chip {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #fff9ec, stop:1 #fef6e7);
    border: 1px solid #f0cd7a;
    border-radius: 11px; padding: 3px 11px;
    font-size: 11px; font-weight: 800; color: #b45309;
}

QScrollArea { border: none; background: transparent; }

QListWidget, QTextEdit {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 6px;
    color: #0f172a;
    selection-background-color: #8b5cf6;
    selection-color: #ffffff;
    font-size: 12px;
}
QListWidget::item { padding: 6px 9px; border-radius: 8px; margin: 1px 0; }
QListWidget::item:selected { background: #7c3aed; color: #fff; }
QListWidget::item:hover:!selected { background: #eef2f9; }

QLineEdit, QTimeEdit {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #d5deea;
    border-radius: 10px;
    padding: 7px 11px;
    font-size: 12px;
    selection-background-color: #8b5cf6;
    selection-color: #ffffff;
}
QLineEdit:focus, QTimeEdit:focus { border: 2px solid #f59e0b; }

QComboBox {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #d5deea;
    border-radius: 10px;
    padding: 6px 11px;
}
QComboBox:hover { border-color: #b0bccd; }
QComboBox:focus { border: 2px solid #f59e0b; }
QComboBox::drop-down { border: none; padding-right: 6px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    color: #0f172a;
    padding: 4px;
    selection-background-color: #8b5cf6;
    selection-color: #ffffff;
    outline: 0;
}

QComboBox#nav_combo {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #d5deea;
    border-radius: 12px;
    padding: 8px 36px 8px 16px;
    font-size: 13px; font-weight: 800;
    min-height: 34px;
}
QComboBox#nav_combo:hover { border-color: #f59e0b; }
QComboBox#nav_combo::drop-down { border: none; width: 30px; }
QComboBox#nav_combo QAbstractItemView {
    background: #ffffff; border: 1px solid #e2e8f0;
    border-radius: 12px; color: #0f172a; padding: 5px;
    selection-background-color: #f59e0b; selection-color: #ffffff; outline: 0;
}
QComboBox#nav_combo QAbstractItemView::item {
    padding: 9px 16px; border-radius: 8px; min-height: 28px;
}

QPushButton {
    background: #ffffff;
    color: #334155;
    border: 1px solid #d5deea;
    border-radius: 10px;
    padding: 7px 15px;
    font-weight: 600; font-size: 12px;
}
QPushButton:hover { background: #eef2f9; border-color: #cbaf6a; color: #0f172a; }
QPushButton:pressed { background: #e2e8f0; border-color: #f59e0b; color: #b45309; }
QPushButton:focus { border: 2px solid #f59e0b; }

QPushButton#primary_btn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #15803d, stop:1 #22c55e);
    color: #fff; border: none;
    font-size: 13px; padding: 10px 24px;
    border-radius: 12px; font-weight: 800;
}
QPushButton#primary_btn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #22c55e, stop:1 #4ade80);
}
QPushButton#primary_btn:pressed { background: #166534; }
QPushButton#primary_btn:focus { border: 2px solid #16a34a; }

QPushButton#live_btn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #d97706, stop:1 #f59e0b);
    color: #ffffff; border: none;
    font-size: 13px; padding: 10px 24px;
    border-radius: 12px; font-weight: 800;
}
QPushButton#live_btn:hover { background: #f59e0b; }
QPushButton#live_btn:pressed { background: #b45309; }
QPushButton#live_btn:focus { border: 2px solid #d97706; }

QPushButton#live_btn_active {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #dc2626, stop:1 #ef4444);
    color: #fff; border: none;
    font-size: 13px; padding: 10px 24px;
    border-radius: 12px; font-weight: 800;
}
QPushButton#live_btn_active:hover { background: #ef4444; }

QPushButton#telegram_btn { background: #eff6ff; color: #2563eb; border-color: #bfdbfe; }
QPushButton#telegram_btn:hover { background: #2563eb; color: #fff; }

QPushButton#discord_btn { background: #eef0ff; color: #4752c4; border-color: #c7ccff; }
QPushButton#discord_btn:hover { background: #5865f2; color: #fff; }

QPushButton#danger_btn { background: #fef2f2; color: #dc2626; border-color: #fca5a5; }
QPushButton#danger_btn:hover { background: #dc2626; color: #fff; }

QPushButton#chip {
    background: #eef2f9; color: #64748b;
    border: 1px solid #e2e8f0;
    border-radius: 11px; padding: 5px 13px;
    font-size: 11px; font-weight: 600;
}
QPushButton#chip:hover { background: #e2e8f0; color: #0f172a; }
QPushButton#chip_active {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #f59e0b, stop:1 #8b5cf6);
    color: #fff; border: none;
    border-radius: 11px; padding: 5px 13px;
    font-size: 11px; font-weight: 800;
}

QCheckBox { color: #0f172a; font-size: 13px; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #cbd5e1;
    border-radius: 5px; background: #fff;
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #f59e0b, stop:1 #8b5cf6);
    border-color: #f59e0b;
}

QTableWidget {
    background: #ffffff; gridline-color: #eef2f7;
    border: 1px solid #e2e8f0; border-radius: 14px;
    color: #0f172a; alternate-background-color: #f8fafc;
}
QTableWidget::item:selected { background: #fef6e7; color: #b45309; }
QHeaderView::section {
    background: #f4f7fc; color: #64748b;
    padding: 8px 9px; border: none;
    border-right: 1px solid #eef2f7;
    border-bottom: 1px solid #e2e8f0;
    font-weight: 800; font-size: 11px;
    letter-spacing: 0.06em;
}

QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 3px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #f59e0b; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 7px; margin: 0; }
QScrollBar::handle:horizontal { background: #cbd5e1; border-radius: 3px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: #f59e0b; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QSplitter::handle { background: #e2e8f0; }

QGroupBox#settings_group {
    border: 1px solid #e2e8f0;
    border-radius: 14px; margin-top: 8px; padding-top: 8px;
    background: #ffffff; font-size: 12px; font-weight: 800; color: #64748b;
}
QGroupBox#settings_group::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 14px; padding: 0 6px; color: #b45309;
}

QProgressBar#analysis_progress {
    background: #e2e8f0; border: none; border-radius: 3px;
    max-height: 5px; min-height: 5px;
}
QProgressBar#analysis_progress::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #f59e0b, stop:1 #8b5cf6);
    border-radius: 3px;
}

QFrame[frameShape="4"] { color: #e2e8f0; }
            """)

        def _populate_currency_combo(self):
            """Feltölti a megjelenítési-valuta combót: Auto(HUF), USD, majd az
            EXTRA_DISPLAY_CURRENCIES. A valuta kódját itemData-ban tároljuk."""
            self.currency_combo.clear()
            self.currency_combo.addItem(self.tr_("currency_auto"), "AUTO")
            self.currency_combo.addItem(self.tr_("currency_usd"), "USD")
            for code, sym in EXTRA_DISPLAY_CURRENCIES:
                self.currency_combo.addItem(f"{code} ({sym})", code)

        def resolve_rate_currency(self):
            idx = self.currency_combo.currentIndex()
            code = self.currency_combo.itemData(idx)
            if code in (None, "AUTO"):
                return get_effective_rate()  # HUF-auto (hibánál USD-re esik vissza)
            if code == "USD":
                return 1.0, "USD", "Kézi USD megjelenítés"
            return get_effective_rate(code)

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
                self.refresh_rules_table()
                self.log_alert("Riasztási szabályok elmentve.")
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                self.log_alert(f"Szabály JSON hiba: {e}")

        def refresh_rules_table(self):
            """A vizuális szabálytábla feltöltése a self.custom_rules listából."""
            if not hasattr(self, "rules_table"):
                return
            cond_map = {k: lbl for lbl, k in self._rule_conditions}
            self.rules_table.setRowCount(len(self.custom_rules))
            for i, rule in enumerate(self.custom_rules):
                asset = str(rule.get("asset", "*"))
                asset_disp = "* (összes)" if asset == "*" else asset
                cond = cond_map.get(str(rule.get("rule", "")), str(rule.get("rule", "")))
                val = rule.get("value", "")
                self.rules_table.setItem(i, 0, QTableWidgetItem(asset_disp))
                self.rules_table.setItem(i, 1, QTableWidgetItem(cond))
                self.rules_table.setItem(i, 2, QTableWidgetItem(str(val)))

        def add_alert_rule_from_form(self):
            asset_txt = self.rule_asset_combo.currentText()
            asset = "*" if asset_txt.startswith("*") else asset_txt
            cond_key = self._rule_conditions[self.rule_cond_combo.currentIndex()][1]
            raw = self.rule_value_edit.text().strip().replace(",", ".")
            try:
                value = float(raw)
            except ValueError:
                self.log_alert("❌ Érvénytelen érték a riasztási szabályhoz.")
                return
            self.custom_rules.append({"asset": asset, "rule": cond_key, "value": value})
            save_custom_alert_rules(self.custom_rules)
            self.refresh_rules_table()
            self.rule_value_edit.clear()
            self.log_alert(f"✅ Riasztási szabály hozzáadva: {asset} {cond_key} {value}")

        def remove_selected_rule(self):
            rows = sorted({i.row() for i in self.rules_table.selectedItems()}, reverse=True)
            if not rows:
                self.log_alert("Jelölj ki egy szabályt a törléshez.")
                return
            for r in rows:
                if 0 <= r < len(self.custom_rules):
                    del self.custom_rules[r]
            save_custom_alert_rules(self.custom_rules)
            self.refresh_rules_table()
            self.log_alert(f"🗑 {len(rows)} szabály törölve.")

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

        def export_analysis_csv(self):
            """Az utolsó elemzés összes eredményének exportja egy CSV fájlba."""
            if not self._last_results:
                self.log_alert("Nincs mit exportálni — futtass előbb elemzést.")
                return
            _, currency, _ = self.resolve_rate_currency()
            path, _sel = QFileDialog.getSaveFileName(
                self,
                "Elemzés CSV export",
                str(Path.home() / "ai_tracker_elemzes.csv"),
                "CSV (*.csv)",
            )
            if not path:
                return
            now_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
            fields = [
                "timestamp", "asset", "symbol", "currency", "current", "future",
                "day_change_pct", "rsi", "next_up_prob", "accuracy", "decision",
                "action", "side", "confidence", "stop", "take_profit",
                "macd_hist", "realized_vol_annual_pct", "max_drawdown_pct",
                "deploy_amount", "deploy_frac",
            ]
            try:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fields)
                    writer.writeheader()
                    for r in self._last_results:
                        rec = r.get("recommendation") or {}
                        met = r.get("metrics") or {}
                        inv = r.get("investment") or {}
                        writer.writerow({
                            "timestamp": now_text,
                            "asset": r.get("name", ""),
                            "symbol": r.get("symbol", ""),
                            "currency": currency,
                            "current": r.get("current", ""),
                            "future": r.get("future", ""),
                            "day_change_pct": r.get("day_change_pct", ""),
                            "rsi": r.get("rsi", ""),
                            "next_up_prob": r.get("next_up_prob", ""),
                            "accuracy": r.get("accuracy", ""),
                            "decision": r.get("decision", ""),
                            "action": rec.get("action", ""),
                            "side": rec.get("side", ""),
                            "confidence": rec.get("confidence", ""),
                            "stop": rec.get("stop", ""),
                            "take_profit": rec.get("take_profit", ""),
                            "macd_hist": met.get("macd_hist", ""),
                            "realized_vol_annual_pct": met.get("realized_vol_annual_pct", ""),
                            "max_drawdown_pct": met.get("max_drawdown_pct", ""),
                            "deploy_amount": inv.get("deploy_amount", ""),
                            "deploy_frac": inv.get("deploy_frac", ""),
                        })
                self.log_alert(f"✅ CSV exportálva: {path} ({len(self._last_results)} sor)")
            except OSError as e:
                self.log_alert(f"❌ CSV exportálási hiba: {e}")

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

        def set_category_filter(self, cat):
            self._active_category = cat
            for c, btn in self._category_btns.items():
                btn.setChecked(c == cat)
                btn.setObjectName("chip_active" if c == cat else "chip")
                btn.setStyle(btn.style())
            self.filter_asset_list(self.asset_search.text())

        def filter_asset_list(self, text):
            needle = (text or "").strip().lower()
            selected_names = {i.text() for i in self.list_widget.selectedItems()}
            cat_names = set(ASSET_CATEGORIES.get(self._active_category, list(ASSETS.keys())))
            self.list_widget.clear()
            for name in ASSETS:
                if name not in cat_names:
                    continue
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

                closes_disp = np.array([c[4] for c in candles], dtype=float)

                # Bollinger-sávok overlay (valódi rajzolás a gyertyadiagramon)
                bb_bands = None
                bb_note = ""
                if self.cb_bb_chart.isChecked() and len(candles) >= 21:
                    up, md, lo = rolling_bollinger(closes_disp, 20, 2.0)
                    bb_bands = (up, md, lo)
                    bb_note = (
                        f" | BB(20,2σ): fel {up[-1]:,.2f}  közép {md[-1]:,.2f}  al {lo[-1]:,.2f} {currency}"
                    )

                # Indikátor alpanel (RSI / MACD)
                indicator = None
                ind_idx = self.indicator_combo.currentIndex() if hasattr(self, "indicator_combo") else 0
                if ind_idx == 1 and len(candles) >= 16:
                    indicator = {"type": "rsi", "values": rolling_rsi(closes_disp, 14)}
                elif ind_idx == 2 and len(candles) >= 35:
                    line, sig, hist = rolling_macd(closes_disp)
                    indicator = {"type": "macd", "line": line, "signal": sig, "hist": hist}

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
                    currency=currency, x_labels=x_labels,
                    bb_bands=bb_bands, indicator=indicator,
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
            if hasattr(self, "summary_panel"):
                self.update_summary_panel()

        def update_summary_panel(self):
            """A bal panel alján lévő áttekintő összegzés frissítése."""
            if not hasattr(self, "summary_panel"):
                return
            dark = self._theme == "dark"
            txt_col = "#cbd5e1" if dark else "#1e293b"
            dim = "#64748b" if dark else "#94a3b8"
            border = "#1e293b" if dark else "#e2e8f0"
            bg = "#111827" if dark else "#ffffff"

            sel = len(self.list_widget.selectedItems()) or len(ASSETS)
            rows = [f"<b style='font-size:12px'>📊 Áttekintés</b>",
                    f"<span style='color:{dim}'>Kiválasztva:</span> <b>{sel}</b> eszköz"]

            if self._fng_value is not None:
                rows.append(
                    f"<span style='color:{dim}'>Fear &amp; Greed:</span> "
                    f"<b>{self._fng_value}</b> <span style='color:{dim}'>({html.escape(self._fng_label)})</span>"
                )
            if self.holdings:
                rows.append(f"<span style='color:{dim}'>Portfólió:</span> <b>{len(self.holdings)}</b> pozíció")

            res = [r for r in self._last_results if r.get("day_change_pct") is not None]
            if res:
                ordered = sorted(res, key=lambda r: r["day_change_pct"], reverse=True)
                top = ordered[0]
                rows.append(
                    f"<span style='color:{dim}'>🔼 Top:</span> {html.escape(top['name'])} "
                    f"<b style='color:#22c55e'>{top['day_change_pct']:+.2f}%</b>"
                )
                if len(ordered) > 1:
                    bot = ordered[-1]
                    rows.append(
                        f"<span style='color:{dim}'>🔽 Alja:</span> {html.escape(bot['name'])} "
                        f"<b style='color:#ef4444'>{bot['day_change_pct']:+.2f}%</b>"
                    )
            if self._last_results:
                buy = sum(1 for r in self._last_results if "📈" in r["decision"])
                sell = sum(1 for r in self._last_results if "⚠️" in r["decision"])
                wait = max(0, len(self._last_results) - buy - sell)
                rows.append(
                    f"<span style='color:{dim}'>Jelzések:</span> "
                    f"<b style='color:#22c55e'>{buy}</b> / "
                    f"<b style='color:#ef4444'>{sell}</b> / "
                    f"<b style='color:#f59e0b'>{wait}</b>"
                )

            body = "<br>".join(rows)
            self.summary_panel.setText(
                f"<div style='border:1px solid {border};background:{bg};border-radius:10px;"
                f"padding:8px 10px;font-size:11px;color:{txt_col};line-height:1.6'>{body}</div>"
            )

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
            if self.ai_provider == "claude_cli":
                provider = "Claude (előfizetés)"
                model_name = self.claude_cli_model or "alap"
                ready = bool(shutil.which("claude"))
            elif self.ai_provider == "claude":
                provider = "Claude API"
                model_name = self.claude_model
                ready = bool(self.claude_api_key)
            elif self.ai_provider == "nvidia":
                provider = "NVIDIA"
                model_name = self.nvidia_model
                ready = bool(self.nvidia_api_key)
            else:
                provider = "OpenAI"
                model_name = self.ai_model
                ready = bool(self.ai_api_key)
            if self.ai_commentary_enabled and ready:
                self.ai_status.setText(self.tr_("ai_active", provider=provider, model=model_name))
            elif ready:
                self.ai_status.setText(self.tr_("ai_key_set", provider=provider, model=model_name))
            else:
                self.ai_status.setText(self.tr_("ai_off"))

        def configure_ai(self):
            providers = [
                "OpenAI (GPT) – API kulcs, fizetős",
                "Claude API (Anthropic) – API kulcs, fizetős",
                "Claude helyi (előfizetés, claude CLI) – ingyenes, ha be vagy lépve",
                "NVIDIA (build.nvidia.com) – API kulcs, ingyenes kvótával",
            ]
            cur = {"openai": 0, "claude": 1, "claude_cli": 2, "nvidia": 3}.get(self.ai_provider, 0)
            prov, ok = QInputDialog.getItem(
                self, "AI szolgáltató",
                "Válaszd ki, melyik AI adja a kommentárt:",
                providers, cur, False,
            )
            if not ok:
                return
            if prov.startswith("Claude helyi"):
                self.ai_provider = "claude_cli"
                if not shutil.which("claude"):
                    self.log_alert("⚠️ A 'claude' parancs nem található — telepítsd a Claude Code-ot.")
                model, ok2 = QInputDialog.getText(
                    self, "Claude modell (helyi CLI)",
                    "Modell (üresen hagyva a Claude Code alapját használja,\n"
                    "pl.: sonnet, opus, haiku):",
                    text=self.claude_cli_model,
                )
                if not ok2:
                    return
                self.claude_cli_model = model.strip()
                self.log_alert(
                    f"AI beállítva: Claude helyi CLI / "
                    f"{self.claude_cli_model or 'alap modell'} (előfizetés)"
                )
                self.refresh_ai_status()
                return
            if prov.startswith("NVIDIA"):
                self.ai_provider = "nvidia"
                key, ok1 = QInputDialog.getText(
                    self, "NVIDIA API kulcs",
                    "NVIDIA API key (nvapi-…):\n"
                    "Kulcs igénylése: https://build.nvidia.com/\n"
                    "(Jelentkezz be → válassz modellt → Get API Key)",
                    text=self.nvidia_api_key,
                )
                if not ok1:
                    return
                model, ok2 = QInputDialog.getText(
                    self, "NVIDIA modell",
                    "Modell azonosító:\n"
                    "Elérhető modellek: https://build.nvidia.com/models\n"
                    f"(alap: {NVIDIA_MODEL_DEFAULT})",
                    text=self.nvidia_model,
                )
                if not ok2:
                    return
                self.nvidia_api_key = key.strip()
                self.nvidia_model = model.strip() if model.strip() else NVIDIA_MODEL_DEFAULT
                if self.nvidia_api_key:
                    self.log_alert(f"AI beállítva: NVIDIA / {self.nvidia_model}")
                self.refresh_ai_status()
                return
            if prov.startswith("Claude API"):
                self.ai_provider = "claude"
                key, ok1 = QInputDialog.getText(
                    self, "Claude API kulcs",
                    "Anthropic API key (sk-ant-…):\n"
                    "Kulcs igénylése: https://console.anthropic.com/settings/keys\n"
                    "(Jelentkezz be → API Keys → Create Key)",
                    text=self.claude_api_key,
                )
                if not ok1:
                    return
                model, ok2 = QInputDialog.getText(
                    self, "Claude modell",
                    "Modell azonosító:\n"
                    "Elérhető modellek: https://docs.anthropic.com/en/docs/about-claude/models\n"
                    f"(alap: {ANTHROPIC_MODEL_DEFAULT})",
                    text=self.claude_model,
                )
                if not ok2:
                    return
                self.claude_api_key = key.strip()
                self.claude_model = model.strip() if model.strip() else ANTHROPIC_MODEL_DEFAULT
                if self.claude_api_key:
                    self.log_alert(f"AI beállítva: Claude / {self.claude_model}")
            else:
                self.ai_provider = "openai"
                key, ok1 = QInputDialog.getText(
                    self, "OpenAI API kulcs",
                    "OpenAI API key (sk-…):\n"
                    "Kulcs igénylése: https://platform.openai.com/api-keys\n"
                    "(Jelentkezz be → Create new secret key)",
                    text=self.ai_api_key,
                )
                if not ok1:
                    return
                model, ok2 = QInputDialog.getText(
                    self, "OpenAI modell",
                    "Modell azonosító:\n"
                    "Elérhető modellek: https://platform.openai.com/docs/models\n"
                    f"(alap: {OPENAI_MODEL_DEFAULT})",
                    text=self.ai_model,
                )
                if not ok2:
                    return
                self.ai_api_key = key.strip()
                self.ai_model = model.strip() if model.strip() else OPENAI_MODEL_DEFAULT
                if self.ai_api_key:
                    self.log_alert(f"AI beállítva: OpenAI / {self.ai_model}")
            self.refresh_ai_status()

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
                self.telegram_status.setText(self.tr_("telegram_active", id=short_id))
            elif self.telegram_bot_token or self.telegram_chat_id:
                self.telegram_status.setText(self.tr_("telegram_partial"))
            else:
                self.telegram_status.setText(self.tr_("telegram_off"))

        def configure_telegram(self):
            token, ok_token = QInputDialog.getText(
                self,
                "Telegram bot token",
                "Bot token (BotFather által adott):\n"
                "1) Nyisd meg Telegramban: https://t.me/BotFather\n"
                "2) /newbot → adj nevet → másold ki a tokent (pl. 123456:ABC-DEF…)",
                text=self.telegram_bot_token,
            )
            if not ok_token:
                return
            chat_id, ok_chat = QInputDialog.getText(
                self,
                "Telegram chat ID",
                "Chat ID (numerikus vagy @csatornanév):\n"
                "Numerikus ID-hez: írj a botodnak egy üzenetet, majd nyisd meg:\n"
                "https://api.telegram.org/bot<TOKEN>/getUpdates — a chat.id mező az.\n"
                "Vagy kérdezd meg: https://t.me/userinfobot",
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

        # ── Discord (webhook) ──────────────────────────────────────────────
        def refresh_discord_status(self):
            if self.discord_enabled and self.discord_webhook_url:
                self.discord_status.setText(self.tr_("discord_active"))
            else:
                self.discord_status.setText(self.tr_("discord_off"))

        def configure_discord(self):
            url, ok = QInputDialog.getText(
                self,
                "Discord webhook URL",
                "Webhook URL:\n"
                "Discord szerver → jobb klikk a csatornán → Csatorna szerkesztése →\n"
                "Integrációk → Webhookok → Új webhook → Webhook URL másolása\n"
                "(pl. https://discord.com/api/webhooks/123…/abc…)",
                text=self.discord_webhook_url,
            )
            if not ok:
                return
            self.discord_webhook_url = url.strip()
            self.discord_enabled = bool(self.discord_webhook_url)
            # Mentés lemezre, hogy újraindítás után is megmaradjon
            save_discord_config(self.discord_webhook_url)
            self.refresh_discord_status()
            if self.discord_enabled:
                ok, err = send_discord_message(
                    self.discord_webhook_url,
                    embeds=[{
                        "title": "🤖 AI Eszközelemző Pro",
                        "description": "✅ Discord kapcsolat aktív és működik!",
                        "color": DISCORD_COLOR_INFO,
                    }],
                )
                if ok:
                    self.log_alert("✅ Discord tesztüzenet elküldve.")
                else:
                    self.log_alert(f"❌ Discord hiba: {err}")

        def send_discord_test(self):
            """Send a standalone test message to Discord."""
            if not self.discord_enabled:
                self.log_alert("❌ Discord nincs beállítva. Először konfiguráld.")
                return
            ok, err = send_discord_message(
                self.discord_webhook_url,
                embeds=[{
                    "title": "🤖 AI Eszközelemző Pro – Tesztüzenet",
                    "description": (
                        f"🕐 {QDateTime.currentDateTime().toString('yyyy-MM-dd HH:mm:ss')}\n"
                        "✅ Kapcsolat rendben."
                    ),
                    "color": DISCORD_COLOR_INFO,
                }],
            )
            if ok:
                self.log_alert("✅ Discord tesztüzenet elküldve.")
            else:
                self.log_alert(f"❌ Discord hiba: {err}")

        def send_discord_full_report(self):
            """Send the last analysis results to Discord as formatted embeds."""
            if not self.discord_enabled:
                self.log_alert("❌ Discord nincs beállítva. Először konfiguráld.")
                return
            if not self._last_results:
                self.log_alert("❌ Nincs elemzési eredmény. Futtass elemzést előbb.")
                return
            _, currency, _ = self.resolve_rate_currency()
            header = (
                "📊 **AI Eszközelemző Pro – Elemzési Riport**\n"
                f"🕐 {QDateTime.currentDateTime().toString('yyyy-MM-dd HH:mm:ss')}\n"
                f"💱 Deviza: **{currency}**  ·  📋 Eszközök: **{len(self._last_results)}**"
            )
            ok, err = send_discord_message(self.discord_webhook_url, content=header)
            if not ok:
                self.log_alert(f"❌ Discord fejléc hiba: {err}")
                return
            sent, failed = 0, 0
            # Discord max. 10 embed / üzenet → kötegelve küldjük
            embeds = [format_discord_result_embed(r, currency) for r in self._last_results]
            for i in range(0, len(embeds), 10):
                batch = embeds[i:i + 10]
                ok, err = send_discord_message(self.discord_webhook_url, embeds=batch)
                if ok:
                    sent += len(batch)
                else:
                    failed += len(batch)
                    self.log_alert(f"❌ Discord küldési hiba: {err}")
                time.sleep(0.5)  # Discord rate limit
            self.log_alert(f"📊 Discord riport elküldve: {sent} sikeres, {failed} hibás.")

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
            if self.discord_enabled:
                ok, err = send_discord_message(
                    self.discord_webhook_url,
                    embeds=[format_discord_alert_embed(message)],
                )
                if not ok:
                    self.log_alert(f"❌ Discord küldés sikertelen: {err}")

        def log_alert(self, text):
            now_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
            self.alert_output.append(f"[{now_text}] {text}")

        def update_decision_stats(self, results):
            buy_keywords = {"📈"}
            sell_keywords = {"⚠️"}
            buy = sum(1 for r in results if "📈" in r["decision"])
            sell = sum(1 for r in results if "⚠️" in r["decision"])
            wait = max(0, len(results) - buy - sell)
            self.stats_decisions.setText(
                self.tr_("signals", b=buy, s=sell, w=wait)
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
                self.btn_interval.setText(self.tr_("btn_interval", n=value))
                if self.live_timer.isActive():
                    self.live_timer.start(self.live_interval_sec * 1000)

        def toggle_live_mode(self):
            if self.live_timer.isActive():
                self.live_timer.stop()
                self.btn_live.setText(self.tr_("btn_live_start"))
                self.btn_live.setObjectName("live_btn")
                self.btn_live.setStyle(self.btn_live.style())
                self.live_status.setText(self.tr_("live_off"))
                if hasattr(self, "_pulse_dot"):
                    self._pulse_dot.set_active(False)
                return

            if not self.ensure_invest_amount():
                self.output.append("Élő mód nem indult: nincs befektetési összeg.\n")
                return

            self.run_analysis(prompt_amount=False)
            self.live_timer.start(self.live_interval_sec * 1000)
            self.btn_live.setText(self.tr_("btn_live_stop"))
            self.btn_live.setObjectName("live_btn_active")
            self.btn_live.setStyle(self.btn_live.style())
            self.live_status.setText(self.tr_("live_on", n=self.live_interval_sec))
            if hasattr(self, "_pulse_dot"):
                self._pulse_dot.set_active(True)

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

            # switch to analysis tab so the user sees the output
            self.nav_combo.setCurrentIndex(0)

            manual_usd = self.currency_combo.currentIndex() == 1
            rate, currency, rate_warning = self.resolve_rate_currency()

            if self.invest_amount is None:
                self.invest_amount = 100_000.0

            has_huf = rate_warning is None and currency == "HUF"
            fx_ctx = get_usdhuf_vs_ma20()
            now_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
            self.stats_update.setText(now_text)

            assets_to_run = self.selected_asset_items()
            total = len(assets_to_run)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            if hasattr(self, "_shimmer"):
                self._shimmer.start()
            self.analysis_info_label.setText(f"0 / {total}")

            dark = self._theme == "dark"
            html_parts = []
            results = []
            csv_rows = []
            db_batch = []

            for idx, (name, symbol) in enumerate(assets_to_run):
                try:
                    result = analyze_asset(name, symbol, rate, currency)
                    # inject holding qty if available
                    result["holding_qty"] = self.holdings.get(name, 0)
                    result["investment"] = evaluate_today_investment(
                        self.invest_amount, currency, has_huf, fx_ctx, result,
                    )
                    if self.ai_commentary_enabled:
                        prov = self.ai_provider
                        ai_text, ai_err = None, None
                        if prov == "claude_cli":
                            ai_text, ai_err = get_claude_cli_commentary(
                                result, currency,
                                model=self.claude_cli_model or None,
                            )
                        elif prov == "claude" and self.claude_api_key:
                            ai_text, ai_err = get_ai_commentary(
                                result=result, currency=currency,
                                api_key=None, model=self.ai_model,
                                claude_api_key=self.claude_api_key,
                                claude_model=self.claude_model,
                            )
                        elif prov == "nvidia" and self.nvidia_api_key:
                            ai_text, ai_err = get_nvidia_commentary(
                                result, currency,
                                api_key=self.nvidia_api_key, model=self.nvidia_model,
                            )
                        elif prov == "openai" and self.ai_api_key:
                            ai_text, ai_err = get_ai_commentary(
                                result=result, currency=currency,
                                api_key=self.ai_api_key, model=self.ai_model,
                            )
                        else:
                            ai_err = (
                                f"Nincs beállítva API kulcs a(z) '{prov}' szolgáltatóhoz. "
                                f"Nyisd meg az 'AI szolgáltató' beállítást és add meg a kulcsot."
                            )
                        if ai_text:
                            result["ai_commentary"] = ai_text
                        elif ai_err:
                            self.log_alert(f"AI ({prov}) hiba — {result.get('name')}: {ai_err}")
                    results.append(result)
                    for msg in fire_custom_rules_if_needed(
                        self.custom_rules, result, self._rule_cooldown
                    ):
                        self.log_alert(msg)
                        self.trigger_alert_channels(msg)
                    html_parts.append(format_result_html(result, currency=currency, dark=dark))
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
                    db_batch.append((
                        now_text, name, currency,
                        float(result["current"]), float(result["future"]),
                        str(result["decision"]), float(result["rsi"]),
                        float(result["next_up_prob"]), float(result["accuracy"]),
                        met.get("macd_hist"), met.get("realized_vol_annual_pct"),
                        met.get("max_drawdown_pct"),
                    ))
                    current_price = float(result["current"])
                    prev = self.last_prices_live.get(name)
                    if prev and prev != 0:
                        change_pct = ((current_price / prev) - 1.0) * 100.0
                        if abs(change_pct) >= self.alert_threshold_pct and self.live_timer.isActive():
                            direction = "↑" if change_pct > 0 else "↓"
                            msg = (f"{name}: {direction} {change_pct:+.2f}% | "
                                   f"{prev:,.2f} → {current_price:,.2f} {currency}")
                            self.log_alert(msg)
                            self.trigger_alert_channels(msg)
                    self.last_prices_live[name] = current_price
                except Exception as e:
                    import traceback as _tb
                    err_detail = _tb.format_exc()
                    dim = "#9ca3af" if dark else "#6b7280"
                    html_parts.append(
                        f'<div style="margin:4px 2px;padding:8px 14px;'
                        f'border-left:3px solid #ef4444;color:{dim}">'
                        f'<b style="color:#ef4444">⚠ {html.escape(name)}</b>: '
                        f'{html.escape(str(e))}'
                        f'<br><span style="font-size:10px;color:{dim}">'
                        f'{html.escape(err_detail[:400])}</span></div>'
                    )
                finally:
                    self.progress_bar.setValue(int((idx + 1) / total * 100))
                    self.analysis_info_label.setText(f"{idx + 1} / {total}")
                    QApplication.processEvents()

            # Render all HTML cards at once
            wrapper_bg = "#0d1117" if dark else "#f6f8fa"
            self.output.setHtml(
                f'<div style="background:{wrapper_bg};padding:4px">{"".join(html_parts)}</div>'
            )
            self.progress_bar.setVisible(False)
            if hasattr(self, "_shimmer"):
                self._shimmer.stop()
            self._fade_in_output()
            self.analysis_info_label.setText(f"✓ {len(results)} eszköz")

            if results:
                self._last_results = results
                self.update_decision_stats(results)
                self.update_portfolio_tab(results, currency)
                self.update_summary_panel()
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
        return 11

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
    parser.add_argument(
        "--claude-key",
        type=str,
        default=None,
        help="Anthropic Claude API kulcs az AI kommentárhoz (elsőbbséget élvez az OpenAI előtt).",
    )
    parser.add_argument(
        "--claude-model",
        type=str,
        default=ANTHROPIC_MODEL_DEFAULT,
        help=f"Claude modell azonosító (alap: {ANTHROPIC_MODEL_DEFAULT}).",
    )
    parser.add_argument(
        "--openai-key",
        type=str,
        default=None,
        help="OpenAI API kulcs az AI kommentárhoz.",
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
