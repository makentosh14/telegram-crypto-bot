from bybit_api import signed_request, get_futures_available_balance
from symbol_utils import get_symbol_category
from config import DEFAULT_LEVERAGE
from logger import log
from error_handler import send_telegram_message
from atr import calculate_atr
from activity_logger import write_log, log_trade_to_file
from symbol_info import round_qty, symbol_precisions
from datetime import datetime
from volume import get_average_volume
import asyncio
import json
import traceback
import time


def calculate_quantity(symbol, raw_qty):
    if raw_qty <= 0:
        return 0
    min_qty = symbol_precisions.get(symbol, {}).get("min_qty", 0.001)
    rounded_qty = round_qty(symbol, raw_qty)
    if rounded_qty < min_qty:
        return 0
    return rounded_qty


def calculate_dynamic_sl_tp(candles_by_tf, price, trade_type, direction, score, confidence, regime="trending"):
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

    if regime == "volatile":
        sl_pct *= 1.5
    elif regime == "ranging":
        sl_pct *= 1.3

    tp1_pct = sl_pct * 1.8
    trailing_pct = sl_pct * 0.5

    if direction.lower() == "long":
        sl = round(price * (1 - sl_pct / 100), 6)
        tp1 = round(price * (1 + tp1_pct / 100), 6)
    else:
        sl = round(price * (1 + sl_pct / 100), 6)
        tp1 = round(price * (1 - tp1_pct / 100), 6)

    return sl, tp1, sl_pct, trailing_pct, tp1_pct


# OPTIMIZATION: Removed twap_execute_trade to make execution immediate

# Cached balance values for faster execution
_cached_balance = None
_balance_timestamp = 0

async def execute_trade_if_valid(signal_data, max_risk=0.06):
    global _cached_balance, _balance_timestamp
    
    symbol = signal_data["symbol"]
    category = get_symbol_category(symbol)
    trade_type = signal_data.get("trade_type", "Intraday")
    direction = signal_data.get("direction", "Long").strip().lower()
    regime = signal_data.get("regime", "trending")

    log(f"⚙️ Executing {direction.upper()} trade for {symbol} [{category.upper()}] as {trade_type}...")

    try:
        # OPTIMIZATION: Use cached balance if available and recent
        current_time = time.time()
        if _cached_balance is None or current_time - _balance_timestamp > 60:
            usdt_balance = await get_futures_available_balance()
            _cached_balance = usdt_balance
            _balance_timestamp = current_time
            log(f"💰 Fetched fresh balance: {usdt_balance} USDT")
        else:
            usdt_balance = _cached_balance
            log(f"💰 Using cached balance: {usdt_balance} USDT (cached {int(current_time - _balance_timestamp)}s ago)")
        
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
            log(f"⚠️ Skipped {symbol}: Quantity too small.")
            return None

        score = signal_data.get("score", 5)
        confidence = signal_data.get("confidence", 60)
        candles_by_tf = signal_data.get("candles")
        indicator_scores = signal_data.get("indicator_scores", {})
        used_indicators = signal_data.get("used_indicators", {})

        # OPTIMIZATION: Removed volume check as we already check this in scoring

        # OPTIMIZATION: Set leverage in parallel with other operations
        leverage_task = signed_request("POST", "/v5/position/set-leverage", {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        })

        # Cancel any existing orders to prevent conflicts
        cancel_task = signed_request("POST", "/v5/order/cancel-all", {
            "category": category, 
            "symbol": symbol
        })

        # Wait for both tasks
        await asyncio.gather(leverage_task, cancel_task)

        # OPTIMIZATION: Execute market order immediately
        order_payload = {
            "category": category,
            "symbol": symbol,
            "side": "Buy" if direction.lower() == "long" else "Sell",
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "IOC"
        }
        
        log(f"📤 Sending market order: {order_payload}")
        order_result = await signed_request("POST", "/v5/order/create", order_payload)
        log(f"📥 Order result: {order_result}")
        
        # Process order result
        if order_result.get("retCode") == 0:
            executed_entry = float(order_result.get("result", {}).get("avgPrice", price)) or price
            
            # OPTIMIZATION: Skip slippage check to execute immediately
                
            sl, tp1, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                candles_by_tf, executed_entry, trade_type, direction, score, confidence, regime
            )

            # OPTIMIZATION: Skip SL adjustment for immediate execution
            
            # Get market price for validation
            try:
                ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": category, "symbol": symbol})
                mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", executed_entry))
                log(f"📊 Got mark price: {mark_price}")
                
                # Validate SL is on the correct side of mark price
                if direction.lower() == "long" and sl >= mark_price:
                    sl = round(mark_price * 0.995, 6)  # 0.5% below mark price
                    log(f"🔧 Adjusted Long SL to {sl} (below mark price {mark_price})")
                elif direction.lower() == "short" and sl <= mark_price:
                    sl = round(mark_price * 1.005, 6)  # 0.5% above mark price
                    log(f"🔧 Adjusted Short SL to {sl} (above mark price {mark_price})")
            except Exception as e:
                log(f"⚠️ Failed to validate SL: {e}", level="WARN")

            side = "Sell" if direction.lower() == "long" else "Buy"
            min_qty = symbol_precisions.get(symbol, {}).get("min_qty", 0.001)
            qty_half = max(round_qty(symbol, qty / 2), min_qty)

            # OPTIMIZATION: Execute SL and TP orders in parallel
            from bybit_api import place_stop_loss
            sl_task = place_stop_loss(
                symbol=symbol,
                direction=direction,
                qty=qty,
                sl_price=sl,
                market_type=category
            )

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

            # Wait for both orders to complete
            sl_result, tp1_result = await asyncio.gather(sl_task, tp1_task)
            
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

            # Send a minimal notification after trade execution (full detail sent in main.py)
            await send_telegram_message(
                f"✅ <b>{trade_type} {direction.upper()} Executed</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Entry: {executed_entry}\n"
                f"SL: {sl} | TP1: {tp1}"
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
            error_msg = f"❌ Order failed: {order_result.get('retMsg', 'Unknown error')}"
            log(error_msg, level="ERROR")
            await send_telegram_message(
                f"❌ <b>Order Failed</b>\nSymbol: <b>{symbol}</b>\nReason: {order_result.get('retMsg', 'Unknown error')}"
            )

    except Exception as e:
        error_trace = traceback.format_exc()
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")
        log(f"Stack trace: {error_trace}", level="ERROR")
        await send_telegram_message(
            f"❌ <b>Execution Error</b>\nSymbol: <b>{symbol}</b>\nError: {str(e)}"
        )

    return None
