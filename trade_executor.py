from bybit_api import (
    place_order, set_leverage_mode, set_leverage, get_balance,
    is_spot_market, round_quantity, round_price
)
from exit_manager import generate_tp_sl
from risk_manager import calculate_position_size
from telegram_bot import send_telegram_message
from config import DEFAULT_LEVERAGE, RISK_LIMITS

def execute_trade_if_valid(signal, max_risk=0.03):
    symbol = signal['symbol']
    score = signal['score']
    print(f"⚙️ Attempting trade: {symbol} (Score: {score})")

    is_spot = is_spot_market(symbol)
    balance = get_balance()

    position_size = calculate_position_size(balance, symbol, max_risk, is_spot)
    if position_size is None:
        print(f"⚠️ Skipping {symbol}: could not calculate position size.")
        return

    # Generate SL/TP
    price_data = signal.get("price_data")
    if not price_data:
        print(f"⚠️ No price data for {symbol}, skipping trade.")
        return

    sl_price, tp1, tp2 = generate_tp_sl(price_data)
    if not sl_price or not tp1:
        print(f"⚠️ Invalid SL/TP for {symbol}, skipping.")
        return

    try:
        if not is_spot:
            set_leverage_mode(symbol, "ISOLATED")
            set_leverage(symbol, DEFAULT_LEVERAGE)

        qty = round_quantity(symbol, position_size)
        entry_price = float(price_data['close'])

        order_id = place_order(
            symbol=symbol,
            side="Buy",
            qty=qty,
            entry_price=round_price(symbol, entry_price),
            stop_loss=sl_price,
            take_profit=tp1,
            is_spot=is_spot
        )

        send_telegram_message(
            f"✅ <b>Trade Executed:</b> {symbol}\n"
            f"📈 Entry: {entry_price}\n"
            f"🎯 TP1: {tp1}, TP2: {tp2}\n"
            f"🛑 SL: {sl_price}\n"
            f"📊 Risk: {max_risk*100:.1f}%, Size: {qty}\n"
            f"{'📍 Spot' if is_spot else '📍 Futures'}"
        )
    except Exception as e:
        send_telegram_message(f"❌ Trade execution failed for {symbol}: {str(e)}")
