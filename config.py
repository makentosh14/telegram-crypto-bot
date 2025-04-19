# config.py

BYBIT_API_URL = "https://api.bybit.com"
BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"

TELEGRAM_TOKEN = "7803544014:AAGLJVwfTg4Ij5lzI8RIVRfrZkKG9uIZnh4"
TELEGRAM_CHAT_ID = "1806610681"
ASSISTANT_CHAT_ID = "YOUR_PRIVATE_ASSISTANT_CHANNEL_ID"

API_KEY = "tL7vmTEDT5B8mp4Yer"
API_SECRET = "xH5S3U3dkLeQJ739cl9AZ0MMNQkerD53vAXN"

TIMEFRAMES = ["5m", "15m", "1h"]

MAX_RISK_DEFAULT = 0.03
MAX_RISK_MEME = 0.02
MAX_RISK_SWING = 0.015
MAX_RISK_ALTSEASON = 0.05

DAILY_LOSS_LIMIT = 0.10  # Bot pauses after losing 10% in a day
MAX_CONSECUTIVE_LOSSES = 3

MIN_SCORE_TO_TRADE = 3.5
SPOT_VOLUME_THRESHOLD = 1000000  # For low-cap detection

# For AI memory + sentiment
SIGNAL_HISTORY_FILE = "logs/signal_history.json"
WIN_LOSS_LOG = "logs/trade_results.json"

# Scanner speed
SCAN_INTERVAL_DEFAULT = 180  # 3 minutes
SCAN_INTERVAL_FAST = 60
SCAN_INTERVAL_SUPERFAST = 3

# Trailing Stop
USE_TRAILING_STOP = True
TRAIL_SL_PERCENT = 0.015

# Leverage
USE_AUTO_LEVERAGE = True
DEFAULT_LEVERAGE = 5
