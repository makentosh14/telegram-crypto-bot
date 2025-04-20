import os

# === Bybit API ===
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY") or "tL7vmTEDT5B8mp4Yer"
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET") or "xH5S3U3dkLeQJ739cl9AZ0MMNQkerD53vAXN"
BYBIT_API_URL = "https://api.bybit.com"
BASE_URL = "https://api.bybit.com"

# === Telegram ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "7803544014:AAGLJVwfTg4Ij5lzI8RIVRfrZkKG9uIZnh4"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "1806610681"
ASSISTANT_CHAT_ID = "-1000000000000"

# === Bot Behavior Settings ===
DEFAULT_SCAN_INTERVAL = 180  # in seconds
DEFAULT_RISK = 0.03  # 3% default risk
MAX_DAILY_LOSS = 0.1  # 10% max daily drawdown
TRADE_MODE = "auto"  # "signal" or "auto"
USE_SMART_EXIT = True
USE_AUTO_REENTRY = True

# === Timeframes ===
TIMEFRAMES = ["5m", "15m", "1h"]

# === Other Constants ===
BTC_SYMBOL = "BTCUSDT"
ETH_SYMBOL = "ETHUSDT"

# === Strategy Thresholds ===
MIN_SCORE_THRESHOLD = 3.0
HIGH_CONVICTION_SCORE = 4.5

# === Altseason Scan Adaptation ===
ALTSEASON_SCAN_INTERVAL = 120
NORMAL_SCAN_INTERVAL = 180
HIGH_VOL_SCAN_INTERVAL = 60

# === Risk & Strategy Settings ===
DEFAULT_RISK = 0.03
SWING_RISK = 0.015
SCALP_RISK = 0.03
MEME_RISK = 0.02
MAX_DAILY_LOSS = 0.1

# === Auto Risk Adjuster ===
WIN_STREAK_BOOST = 0.005
LOSS_STREAK_REDUCE = 0.01

# === Market Context Thresholds ===
ALTSEASON_VOLUME_SPIKE = 1.5
BTC_DOMINANCE_DROP = 1.0
ETH_BTC_RATIO_MIN = 0.055

# === Watchlist / Filtering ===
MIN_VOLUME_USDT = 500000
TOP_N_CANDIDATES = 5
MAX_SYMBOLS_TO_SCAN = 500  # safety cap

# === Logging / Debug ===
LOG_FILE = "logs/bot_log.txt"
DEBUG = True
