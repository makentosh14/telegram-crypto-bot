from bybit_api import signed_request, get_futures_available_balance
from symbol_utils import get_symbol_category
from config import DEFAULT_LEVERAGE
from logger import log
from telegram_bot import send_telegram_message
from atr import calculate_atr


def calculate_quantity(raw_qty, price, category="spot"):
    if raw_qty <= 0:
        return 0

    if category == "spot":
        if price < 0.1:
            qty = round(raw_qty, 4)
        elif price < 1:
            qty = round(raw_qty, 3)
        elif price < 100:
            qty = round(raw_qty, 2)
        else:
            qty = round(raw_qty, 1)
    else:
        if price < 1:
            qty = round(raw_qty, 3)
        else:
            qty = round(raw_qty, 1)

    return max(qty, 0.001)


def calculate_dynamic_sl_tp(candles_by_tf, price, trade_type, direction, score, confidence):
    atr_tf_map = {"Scalp": '3', "Intraday": '15', "Swing": '60'}
    atr_tf = atr_tf_map.get(trade_type, '15')
    candles = candles_by_tf.get(atr_tf)
    atr = calculate_atr(candles) if candles else None

    atr_factor_map = {"Scalp": 1.5, "Intraday": 2.0, "Swing": 2.5}
    factor = atr_factor_map.get(trade_type, 2.0)

    if atr:
        sl_distance = atr * factor
        sl_pct = (sl_distance / price) * 100
    else:
        if confidence >= 85 and score >= 7.5:
            sl_pct = 1.5
        elif confidence < 60 or score < 6:
            sl_pct = 0.6
        else:
            sl_pct = 1.0

    tp1_pct = sl_pct * 2.0
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
                f"❌ <b>Execution Error</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Error: Futures available balance is 0."
            )
            return None

        price = float(signal_data.get("price", 1.0))
        leverage = DEFAULT_LEVERAGE
        risk_amount = usdt_balance * max_risk
        position_size = risk_amount * leverage
        raw_qty = position_size / price
        qty = calculate_quantity(raw_qty, price, category)

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

        sl, tp1, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
            candles_by_tf, price, trade_type, direction, score, confidence
        )
        log(f"📏 Final qty = {qty} (type: {type(qty)})")

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
            "isLeverage": True
        }

        order_result = await signed_request("POST", "/v5/order/create", order_payload)

        if order_result.get("retCode") == 0:
            # Submit SL and TP1 orders
            sl_side = "Sell" if direction == "Long" else "Buy"
            tp_side = sl_side

            # Take-Profit (TP1)
            await signed_request("POST", "/v5/order/create", {
                "category": category,
                "symbol": symbol,
                "side": tp_side,
                "orderType": "Limit",
                "qty": str(qty),
                "price": str(tp1),
                "timeInForce": "GTC",
                "reduceOnly": True
            })

            # Stop-Loss
            await signed_request("POST", "/v5/order/create", {
                "category": category,
                "symbol": symbol,
                "side": sl_side,
                "orderType": "Market",
                "triggerDirection": 1 if direction == "Long" else 2,
                "triggerPrice": str(sl),
                "qty": str(qty),
                "timeInForce": "IOC",
                "reduceOnly": True
            })

            log(f"✅ {direction.upper()} Order placed for {symbol} | Qty: {qty} | SL: {sl} | TP1: {tp1}")
            await send_telegram_message(
                f"📣 <b>{trade_type} {direction} Executed</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Qty: {qty} | SL: {sl} ({sl_pct:.2f}%) | TP1: {tp1}\n"
                f"Trailing SL activates after TP1 hit ({trailing_pct:.2f}% base)"
            )
            return {
                "entry": price,
                "sl": sl,
                "tp1": tp1,
                "qty": qty,
                "type": trade_type,
                "direction": direction,
                "symbol": symbol,
                "sl_pct": sl_pct,
                "tp1_pct": tp1_pct,
                "trailing_pct": trailing_pct
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

    except Exception as e:
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")
        await send_telegram_message(
            f"❌ <b>Execution Error</b>\n"
            f"Symbol: <b>{symbol}</b>\n"
            f"Error: {str(e)}"
        )

    return None
