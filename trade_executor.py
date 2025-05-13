from bybit_api import signed_request, get_futures_available_balance
from symbol_utils import get_symbol_category
from config import DEFAULT_LEVERAGE
from logger import log
from error_handler import send_telegram_message
from atr import calculate_atr
from activity_logger import write_log, log_trade_to_file
from symbol_info import round_qty, symbol_precisions
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
    trailing_pct = sl_pct * 0.5

    if direction == "Long":
        sl = round(price * (1 - sl_pct / 100), 6)
        tp1 = round(price * (1 + tp1_pct / 100), 6)
    else:
        sl = round(price * (1 + sl_pct / 100), 6)
        tp1 = round(price * (1 - tp1_pct / 100), 6)

    return sl, tp1, sl_pct, trailing_pct, tp1_pct


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
                f"❌ <b>Execution Error</b>\nSymbol: <b>{symbol}</b>\nError: Futures available balance is 0."
            )
            return None

        price = float(signal_data.get("price", 1.0))
        leverage = DEFAULT_LEVERAGE
        risk_amount = usdt_balance * max_risk
        position_value = risk_amount * leverage
        raw_qty = position_value / price
        qty = calculate_quantity(symbol, raw_qty)

        if qty <= 0:
            await send_telegram_message(f"⚠️ Skipped <b>{symbol}</b>: Quantity too small.")
            return None

        score = signal_data.get("score", 5)
        confidence = signal_data.get("confidence", 60)
        candles_by_tf = signal_data.get("candles")
        indicator_scores = signal_data.get("indicator_scores", {})
        used_indicators = signal_data.get("used_indicators", {})

        await signed_request("POST", "/v5/position/set-leverage", {
            "category": "linear",
            "symbol": symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        })

        await signed_request("POST", "/v5/order/cancel-all", {"category": category})

        order_payload = {
            "category": category,
            "symbol": symbol,
            "side": "Buy" if direction == "Long" else "Sell",
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "IOC"
        }

        order_result = await signed_request("POST", "/v5/order/create", order_payload)

        if order_result.get("retCode") == 0:
            executed_entry = float(order_result.get("result", {}).get("avgPrice", price)) or price
            sl, tp1, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                candles_by_tf, executed_entry, trade_type, direction, score, confidence
            )

            side = "Sell" if direction == "Long" else "Buy"
            min_qty = symbol_precisions.get(symbol, {}).get("min_qty", 0.001)
            qty_half = max(round_qty(symbol, qty / 2), min_qty)

            tp1_task = signed_request("POST", "/v5/order/create", {
                "category": category,
                "symbol": symbol,
                "side": side,
                "orderType": "Limit",
                "qty": str(qty_half),
                "price": str(tp1),
                "timeInForce": "GTC",
                "reduceOnly": True
            })

            if direction == "Long":
                trigger_direction = 2 if sl >= executed_entry else 1
                if sl >= executed_entry:
                    sl = round(executed_entry * 0.998, 6)
            else:
                trigger_direction = 2 if sl <= executed_entry else 1
                if sl <= executed_entry:
                    sl = round(executed_entry * 1.002, 6)

            sl_task = signed_request("POST", "/v5/order/create", {
                "category": category,
                "symbol": symbol,
                "side": side,
                "orderType": "Market",
                "triggerPrice": str(sl),
                "triggerDirection": trigger_direction,
                "triggerBy": "LastPrice",
                "qty": str(qty),
                "reduceOnly": True,
                "timeInForce": "GTC",
                "orderFilter": "Stop"
            })

            tp1_result, sl_result = await asyncio.gather(tp1_task, sl_task)
            log(f"📤 TP1 response: {tp1_result}")
            log(f"📤 SL response: {sl_result}")

            sl_order_id = sl_result.get("result", {}).get("orderId")

            log_trade_to_file(
                symbol=symbol,
                direction=direction,
                entry=executed_entry,
                sl=sl,
                tp1=tp1,
                tp2=None,
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
                f"Qty: {qty} (TP1 only)\n"
                f"SL: {sl} ({sl_pct:.2f}%) | TP1: {tp1}\n"
                f"Trailing SL activates after TP1 hit ({trailing_pct:.2f}% base)"
            )

            return {
                "entry": executed_entry,
                "sl": sl,
                "tp1": tp1,
                "tp2": None,
                "qty": qty,
                "type": trade_type,
                "direction": direction,
                "symbol": symbol,
                "sl_pct": sl_pct,
                "tp1_pct": tp1_pct,
                "tp2_pct": None,
                "trailing_pct": trailing_pct,
                "indicator_scores": indicator_scores,
                "used_indicators": used_indicators,
                "sl_order_id": sl_order_id
            }

        else:
            await send_telegram_message(
                f"❌ <b>Order Failed</b>\nSymbol: <b>{symbol}</b>\nReason: {order_result.get('retMsg')}"
            )
            log(f"❌ Order failed: {order_result}", level="ERROR")

    except Exception as e:
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")
        await send_telegram_message(
            f"❌ <b>Execution Error</b>\nSymbol: <b>{symbol}</b>\nError: {str(e)}"
        )

    return None
