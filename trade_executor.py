from bybit_api import place_order, set_leverage_mode, set_leverage, get_balance
from telegram_bot import send_trade_execution, send_error_report
import time

DEFAULT_LEVERAGE = 10
DEFAULT_MARGIN_MODE = "CROSS"
DEFAULT_TRADE_RISK = 0.03  # 3% of balance per trade

def calculate_position_size(symbol, price, balance, risk_pct=DEFAULT_TRADE_RISK, leverage=DEFAULT_LEVERAGE):
    # Risk-based fixed % of balance, adjusted by leverage
    risk_amount = balance * risk_pct
    position_size = (risk_amount * leverage) / price
    return round(position_size, 3)

def execute_trade(symbol, side, entry, sl, tp1, tp2, market_type="futures", leverage=DEFAULT_LEVERAGE, margin_mode=DEFAULT_MARGIN_MODE):
    try:
        # 1. Fetch balance
        balance = get_balance(market_type)
        if balance < 10:
            send_error_report("Trade Rejected", "Low balance")
            return

        # 2. Set leverage & margin
        set_leverage_mode(symbol, margin_mode, market_type)
        set_leverage(symbol, leverage, market_type)

        # 3. Calculate position size
        qty = calculate_position_size(symbol, entry, balance, DEFAULT_TRADE_RISK, leverage)

        # 4. Place market order
        response = place_order(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry,
            stop_loss=sl,
            tp1=tp1,
            tp2=tp2,
            market_type=market_type
        )

        # 5. Telegram alert
        send_trade_execution(symbol, side, qty, entry, sl, tp1, tp2)
        print(f"[TRADE EXECUTED] {symbol} {side} x{qty} @ {entry}")

    except Exception as e:
        send_error_report("execute_trade", str(e))
        time.sleep(2)
