import asyncio
from error_handler import send_error_to_telegram

def calculate_atr(candles, period=10):
    try:
        trs = []
        for i in range(1, len(candles)):
            high = float(candles[i]["high"])
            low = float(candles[i]["low"])
            prev_close = float(candles[i - 1]["close"])
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        return sum(trs[-period:]) / period if len(trs) >= period else 0
    except Exception as e:
        import traceback
        asyncio.create_task(send_error_to_telegram(
            f"❌ <b>ATR Calculation Error</b>\nError: <code>{str(e)}</code>\n<pre>{traceback.format_exc()}</pre>"
        ))
        return 0

def calculate_supertrend_signal(candles, period=10, multiplier=3):
    """
    Returns 'bullish' or 'bearish' if Supertrend crosses in either direction.
    """
    try:
        if len(candles) < period + 1:
            return None

        atr = calculate_atr(candles, period)
        if atr < 1e-8:  # ATR too small to be reliable
            return None

        latest = candles[-1]
        prev = candles[-2]

        avg_price = (float(latest["high"]) + float(latest["low"])) / 2
        upper_band = avg_price + multiplier * atr
        lower_band = avg_price - multiplier * atr

        close = float(latest["close"])
        prev_close = float(prev["close"])

        if close > upper_band and prev_close <= upper_band:
            return "bullish"
        elif close < lower_band and prev_close >= lower_band:
            return "bearish"
        else:
            return None

    except Exception as e:
        import traceback
        asyncio.create_task(send_error_to_telegram(
            f"❌ <b>Supertrend Signal Error</b>\nError: <code>{str(e)}</code>\n<pre>{traceback.format_exc()}</pre>"
        ))
        return None
