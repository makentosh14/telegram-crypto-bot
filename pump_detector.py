import asyncio
import traceback
from volume import is_volume_spike
from whale_detector import detect_whale_activity
from stealth_detector import detect_slow_breakout
from social_sentiment import check_social_sentiment
from telegram_bot import send_error_to_telegram
from logger import log

async def detect_early_pump(candles_by_tf, symbol):
    results = {
        "volume_spike": False,
        "whale_activity": False,
        "base_breakout": False,
        "social_hype": False,
        "trigger_count": 0
    }

    tf1 = candles_by_tf.get("1", [])
    tf3 = candles_by_tf.get("3", [])

    try:
        if tf1 and is_volume_spike(tf1, multiplier=2.5):
            results["volume_spike"] = True
            results["trigger_count"] += 1
            log(f"⚡ Volume spike detected on {symbol}")
    except Exception as e:
        await send_error_to_telegram(
            f"⚠️ <b>Volume Spike Error</b>\nSymbol: <b>{symbol}</b>\n<code>{traceback.format_exc()}</code>"
        )

    try:
        if tf3 and detect_whale_activity(tf3, threshold_ratio=1.8):
            results["whale_activity"] = True
            results["trigger_count"] += 1
            log(f"🐋 Whale activity detected on {symbol}")
    except Exception as e:
        await send_error_to_telegram(
            f"🐋 <b>Whale Detection Error</b>\nSymbol: <b>{symbol}</b>\n<code>{traceback.format_exc()}</code>"
        )

    try:
        if tf3 and detect_slow_breakout(tf3):
            results["base_breakout"] = True
            results["trigger_count"] += 1
            log(f"📈 Slow breakout detected on {symbol}")
    except Exception as e:
        await send_error_to_telegram(
            f"📈 <b>Slow Breakout Error</b>\nSymbol: <b>{symbol}</b>\n<code>{traceback.format_exc()}</code>"
        )

    try:
        if await check_social_sentiment(symbol):
            results["social_hype"] = True
            results["trigger_count"] += 1
            log(f"📢 Social hype detected on {symbol}")
    except Exception as e:
        await send_error_to_telegram(
            f"📢 <b>Social Sentiment Error</b>\nSymbol: <b>{symbol}</b>\n<code>{traceback.format_exc()}</code>"
        )

    return results
