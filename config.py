import os
from dotenv import load_dotenv

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_API_URL = "https://api.bybit.com"

TELEGRAM_BOT_TOKEN = "7803544014:AAGLJVwfTg4Ij5lzI8RIVRfrZkKG9uIZnh4"
TELEGRAM_CHAT_ID = "1806610681"
TELEGRAM_ASSISTANT_CHAT_ID = "-1000000000000"  # optional

# === TRADING MODE ===
TRADING_MODE = "auto"  # "auto" or "signal"
RISK_SPOT = 0.03
RISK_FUTURES = 0.09    # default 9% per futures trade
DAILY_MAX_LOSS = 0.1   # max daily loss before auto pause (10%)

# === LEVERAGE / MARGIN SETTINGS ===
DEFAULT_LEVERAGE = 5
MARGIN_MODE = "CROSSED"  # or "ISOLATED"

# === CANDLE INTERVAL SETTINGS ===
DEFAULT_INTERVAL = '1'
SUPPORTED_INTERVALS = ['1', '3', '5', '15']

# === SIGNAL THRESHOLDS ===
MIN_SCALP_SCORE = 6
MIN_INTRADAY_SCORE = 7
MIN_SWING_SCORE = 8
ALTSEASON_SCORE_BOOST = 0.5
MEME_SCORE_BOOST = 0.5
ALWAYS_ALLOW_SWING = False  # ❌ Disabled to prevent low-score trades - change back to True if needed

# === MEME / ALTSEASON DETECTION ===
ENABLE_MEME_RADAR = True
ENABLE_ALTS_SCALING = True

# === SCAN SPEED CONTROL ===
BASE_SCAN_INTERVAL = 180  # default: 3 minutes
ALTSEASON_SCAN_INTERVAL = 120
MEME_HYPE_SCAN_INTERVAL = 90

# === MARKET TYPES ===
ENABLE_SPOT = False  # 🔴 Spot trading disabled
ENABLE_FUTURES = True

# === SMART SYSTEMS ===
ENABLE_SMART_EXIT = True
ENABLE_AI_SIGNAL_MEMORY = True
ENABLE_LIQUIDITY_TRAP_FILTER = True
ENABLE_WHALE_WATCH = True
ENABLE_NEWS_REACTION = True
