import asyncio
import traceback
from logger import log
from telegram_bot import send_error_to_telegram  # 🚨 make sure this is implemented

def is_bullish_engulfing(prev, curr):
    return (
        float(prev["close"]) < float(prev["open"]) and
        float(curr["close"]) > float(curr["open"]) and
        float(curr["open"]) < float(prev["close"]) and
        float(curr["close"]) > float(prev["open"])
    )

def is_bearish_engulfing(prev, curr):
    return (
        float(prev["close"]) > float(prev["open"]) and
        float(curr["close"]) < float(curr["open"]) and
        float(curr["open"]) > float(prev["close"]) and
        float(curr["close"]) < float(prev["open"])
    )

def is_hammer(candle):
    high = float(candle["high"])
    low = float(candle["low"])
    open_ = float(candle["open"])
    close = float(candle["close"])
    body = abs(close - open_)
    tail = min(open_, close) - low
    return body < (high - low) * 0.3 and tail > body * 2

def is_inverted_hammer(candle):
    high = float(candle["high"])
    low = float(candle["low"])
    open_ = float(candle["open"])
    close = float(candle["close"])
    body = abs(close - open_)
    wick = high - max(open_, close)
    return body < (high - low) * 0.3 and wick > body * 2

def is_inside_bar(prev, curr):
    return (
        float(curr["high"]) < float(prev["high"]) and
        float(curr["low"]) > float(prev["low"])
    )

def is_morning_star(c1, c2, c3):
    return (
        float(c1["close"]) < float(c1["open"]) and
        abs(float(c2["close"]) - float(c2["open"])) < (float(c1["open"]) - float(c1["close"])) * 0.5 and
        float(c3["close"]) > float(c3["open"]) and
        float(c3["close"]) > float(c1["open"])
    )

def is_evening_star(c1, c2, c3):
    return (
        float(c1["close"]) > float(c1["open"]) and
        abs(float(c2["close"]) - float(c2["open"])) < (float(c1["close"]) - float(c1["open"])) * 0.5 and
        float(c3["close"]) < float(c3["open"]) and
        float(c3["close"]) < float(c1["open"])
    )

def is_doji(candle):
    open_ = float(candle["open"])
    close = float(candle["close"])
    high = float(candle["high"])
    low = float(candle["low"])
    return abs(open_ - close) <= (high - low) * 0.1

def detect_pattern(candles):
    try:
        if len(candles) < 3:
            return None

        c1, c2, c3 = candles[-3], candles[-2], candles[-1]

        if is_morning_star(c1, c2, c3):
            log("🔍 Pattern Detected: morning_star")
            return "morning_star"
        if is_evening_star(c1, c2, c3):
            log("🔍 Pattern Detected: evening_star")
            return "evening_star"
        if is_bullish_engulfing(c2, c3):
            log("🔍 Pattern Detected: bullish_engulfing")
            return "bullish_engulfing"
        if is_bearish_engulfing(c2, c3):
            log("🔍 Pattern Detected: bearish_engulfing")
            return "bearish_engulfing"
        if is_hammer(c3):
            log("🔍 Pattern Detected: hammer")
            return "hammer"
        if is_inverted_hammer(c3):
            log("🔍 Pattern Detected: inverted_hammer")
            return "inverted_hammer"
        if is_inside_bar(c2, c3):
            log("🔍 Pattern Detected: inside_bar")
            return "inside_bar"
        if is_doji(c3):
            log("🔍 Pattern Detected: doji")
            return "doji"

        return None

    except Exception as e:
        asyncio.create_task(send_error_to_telegram(
            f"❌ <b>Pattern Detection Error</b>\nError: <code>{str(e)}</code>\n<pre>{traceback.format_exc()}</pre>"
        ))
        return None
