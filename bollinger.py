import asyncio
import traceback
from telegram_bot import send_error_to_telegram  # 🚨 Ensure this function exists in telegram_bot.py

def calculate_bollinger_bands(candles, period=20, multiplier=2):
    """
    candles: list of dicts with 'close' prices as strings
    returns: list of dicts with 'middle', 'upper', 'lower' or None if not enough data
    """
    try:
        closes = [float(c['close']) for c in candles]
        bands = []

        for i in range(len(closes)):
            if i + 1 < period:
                bands.append(None)
                continue

            window = closes[i + 1 - period:i + 1]
            sma = sum(window) / period
            variance = sum((price - sma) ** 2 for price in window) / period
            std_dev = variance ** 0.5
            upper = sma + multiplier * std_dev
            lower = sma - multiplier * std_dev

            bands.append({
                'middle': sma,
                'upper': upper,
                'lower': lower
            })

        return bands

    except Exception as e:
        asyncio.create_task(send_error_to_telegram(
            f"❌ <b>Bollinger Bands Error</b>\nError: <code>{str(e)}</code>\n<pre>{traceback.format_exc()}</pre>"
        ))
        return []
