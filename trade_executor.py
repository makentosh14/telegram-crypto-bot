from bybit_api import signed_request
from symbol_utils import get_symbol_category
from config import DEFAULT_LEVERAGE
from logger import log
from telegram_bot import send_telegram_message
from atr import calculate_atr

def calculate_quantity(risk_amount, price, category="spot"):
    if price == 0:
        return 0
    if category == "spot":
        if price < 0.1:
            qty = round(risk_amount / price, 4)
        elif price < 1:
            qty = round(risk_amount / price, 3)
        elif price < 100:
            qty = round(risk_amount / price, 2)
        else:
            qty = round(risk_amount / price, 1)
    else:
        if price < 1:
            qty = round(risk_amount / price, 3)
        else:
            qty = round(risk_amount / price, 1)
    return qty

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
        from bybit_api import get_wallet_balance
        balance_data = await get_wallet_balance()

        if not balance_data or "result" not in balance_data or "list" not in balance_data["result"]:
            await send_telegram_message(
                f"❌ <b>Execution Error</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Error: Wallet balance data is missing or invalid."
            )
            log(f"❌ Invalid balance response: {balance_data}", level="ERROR")
            return None

        coins = balance_data["result"]["list"][0]["coin"]
        usdt_info = next((coin for coin in coins if coin["coin"] == "USDT"), None)

        if not usdt_info:
            await send_telegram_message(
                f"❌ <b>Execution Error</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Error: USDT coin entry missing in wallet."
            )
            log(f"❌ USDT entry missing: {coins}", level="ERROR")
            return None

        usdt_str = usdt_info.get("availableToWithdraw") or usdt_info.get("walletBalance")
        try:
            usdt_balance = float(usdt_str)
        except (ValueError, TypeError):
            await send_telegram_message(
                f"❌ <b>Execution Error</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Error: USDT balance string invalid: '{usdt_str}'"
            )
            log(f"❌ Cannot convert USDT balance string: '{usdt_str}'", level="ERROR")
            return None

        price = float(signal_data.get("price", 1.0))
        risk_amount = usdt_balance * max_risk
        qty = calculate_quantity(risk_amount, price, category)

        if qty <= 0:
            await send_telegram_message(
                f"❌ <b>Order Failed</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Reason: Calculated quantity is too low ({qty})."
            )
            log(f"❌ Order not sent due to invalid quantity: {qty}", level="ERROR")
            return None

        score = signal_data.get("score", 5)
        confidence = signal_data.get("confidence", 60)
        candles_by_tf = signal_data.get("candles")

        sl, tp1, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
            candles_by_tf, price, trade_type, direction, score, confidence
        )

        if category != "spot":
            await signed_request("POST", "/v5/position/set-leverage", {
                "category": "linear",
                "symbol": symbol,
                "buyLeverage": DEFAULT_LEVERAGE,
                "sellLeverage": DEFAULT_LEVERAGE
            })

        await signed_request("POST", "/v5/order/cancel-all", {
            "category": category
        })

        order_payload = {
            "category": category,
            "symbol": symbol,
            "side": "Buy" if direction == "Long" else "Sell",
            "orderType": "Market",
            "qty": qty,
            "timeInForce": "GTC"
        }

        order_result = await signed_request("POST", "/v5/order/create", order_payload)

        if order_result.get("retCode") == 0:
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
                "tp1_pct": tp1_pct
            }
        else:
            log(f"❌ Order failed for {symbol}: {order_result}", level="ERROR")
            await send_telegram_message(
                f"❌ <b>Order Failed</b>\n"
                f"Symbol: <b>{symbol}</b>\n"
                f"Reason: {order_result.get('retMsg', 'Unknown error')}"
            )

    except Exception as e:
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")
        await send_telegram_message(
            f"❌ <b>Execution Error</b>\n"
            f"Symbol: <b>{symbol}</b>\n"
            f"Error: {str(e)}"
        )

    return None
