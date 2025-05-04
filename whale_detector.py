import asyncio
import traceback
from error_handler import send_error_to_telegram

def detect_whale_activity(candles, threshold_ratio=1.8):
    """
    Detects whale activity by comparing recent volume/body size to prior candles.
    Returns True if high volume and big candle body detected.
    """
    try:
        if len(candles) < 6:
            return False

        recent = candles[-3:]
        earlier = candles[-6:-3]

        avg_early_volume = sum(float(c['volume']) for c in earlier) / len(earlier)
        avg_recent_volume = sum(float(c['volume']) for c in recent) / len(recent)

        body_sizes = [abs(float(c['close']) - float(c['open'])) for c in recent]
        avg_body = sum(body_sizes) / len(body_sizes)

        whale_detected = avg_recent_volume > avg_early_volume * threshold_ratio and avg_body > 0.5
        return whale_detected

    except Exception as e:
        asyncio.create_task(send_error_to_telegram(
            f"🐋 <b>Whale Detector Error</b>\nError: <code>{str(e)}</code>\n<pre>{traceback.format_exc()}</pre>"
        ))
        return False
