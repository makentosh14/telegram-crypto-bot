from bybit_api import place_order, set_leverage_mode, set_leverage, get_balance
from exit_manager import generate_tp_sl
from risk_manager import calculate_position_size
from telegram_bot import send_telegram_message
from config import QUOTE_ASSET

def execute_trade_if_valid(signal_data, max_risk=0.03):
    try:
        symbol = signal_data['symbol']
        score = signal_data['score']
        tf_scores = signal_data['tf_scores']
        btc_trend = signal_data['btc_trend']
        altseason = signal_data['altseason']

        balance = get_balance()
        if not balance:
            send_telegram_message("❌ Unable to fetch balance.")
            return

        qty, entry_price = calculate_position_size(symbol, balance, max_risk)
        if not qty:
            send_telegram_message(f"⚠️ Skipping {symbol} - unable to calculate size.")
            return

        set_leverage_mode(symbol, mode="Cross")
        set_leverage(symbol, leverage=5)

        tp, sl = generate_tp_sl(symbol, entry_price)

        success, order_response = place_order(
            symbol=symbol,
            side="Buy",
            qty=qty,
            entry_price=entry_price,
            tp=tp,
            sl=sl
        )

        if success:
            msg = (
                f"✅ Trade Executed: {symbol}\n"
                f"🟢 Entry: {entry_price}\n"
                f"🎯 TP: {tp} | 🛑 SL: {sl}\n"
                f"📊 Score: {score} | TFs: {tf_scores}\n"
                f"📈 BTC Trend: {btc_trend}, Altseason: {altseason}\n"
                f"📉 Risk: {max_risk * 100:.1f}% of balance"
            )
            send_telegram_message(msg)
        else:
            send_telegram_message(f"❌ Order failed for {symbol}: {order_response}")
    except Exception as e:
        send_telegram_message(f"❌ Trade execution error: {str(e)}")
