# trade_executor.py

from bybit_api import (
    place_market_order,
    get_balance,
    set_leverage,
    set_margin_mode,
    cancel_all_orders
)
from symbol_utils import get_symbol_category
from config import DEFAULT_LEVERAGE, MARGIN_MODE
from logger import log

def calculate_sl_tp(price, trade_type):
    if trade_type == "Scalp":
        sl_pct = 0.7
        tp1_pct = 1.5
    elif trade_type == "Intraday":
        sl_pct = 1.5
        tp1_pct = 3.0
    else:  # Swing
        sl_pct = 2.5
        tp1_pct = 6.0

    sl = round(price * (1 - sl_pct / 100), 4)
    tp1 = round(price * (1 + tp1_pct / 100), 4)
    return sl, tp1

async def execute_trade_if_valid(signal_data, max_risk=0.02):
    symbol = signal_data["symbol"]
    category = get_symbol_category(symbol)
    trade_type = signal_data.get("trade_type", "Intraday")

    log(f"⚙️ Executing trade for {symbol} [{category.upper()}] as {trade_type}...")

    try:
        balance = await get_balance()
        price = float(signal_data.get("price", 1.0))
        risk_amount = balance * max_risk
        qty = round(risk_amount / price, 2 if category == "spot" else 1)

        sl, tp1 = calculate_sl_tp(price, trade_type)

        if category != "spot":
            await set_margin_mode(symbol, MARGIN_MODE)
            await set_leverage(symbol, buy_leverage=DEFAULT_LEVERAGE, sell_leverage=DEFAULT_LEVERAGE)

        await cancel_all_orders(symbol, category=category)
        order_result = await place_market_order(symbol, "Buy", qty, market_type=category)

        if order_result.get("retCode") == 0:
            log(f"✅ Order placed for {symbol} | Qty: {qty} | SL: {sl} | TP1: {tp1}")
            return {
                "entry": price,
                "sl": sl,
                "tp1": tp1,
                "qty": qty,
                "type": trade_type
            }
        else:
            log(f"❌ Order failed for {symbol}: {order_result}", level="ERROR")

    except Exception as e:
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")

    return None
