import asyncio
from websocket_candles import live_candles
from pattern_discovery import load_patterns
from score import score_symbol
from error_handler import send_telegram_message, send_error_to_telegram
from trade_executor import execute_trade_if_valid
from logger import log, write_log
from datetime import datetime
from monitor import track_active_trade
from monitor_report import log_trade_result

TIMEFRAMES = ['1', '3', '5']
MATCH_KEYS = ["pattern", "volume_spike"]
MATCH_INDICATORS = ["rsi", "macd", "supertrend"]
MIN_MATCH_SCORE = 3

# ✅ Pattern tracking stats for hourly summaries or commands
pattern_stats = {
    "scans": 0,
    "matches": 0,
    "trades": 0
}

async def pattern_match_scan(symbols):
    patterns = load_patterns()

    for symbol in symbols:
        await asyncio.sleep(1.5)
        pattern_stats["scans"] += 1  # ✅ Count every scan

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
            for entry in patterns[-100:]:
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
                pattern_stats["matches"] += 1  # ✅ Track matched patterns

                direction = "Long" if tf_scores.get("rsi", 0) > 45 else "Short"
                price = float(live_candles[symbol]['1'][-1]['close'])
                confidence = 90
                leverage = 5
                risk_pct = 9.0
                trailing_pct = 0.5

                sl = price * 0.985 if direction == "Long" else price * 1.015
                tp1 = price * 1.018 if direction == "Long" else price * 0.982
                tp2 = price * 1.035 if direction == "Long" else price * 0.965

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
                    pattern_stats["trades"] += 1  # ✅ Track executed trades
                    log(f"🚀 Pattern-based trade executed for {symbol} | Entry: {price}")
                    write_log(f"AUTO TRADE (pattern match): {symbol} | Entry: {price} | SL: {sl} | TP1: {tp1}")

                    # ✅ Register trade in monitor for ongoing tracking
                    track_active_trade(
                        symbol=symbol,
                        trade_type="Scalp",
                        initial_score=score,
                        entry_price=price,
                        direction=direction,
                        trailing_pct=trailing_pct,
                        tp2=tp2,
                        sl=sl
                    )
                    
                    write_log("PATTERN MATCH: cycle running...")

        except Exception as e:
            log(f"❌ Pattern match failed for {symbol}: {e}", level="ERROR")
