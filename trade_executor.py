from bybit_api import signed_request, get_futures_available_balance
from symbol_utils import get_symbol_category
from config import DEFAULT_LEVERAGE
from logger import log
from error_handler import send_telegram_message, send_error_to_telegram
from atr import calculate_atr
from activity_logger import write_log, log_trade_to_file
from symbol_info import round_qty, symbol_precisions
from score import score_symbol, determine_direction, calculate_confidence
from datetime import datetime
import asyncio

def calculate_quantity(symbol, raw_qty):
    if raw_qty <= 0:
        return 0
    min_qty = symbol_precisions.get(symbol, {}).get("min_qty", 0.001)
    rounded_qty = round_qty(symbol, raw_qty)
    if rounded_qty < min_qty:
        return 0
    return rounded_qty

def calculate_dynamic_sl_tp(candles_by_tf, price, trade_type, direction, score, confidence):
    atr_tf_map = {"Scalp": '3', "Intraday": '15', "Swing": '60'}
    atr_tf = atr_tf_map.get(trade_type, '15')
    candles = candles_by_tf.get(atr_tf)
    atr = calculate_atr(candles) if candles else None

    atr_factor = 1.2
    if atr:
        sl_distance = atr * atr_factor
        sl_pct = (sl_distance / price) * 100
    else:
        if confidence >= 85 and score >= 7.5:
            sl_pct = 1.5
        elif confidence < 60 or score < 6:
            sl_pct = 0.6
        else:
            sl_pct = 1.0

    tp1_pct = sl_pct * 1.8
    tp2_pct = sl_pct * 3.5
    trailing_pct = sl_pct * 0.5

    if direction == "Long":
        sl = round(price * (1 - sl_pct / 100), 6)
        tp1 = round(price * (1 + tp1_pct / 100), 6)
        tp2 = round(price * (1 + tp2_pct / 100), 6)
    else:
        sl = round(price * (1 + sl_pct / 100), 6)
        tp1 = round(price * (1 - tp1_pct / 100), 6)
        tp2 = round(price * (1 - tp2_pct / 100), 6)

    return sl, tp1, tp2, sl_pct, trailing_pct, tp1_pct, tp2_pct

