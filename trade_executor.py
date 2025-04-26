from bybit_api_async import signed_request
from symbol_utils import get_symbol_category
from config import DEFAULT_LEVERAGE, MARGIN_MODE
from logger import log
from telegram_bot import send_telegram_message
from atr import calculate_atr


def calculate_quantity(risk_amount, price, category="spot"):
    """
    Calculate quantity based on price and market type with dynamic precision.
    - More decimals for cheaper coins.
    - Futures and spot handled separately.
    """
    if category == "spot":
        if price < 0.1:
            qty = round(risk_amount / price, 4)
        elif price < 1:
            qty = round(risk_amount / price, 3)
        elif price < 100:
            qty = round(risk_amount / price, 2)
        else:
            qty = round(risk_amount / price, 1)
    else:  # Futures
        if price < 1:
            qty = round(risk_amount / price, 3)
        else:
            qty = round(risk_amount / price, 1)
    
    return qty

def calculate_sl_tp(price, trade_type, direction):
    if trade_type == "Scalp":
        sl_pct = 0.7
        tp1_pct = 1.5
    elif trade_type == "Intraday":
        sl_pct = 1.5
        tp1_pct = 3.0
    else:  # Swing
        sl_pct = 2.5
        tp1_pct = 6.0

    if direction == "Long":
        sl = round(price * (1 - sl_pct / 100), 4)
        tp1 = round(price * (1 + tp1_pct / 100), 4)
    else:
        sl = round(price * (1 + sl_pct / 100), 4)
        tp1 = round(price * (1 - tp1_pct / 100), 4)

    return sl, tp1, sl_pct, tp1_pct

def calculate_dynamic_sl_tp(candles_by_tf, price, trade_type, direction, score, confidence):
    atr_tf_map = {
        "Scalp": '3',
        "Intraday": '15',
        "Swing": '60'
    }
    atr_tf = atr_tf_map.get(trade_type, '15')
    candles = candles_by_tf.get(atr_tf)
    atr = calculate_atr(candles) if candles else None

    atr_factor_map = {
        "Scalp": 1.5,
        "Intraday": 2.0,
        "Swing": 2.5
    }
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

    return sl, tp1, sl_pct, trailing_pct

async def execute_trade_if_valid(signal_data, max_risk=0.06):
    symbol = signal_data["symbol"]
    category = get_symbol_category(symbol)
    trade_type = signal_data.get("trade_type", "Intraday")
    direction = signal_data.get("direction", "Long")

    log(f"⚙️ Executing {direction.upper()} trade for {symbol} [{category.upper()}] as {trade_type}...")

    try:
        # === Step 1: Get account balance ===
        balance_data = await signed_request("GET", "/v5/account/wallet-balance", {
            "accountType": "UNIFIED"
        })
        usdt_balance = float(balance_data["result"]["list"][0]["coin"][0]["availableToWithdraw"])

        price = float(signal_data.get("price", 1.0))
        risk_amount = usdt_balance * max_risk
        qty = calculate_quantity(risk_amount, price, category)

        score = signal_data.get("score", 5)
        confidence = signal_data.get("confidence", 60)
        candles_by_tf = signal_data.get("candles")

        sl, tp1, sl_pct, trailing_pct = calculate_dynamic_sl_tp(
            candles_by_tf, price, trade_type, direction, score, confidence
        )

        if category != "spot":
            # Set margin mode (crossed)
            await signed_request("POST", "/v5/position/set-leverage", {
                "category": "linear",
                "symbol": symbol,
                "buyLeverage": DEFAULT_LEVERAGE,
                "sellLeverage": DEFAULT_LEVERAGE
            })

        # Cancel existing open orders
        await signed_request("POST", "/v5/order/cancel-all", {
            "category": "linear" if category == "futures" else "spot",
            "symbol": symbol
        })

        # Place market order
        order_result = await signed_request("POST", "/v5/order/create", {
            "category": "linear" if category == "futures" else "spot",
            "symbol": symbol,
            "side": "Buy" if direction == "Long" else "Sell",
            "orderType": "Market",
            "qty": qty,
            "timeInForce": "GTC"
        })

        if order_result.get("retCode") == 0:
            log(f"✅ {direction.upper()} Order placed for {symbol} | Qty: {qty} | SL: {sl} | TP1: {tp1}")
            await send_telegram_message(
                f"🚨 <b>{trade_type} {direction} Executed</b>\n"
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

    except Exception as e:
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")

    return None
