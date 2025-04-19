import os

# === Bybit API ===
BYBIT_API_KEY = "tL7vmTEDT5B8mp4Yer"
BYBIT_API_SECRET = "xH5S3U3dkLeQJ739cl9AZ0MMNQkerD53vAXN"
BYBIT_API_URL = "https://api.bybit.com"

# === Telegram Bot ===
TELEGRAM_BOT_TOKEN = "7803544014:AAGLJVwfTg4Ij5lzI8RIVRfrZkKG9uIZnh4"
TELEGRAM_CHAT_ID = "1806610681"

# === Scanning Settings ===
TIMEFRAMES = ['5m', '15m', '1h']
SYMBOL_LIMIT = 500  # Limit if needed

# === Risk Settings ===
DEFAULT_RISK = 0.03
SCALP_RISK = 0.03
SWING_RISK = 0.015
MEME_RISK = 0.02
MAX_DAILY_LOSS = 0.10

# === Trade Settings ===
TP_RATIO_1 = 1.5
TP_RATIO_2 = 2.5
USE_TRAILING_SL = True
TRAIL_SL_OFFSET = 0.3  # 30% behind high


# Leverage
USE_AUTO_LEVERAGE = True
DEFAULT_LEVERAGE = 5
