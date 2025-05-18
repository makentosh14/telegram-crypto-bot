
import asyncio
import json
from datetime import datetime

async def test_tp1_trailing_sl():
    """
    Simulate the TP1 and trailing stop logic for a trade
    """
    # Simulate a trade being tracked
    symbol = "BTCUSDT"
    direction = "Long"
    entry_price = 50000
    original_sl = 49000
    tp1_level = entry_price * 1.018  # 1.8% above entry
    qty = 0.01  # Position size
    
    print(f"📊 Test scenario: {direction} trade on {symbol}")
    print(f"📈 Entry: {entry_price}, Original SL: {original_sl}")
    print(f"🎯 TP1 target: {tp1_level} (1.8% from entry)")
    
    # Create a mock trade object similar to what's in the active_trades dict
    trade = {
        "score_history": [8.5],
        "trade_type": "Intraday",
        "entry_price": entry_price,
        "direction": direction,
        "cycles": 0,
        "exited": False,
        "trailing_pct": 0.5,  # 0.5% trailing percentage
        "trailing_sl": None,
        "original_sl": original_sl,
        "tp1_hit": False,
        "tp1_partial_exit": False,
        "tp2_hit": False,
        "sl_order_id": "mock-sl-order-123",
        "qty": qty,
        "break_even_triggered": False,
        "tp1_price": None,
        "tp2_price": None,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "exit_tranches": [0.003, 0.003, 0.004],  # Mock exit tranches
        "smart_pump_alerted": False,
        "in_momentum": False,
        "has_pump_potential": True  # Set to True to test pump-optimized logic
    }
    
    # Step 1: Simulate price moving to TP1
    current_price = tp1_level
    print(f"\n🔄 Step 1: Price moves to TP1: {current_price}")
    print("✅ System should: 1) Take partial profit, 2) Move SL to breakeven, 3) Activate trailing")
    
    # Simulate the TP1 hit logic from monitor.py
    trade["tp1_hit"] = True
    trade["tp1_hit_cycle"] = trade["cycles"]
    trade["break_even_triggered"] = True
    trade["tp1_price"] = current_price
    
    # Simulate executing partial exit (33% of position)
    first_tranche = trade["exit_tranches"][0]
    trade["qty"] -= first_tranche
    trade["tp1_partial_exit"] = True
    
    # Simulate moving SL to breakeven
    new_sl = entry_price
    trade["trailing_sl"] = new_sl
    
    print(f"🔸 Partial exit executed: {first_tranche} (33% of position)")
    print(f"🔸 SL moved to breakeven: {new_sl}")
    print(f"🔸 Remaining position: {trade['qty']}")
    
    # Step 2: Simulate price moving higher after TP1
    current_price = entry_price * 1.03  # 3% above entry
    print(f"\n🔄 Step 2: Price continues higher to {current_price} (3% from entry)")
    
    # Calculate trailing stop using the logic from exit_manager.py
    def calculate_trailing_stop(entry_price, current_price, direction="Long", trailing_pct=0.5):
        # For long positions
        if direction == "Long":
            # Calculate how much we've moved up
            move_up = current_price - entry_price
            # Trail by trailing_pct of this movement
            new_sl = entry_price + (move_up * (1 - trailing_pct/100))
            return round(new_sl, 2)
        # For short positions
        elif direction == "Short":
            # Calculate how much we've moved down
            move_down = entry_price - current_price
            # Trail by trailing_pct of this movement
            new_sl = entry_price - (move_down * (1 - trailing_pct/100))
            return round(new_sl, 2)
        return None
    
    trailing_sl = calculate_trailing_stop(
        entry_price=entry_price,
        current_price=current_price,
        direction=direction,
        trailing_pct=trade["trailing_pct"]
    )
    
    trade["trailing_sl"] = trailing_sl
    print(f"🔸 Trailing SL updated to: {trailing_sl}")
    
    # Calculate how much we're now protecting in profit
    profit_pct = ((trailing_sl - entry_price) / entry_price) * 100
    print(f"🔸 Now protecting {profit_pct:.2f}% profit")
    
    # Step 3: Simulate a pullback
    current_price = current_price * 0.99  # 1% pullback
    print(f"\n🔄 Step 3: Price pulls back to {current_price}")
    
    # Verify SL remains the same (doesn't move lower)
    print(f"🔸 SL should remain at: {trailing_sl} (not moving lower)")
    
    # Step 4: Simulate another push higher
    current_price = entry_price * 1.05  # 5% above entry
    print(f"\n🔄 Step 4: Price pushes higher to {current_price} (5% from entry)")
    
    # Recalculate trailing stop
    new_trailing_sl = calculate_trailing_stop(
        entry_price=entry_price,
        current_price=current_price,
        direction=direction,
        trailing_pct=trade["trailing_pct"]
    )
    
    trade["trailing_sl"] = new_trailing_sl
    print(f"🔸 Trailing SL updated to: {new_trailing_sl}")
    
    # Second tranche exit - simulating a detected pump move
    if len(trade["exit_tranches"]) >= 2:
        second_tranche = trade["exit_tranches"][1]
        trade["qty"] -= second_tranche
        print(f"🔸 Second partial exit executed: {second_tranche} during pump move")
        print(f"🔸 Remaining position: {trade['qty']}")
    
    # Step 5: Simulate a big pullback that hits the trailing stop
    current_price = new_trailing_sl * 0.99
    print(f"\n🔄 Step 5: Price pulls back to {current_price}, hitting trailing SL")
    
    # Check if trailing SL is hit
    trailing_sl_hit = (direction == "Long" and current_price <= new_trailing_sl) or \
                     (direction == "Short" and current_price >= new_trailing_sl)
    
    if trailing_sl_hit:
        # Simulate final exit
        trade["exited"] = True
        final_qty = trade["qty"]
        
        # Calculate overall trade result
        initial_qty = sum(trade["exit_tranches"])
        tranche1_result = first_tranche * (trade["tp1_price"] - entry_price)
        tranche2_result = second_tranche * (current_price * 1.01 - entry_price)  # Assume second exit at slightly higher price
        tranche3_result = final_qty * (new_trailing_sl - entry_price)
        
        total_profit = tranche1_result + tranche2_result + tranche3_result
        profit_pct = (total_profit / (initial_qty * entry_price)) * 100
        
        print("✅ Trailing SL hit - exiting final position")
        print(f"🔸 Final exit quantity: {final_qty}")
        print(f"📊 Trade Summary:")
        print(f"  - First exit (33%): +{(trade['tp1_price'] - entry_price) / entry_price * 100:.2f}%")
        print(f"  - Second exit (33%): +{((current_price * 1.01) - entry_price) / entry_price * 100:.2f}%")
        print(f"  - Final exit (34%): +{(new_trailing_sl - entry_price) / entry_price * 100:.2f}%")
        print(f"  - Overall result: +{profit_pct:.2f}%")

print("🚀 Starting TP1 & Trailing Stop Test...\n")
asyncio.run(test_tp1_trailing_sl())
