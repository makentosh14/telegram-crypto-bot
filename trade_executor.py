# trade_executor.py

from bybit_api import (
    place_market_order,
    get_balance,
    set_leverage,
    set_margin_mode,
    cancel_all_orders
)
from symbol_utils import is_spot_symbol, get_symbol_category
from config import DEFAULT_LEVERAGE, MARGIN_MODE
from logger import log

async def execute_trade_if_valid(signal_data, max_risk=0.02):
    symbol = signal_data["symbol"]
    category = get_symbol_category(symbol)
    is_spot = category == "spot"

    log(f"⚙️ Executing trade for {symbol} [{category.upper()}]...")

    try:
        balance = await get_balance()
        risk_amount = balance * max_risk

        price = float(signal_data.get("price", 1.0))  # fallback in case price not attached
        qty = round(risk_amount / price, 2 if is_spot else 1)

        if not is_spot:
            await set_margin_mode(symbol, MARGIN_MODE)
            await set_leverage(symbol, buy_leverage=DEFAULT_LEVERAGE, sell_leverage=DEFAULT_LEVERAGE)

        await cancel_all_orders(symbol, category=category)
        order_result = await place_market_order(symbol, "Buy", qty, market_type=category)

        if order_result.get("retCode") == 0:
            log(f"✅ Order placed for {symbol} | Qty: {qty} | Mode: {category.upper()}")
        else:
            log(f"❌ Order failed for {symbol}: {order_result}", level="ERROR")

    except Exception as e:
        log(f"❌ Exception in trade execution for {symbol}: {e}", level="ERROR")
