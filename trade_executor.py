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
import json
import traceback


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

    if direction.lower() == "long":
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
    direction = signal_data.get("direction", "Long").strip().lower()

    log(f"⚙️ Executing {direction.upper()} trade for {symbol} [{category.upper()}] as {trade_type}...")

    try:
        # Fetch available balance - log detailed info for debugging
        log(f"📊 Fetching futures balance for {symbol} trade...")
        usdt_balance = await get_futures_available_balance()
        log(f"💰 Futures available balance: {usdt_balance} USDT")
        
        if usdt_balance <= 0:
            error_msg = f"❌ <b>Execution Error</b>\nSymbol: <b>{symbol}</b>\nError: Futures available balance is 0."
            log(error_msg, level="ERROR")
            await send_telegram_message(error_msg)
            return None

        price = float(signal_data.get("price", 1.0))
        planned_entry = price
        leverage = DEFAULT_LEVERAGE
        risk_amount = usdt_balance * max_risk
        position_value = risk_amount * leverage
        raw_qty = position_value / price
        
        log(f"📈 Trade calculation: Risk {max_risk*100}% of {usdt_balance} USDT = {risk_amount} USDT risk")
        log(f"📈 Position value: {position_value} USDT ({risk_amount} × {leverage})")
        log(f"📈 Raw quantity: {raw_qty} units ({position_value} ÷ {price})")
        
        qty = calculate_quantity(symbol, raw_qty)
        log(f"📈 Final quantity after rounding: {qty}")

        if qty <= 0:
            await send_telegram_message(f"⚠️ Skipped <b>{symbol}</b>: Quantity too small.")
            return None

        score = signal_data.get("score", 5)
        confidence = signal_data.get("confidence", 60)
        candles_by_tf = signal_data.get("candles")
        indicator_scores = signal_data.get("indicator_scores", {})
        used_indicators = signal_data.get("used_indicators", {})

        await signed_request("POST", "/v5/position/set-leverage", {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        })

        await signed_request("POST", "/v5/order/cancel-all", {"category": category, "symbol": symbol})

        order_payload = {
            "category": category,
            "symbol": symbol,
            "side": "Buy" if direction == "long" else "Sell",
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "IOC"
        }
        
        log(f"📤 Sending market order: {order_payload}")
        order_result = await signed_request("POST", "/v5/order/create", order_payload)
        log(f"📥 Order result: {order_result}")

        if order_result.get("retCode") == 0:
            executed_entry = float(order_result.get("result", {}).get("avgPrice", price)) or price
            sl, tp1, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                candles_by_tf, executed_entry, trade_type, direction, score, confidence
            )

            if direction == "long" and executed_entry < planned_entry:
                diff_pct = (planned_entry - executed_entry) / planned_entry
                sl = round(sl * (1 - diff_pct), 6)
                log(f"🔧 Adjusted SL down by {diff_pct:.4f} for lower-than-expected entry")
            elif direction == "short" and executed_entry > planned_entry:
                diff_pct = (executed_entry - planned_entry) / planned_entry
                sl = round(sl * (1 + diff_pct), 6)
                log(f"🔧 Adjusted SL up by {diff_pct:.4f} for higher-than-expected short entry")
            else:
                log("✅ No SL adjustment needed based on entry slippage")

            MIN_SL_BUFFER = 0.0035
            try:
                ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": category, "symbol": symbol})
                mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", executed_entry))
                log(f"📊 Got mark price: {mark_price}")
            except Exception as e:
                mark_price = executed_entry
                log(f"⚠️ Failed to fetch markPrice, using entry price: {e}")

            if direction == "long":
                trigger_direction = 1
                if sl >= mark_price:
                    old_sl = sl
                    sl = round(mark_price * (1 - MIN_SL_BUFFER), 6)
                    log(f"🔧 Adjusted Long SL from {old_sl} to {sl} (below mark price {mark_price})")
            else:
                trigger_direction = 2
                if sl <= mark_price:
                    old_sl = sl
                    sl = round(mark_price * (1 + MIN_SL_BUFFER), 6)
                    log(f"🔧 Adjusted Short SL from {old_sl} to {sl} (above mark price {mark_price})")

            side = "Sell" if direction == "long" else "Buy"

            log(f"🧪 SL Debug [1st Attempt] | {symbol} | Dir: {direction} | Entry: {executed_entry} | SL: {sl} | Mark: {mark_price} | TriggerDir: {trigger_direction}")

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

            # Use the improved SL placement approach
            from bybit_api import place_stop_loss
            sl_result = await place_stop_loss(
                symbol=symbol,
                direction=direction,
                qty=qty,
                sl_price=sl,
                market_type=category
            )

            if sl_result.get("retCode") != 0:
                log(f"❌ SL rejected — RetCode {sl_result.get('retCode')} | RetMsg: {sl_result.get('retMsg')}", level="ERROR")
                
                # Additional fallback - try a simpler SL approach as last resort
                fallback_sl_payload = {
                    "category": category,
                    "symbol": symbol,
                    "side": side,
                    "orderType": "Market",
                    "triggerPrice": str(sl),
                    "triggerDirection": trigger_direction,
                    "triggerBy": "LastPrice",  # Try LastPrice trigger
                    "qty": str(qty),
                    "reduceOnly": True,
                    "timeInForce": "GTC",
                    "orderFilter": "Stop",
                    "positionIdx": 0  # Explicitly set position index
                }
                
                log(f"🔁 Last resort SL attempt with payload: {fallback_sl_payload}")
                sl_result = await signed_request("POST", "/v5/order/create", fallback_sl_payload)
            
            tp1_result = await tp1_task
            log(f"📤 TP1 response: {tp1_result}")
            log(f"📤 SL response: {sl_result}")

            sl_order_id = sl_result.get("result", {}).get("orderId")
            if not sl_order_id:
                log(f"⚠️ Warning: No SL order ID returned. Will need to set SL manually.", level="WARN")

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
                f"📣 <b>{trade_type} {direction.upper()} Executed</b>\n"
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
        error_trace = traceback.format_exc()
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")
        log(f"Stack trace: {error_trace}", level="ERROR")
        await send_telegram_message(
            f"❌ <b>Execution Error</b>\nSymbol: <b>{symbol}</b>\nError: {str(e)}"
        )

    return None
