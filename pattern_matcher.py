# pattern_matcher.py

import asyncio
from websocket_candles import live_candles
from pattern_discovery import load_patterns
from score import score_symbol
from telegram_bot import send_telegram_message
from trade_executor import execute_trade_if_valid
from logger import log, write_log
from datetime import datetime

TIMEFRAMES = ['1', '3', '5']
MATCH_KEYS = ["pattern", "volume_spike"]
MATCH_INDICATORS = ["rsi", "macd", "supertrend"]
MIN_MATCH_SCORE = 3  # Require 3/5 matches to trigger

async def pattern_match_scan(symbols):
    patterns = load_patterns()

    for symbol in symbols:
        await asyncio.sleep(1.5)
        if symbol not in live_candles:
            continue

        try:
            candles_by_tf = {
                tf: list(live_candles[symbol][str(tf)]) for tf in TIMEFRAMES
                if len(live_candles[symbol][str(tf)]) >= 30
            }
            if not candles_by_tf:
                continue

            score, tf_scores, trade_type = score_symbol(symbol, candles_by_tf)
            recent_candles = list(live_candles[symbol]['1'][-3:])
            last_pattern = recent_candles[-2:] if len(recent_candles) >= 2 else []
            pattern_type = None
            if last_pattern:
                from pattern_detector import detect_pattern
                pattern_type = detect_pattern(last_pattern)

            volume_now = float(live_candles[symbol]['1'][-1]['volume'])
            avg_volume = sum(float(c['volume']) for c in live_candles[symbol]['1'][-20:]) / 20
            volume_spike = volume_now > avg_volume * 1.5

            matched = []
            for entry in patterns[-100:]:  # Only compare to last 100 patterns for speed
                match_count = 0
                if pattern_type and entry.get("pattern") == pattern_type:
                    match_count += 1
                if entry.get("volume_spike") == volume_spike:
                    match_count += 1

                for ind in MATCH_INDICATORS:
                    if ind in tf_scores and ind in entry.get("context", {}):
                        val_live = tf_scores[ind]
                        val_saved = entry["context"][ind]
                        if abs(val_live - val_saved) <= 1:
                            match_count += 1

                if match_count >= MIN_MATCH_SCORE:
                    matched.append(entry)

            if matched:
                direction = "Long" if tf_scores.get("rsi", 0) > 45 else "Short"
                price = float(live_candles[symbol]['1'][-1]['close'])
                confidence = 90
                leverage = 5
                risk_pct = 9.0  # Fixed 9% risk for pattern match
                trailing_pct = 0.5  # Fixed for now

                sl = price * 0.985 if direction == "Long" else price * 1.015
                tp1 = price * 1.018 if direction == "Long" else price * 0.982

                msg = (
                    f"🧠 <b>Pattern Match Signal</b>\n"
                    f"<b>Symbol:</b> {symbol}\n"
                    f"<b>Entry:</b> {price:.4f} | <b>SL:</b> {sl:.4f} | <b>TP1:</b> {tp1:.4f}\n"
                    f"<b>Risk:</b> 9% | <b>Type:</b> Scalp | <b>Confidence:</b> {confidence}%\n"
                    f"<b>Pattern:</b> {pattern_type or 'Unknown'} | Volume Spike: {volume_spike}\n"
                    f"<i>Matched {len(matched)} past winners</i>"
                )
                await send_telegram_message(msg)

                trade = await execute_trade_if_valid({
                    "symbol": symbol,
                    "price": price,
                    "trade_type": "Scalp",
                    "direction": direction,
                    "score": score,
                    "confidence": confidence,
                    "candles": candles_by_tf
                })

                if trade:
                    log(f"🚀 Pattern-based trade executed for {symbol} | Entry: {price}")
                    write_log(f"AUTO TRADE (pattern match): {symbol} | Entry: {price} | SL: {sl} | TP1: {tp1}")

        except Exception as e:
            log(f"❌ Pattern match failed for {symbol}: {e}")
