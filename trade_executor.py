from bybit_api import (
    place_order, set_leverage, set_leverage_mode, get_balance,
    get_price, is_futures_pair, is_spot_pair
)
from risk_manager import calculate_position_size
from exit_manager import generate_tp_sl
from telegram_bot import send_telegram_message
from config import DEFAULT_LEVERAGE, MARGIN_MODE, TRADING_PAIR_WHITELIST

def execute_trade_if_valid(signal, max_risk):
    symbol = signal['symbol']
    score = signal['score']

    try:
        if not symbol.endswith("USDT"):
            print(f"⚠️ Skipping non-USDT pair: {symbol}")
            return

        if TRADING_PAIR_WHITELIST and symbol not in TRADING_PAIR_WHITELIST:
            print(f"⚠️ {symbol} not in whitelist.")
            return

        price = get_price(symbol)
        balance = get_balance()
        quantity = calculate_position_size(balance, price, max_risk, DEFAULT_LEVERAGE)

        if quantity <= 0:
            print(f"⚠️ Skipping {symbol}, quantity too low: {quantity}")
            return

        sl, tp1, tp2 = generate_tp_sl(symbol, price)

        if is_futures_pair(symbol):
            set_leverage_mode(symbol, MARGIN_MODE)
            set_leverage(symbol, DEFAULT_LEVERAGE)

            order = place_order(
                symbol=symbol,
                side="Buy",
                qty=quantity,
                entry=price,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                type="futures"
            )

        elif is_spot_pair(symbol):
            order = place_order(
                symbol=symbol,
                side="Buy",
                qty=quantity,
                entry=price,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                type="spot"
            )

        else:
            print(f"⚠️ Unknown market type for {symbol}")
            return

        send_telegram_message(
            f"✅ Executed Trade:\n"
            f"Symbol: {symbol}\n"
            f"Score: {score}\n"
            f"Entry: {price}\nSL: {sl}\nTP1: {tp1}\nTP2: {tp2}\nQty: {quantity}"
        )

    except Exception as e:
        send_telegram_message(f"❌ Trade execution failed for {symbol}: {str(e)}")