async def execute_trade_if_valid(signal_data, max_risk=0.06):
    symbol = signal_data["symbol"]
    category = get_symbol_category(symbol)
    trade_type = signal_data.get("trade_type", "Intraday")
    direction = signal_data.get("direction", "Long")

    log(f"⚙️ Executing {direction.upper()} trade for {symbol} [{category.upper()}] as {trade_type}...")

    try:
        usdt_balance = await get_futures_available_balance()
        if usdt_balance <= 0:
            await send_telegram_message(
                f"❌ <b>Execution Error</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Error: Futures available balance is 0."
            )
            return None

        price = float(signal_data.get("price", 1.0))
        leverage = DEFAULT_LEVERAGE
        risk_amount = usdt_balance * max_risk
        position_value = risk_amount * leverage
        raw_qty = position_value / price
        qty = calculate_quantity(symbol, raw_qty)

        if qty <= 0:
            log(f"❌ Skipping {symbol} — qty too low ({qty}) or invalid for Bybit min limit")
            await send_telegram_message(
                f"⚠️ Skipped <b>{symbol}</b>: Quantity too small or invalid for Bybit minimum."
            )
            return None

        if qty * price > usdt_balance * leverage:
            log(f"⚠️ Qty too large for balance! Requested ${qty * price:.2f} > Available {usdt_balance * leverage:.2f}")
            await send_telegram_message(
                f"⚠️ <b>Order Blocked</b>\n<b>{symbol}</b>: Qty too large.\n"
                f"Needed: ${qty * price:.2f}, Available: ${usdt_balance * leverage:.2f}"
            )
            return None

        score = signal_data.get("score", 5)
        confidence = signal_data.get("confidence", 60)
        candles_by_tf = signal_data.get("candles")
        indicator_scores = signal_data.get("indicator_scores", {})
        used_indicators = signal_data.get("used_indicators", {})

        if category != "spot":
            await signed_request("POST", "/v5/position/set-leverage", {
                "category": "linear",
                "symbol": symbol,
                "buyLeverage": str(leverage),
                "sellLeverage": str(leverage)
            })

        await signed_request("POST", "/v5/order/cancel-all", {
            "category": category
        })

        order_payload = {
            "category": category,
            "symbol": symbol,
            "side": "Buy" if direction == "Long" else "Sell",
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "IOC",
        }

        order_result = await signed_request("POST", "/v5/order/create", order_payload)

        if order_result.get("retCode") == 0:
            executed_entry = float(order_result.get("result", {}).get("avgPrice", price)) or price
            sl, tp1, tp2, sl_pct, trailing_pct, tp1_pct, tp2_pct = calculate_dynamic_sl_tp(
                candles_by_tf, executed_entry, trade_type, direction, score, confidence
            )

            sl_side = "Sell" if direction == "Long" else "Buy"
            tp_side = sl_side
            qty_half = round(qty / 2, 6)
            if qty_half <= 0:
                qty_half = qty

            tp1_task = signed_request("POST", "/v5/order/create", {
                "category": category,
                "symbol": symbol,
                "side": tp_side,
                "orderType": "Limit",
                "qty": str(qty_half),
                "price": str(tp1),
                "timeInForce": "GTC",
                "reduceOnly": True
            })

            tp2_task = signed_request("POST", "/v5/order/create", {
                "category": category,
                "symbol": symbol,
                "side": tp_side,
                "orderType": "Limit",
                "qty": str(qty_half),
                "price": str(tp2),
                "timeInForce": "GTC",
                "reduceOnly": True
            })

            # ✅ Adjust triggerDirection based on SL vs current price
            trigger_direction = 1 if (direction == "Long" and sl > executed_entry) or (direction == "Short" and sl < executed_entry) else 2

            sl_task = signed_request("POST", "/v5/order/create", {
                "category": category,
                "symbol": symbol,
                "side": sl_side,
                "orderType": "Market",
                "triggerPrice": str(sl),
                "triggerDirection": trigger_direction,
                "triggerBy": "LastPrice",
                "qty": str(qty),
                "reduceOnly": True,
                "timeInForce": "GTC",
                "orderFilter": "Stop"
            })

            tp1_result, tp2_result, sl_result = await asyncio.gather(tp1_task, tp2_task, sl_task)
            log(f"📤 TP1 response: {tp1_result}")
            log(f"📤 TP2 response: {tp2_result}")
            log(f"📤 SL response: {sl_result}")

            if sl_result.get("retCode") != 0:
                log(f"❌ SL order failed: {sl_result}", level="ERROR")
                await send_telegram_message(
                    f"❗️<b>SL Order Failed</b> for {symbol}\nReason: {sl_result.get('retMsg')}"
                )

            log(f"✅ {direction.upper()} Order placed for {symbol} | Qty: {qty} | SL: {sl} | TP1: {tp1} | TP2: {tp2}")
            write_log(f"TRADE EXECUTED: {symbol} | {direction} | Qty: {qty} | SL: {sl} | TP1: {tp1} | TP2: {tp2} | Type: {trade_type}")

            log_trade_to_file(
                symbol=symbol,
                direction=direction,
                entry=executed_entry,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                result="open",
                score=score,
                trade_type=trade_type,
                confidence=confidence,
                tf_scores=signal_data.get("tf_scores", {}),
                indicator_scores=indicator_scores,
                used_indicators=used_indicators,
                pattern_detected=signal_data.get("pattern"),
                whale_signal=signal_data.get("whale", False),
                volume_spike=signal_data.get("volume_spike", False),
                sl_strategy=f"ATR-{trade_type}"
            )

            await send_telegram_message(
                f"📣 <b>{trade_type} {direction} Executed</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Qty: {qty} (TP1/TP2 split)\n"
                f"SL: {sl} ({sl_pct:.2f}%) | TP1: {tp1} | TP2: {tp2}\n"
                f"Trailing SL activates after TP1 hit ({trailing_pct:.2f}% base)"
            )

            return {
                "entry": executed_entry,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "qty": qty,
                "type": trade_type,
                "direction": direction,
                "symbol": symbol,
                "sl_pct": sl_pct,
                "tp1_pct": tp1_pct,
                "tp2_pct": tp2_pct,
                "trailing_pct": trailing_pct,
                "indicator_scores": indicator_scores,
                "used_indicators": used_indicators
            }

        else:
            error_msg = order_result.get("retMsg", "Unknown error")
            await send_telegram_message(
                f"❌ <b>Order Failed</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Qty: <b>{qty}</b>\n"
                f"Reason: {error_msg}"
            )
            log(f"❌ Order failed payload: {order_payload}", level="ERROR")
            log(f"❌ Order failed response: {order_result}", level="ERROR")
            write_log(f"ORDER FAILED: {symbol} | Reason: {error_msg} | Payload: {order_payload}", level="ERROR")

    except Exception as e:
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")
        await send_telegram_message(
            f"❌ <b>Execution Error</b>\n"
            f"Symbol: <b>{symbol}</b>\n"
            f"Error: {str(e)}"
        )
        write_log(f"BALANCE ERROR: No available USDT for {symbol}", level="WARNING")

    return None

