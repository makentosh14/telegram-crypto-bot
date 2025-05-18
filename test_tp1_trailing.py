import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

# Mock necessary components to avoid dependency issues
class MockCandles:
    def __init__(self, base_price, direction="up"):
        self.base_price = base_price
        self.direction = direction
        self.candles = self._generate_candles()
        
    def _generate_candles(self):
        """Generate 30 mock candles"""
        candles = []
        price = self.base_price
        
        for i in range(30):
            # Create price movement pattern
            if self.direction == "up":
                open_price = price
                close_price = price * (1 + 0.002 * (i % 3 + 1))  # 0.2-0.6% up
                high_price = close_price * 1.001
                low_price = open_price * 0.999
            else:
                open_price = price
                close_price = price * (1 - 0.002 * (i % 3 + 1))  # 0.2-0.6% down
                high_price = open_price * 1.001
                low_price = close_price * 0.999
            
            # Create volume pattern (increasing for momentum detection)
            base_volume = 100
            volume = base_volume * (1 + (i / 30))
            
            # For momentum testing, create larger volume and stronger moves in later candles
            if i > 20:
                volume *= 2
                if self.direction == "up":
                    close_price = open_price * (1 + 0.004 * (i % 3 + 1))
                    high_price = close_price * 1.002
                else:
                    close_price = open_price * (1 - 0.004 * (i % 3 + 1))
                    low_price = close_price * 0.998
            
            candle = {
                'timestamp': int((datetime.now() - timedelta(minutes=30-i)).timestamp() * 1000),
                'open': str(open_price),
                'high': str(high_price),
                'low': str(low_price),
                'close': str(close_price),
                'volume': str(volume)
            }
            
            candles.append(candle)
            
            # Update for next candle
            price = close_price
            
        return candles
    
    def update_price(self, new_price):
        """Update the latest candle with a new closing price"""
        if len(self.candles) > 0:
            self.candles[-1]['close'] = str(new_price)
            
            # Update high/low if needed
            if new_price > float(self.candles[-1]['high']):
                self.candles[-1]['high'] = str(new_price)
            if new_price < float(self.candles[-1]['low']):
                self.candles[-1]['low'] = str(new_price)
    
    def add_candle(self, price_change_pct=0.002):
        """Add a new candle with specified price change"""
        last_close = float(self.candles[-1]['close'])
        
        if self.direction == "up":
            open_price = last_close
            close_price = last_close * (1 + price_change_pct)
            high_price = close_price * 1.001
            low_price = open_price * 0.999
        else:
            open_price = last_close
            close_price = last_close * (1 - price_change_pct)
            high_price = open_price * 1.001
            low_price = close_price * 0.999
        
        # Create volume (increasing for momentum detection)
        volume = float(self.candles[-1]['volume']) * 1.1
        
        new_candle = {
            'timestamp': int(datetime.now().timestamp() * 1000),
            'open': str(open_price),
            'high': str(high_price),
            'low': str(low_price),
            'close': str(close_price),
            'volume': str(volume)
        }
        
        self.candles.append(new_candle)
        return close_price

# Mock functions for testing
async def mock_update_stop_loss(symbol, trade, new_sl_price):
    """Mock function for updating stop loss order"""
    old_sl = trade.get("trailing_sl")
    trade["trailing_sl"] = new_sl_price
    print(f"🔄 SL Update: {symbol} - Old: {old_sl} → New: {new_sl_price}")
    return True

async def mock_execute_partial_exit(symbol, trade, exit_percentage):
    """Mock function for executing partial exit"""
    total_qty = trade.get("qty", 0)
    exit_qty = total_qty * (exit_percentage / 100)
    trade["qty"] = trade["qty"] - exit_qty
    print(f"💰 Partial Exit: {symbol} - {exit_percentage}% ({exit_qty} of {total_qty})")
    return True

def calculate_atr(candles, period=14):
    """Simplified ATR calculation for testing"""
    if len(candles) < period + 1:
        return 0.0
        
    trs = []
    for i in range(1, period + 1):
        high = float(candles[-i]['high'])
        low = float(candles[-i]['low'])
        prev_close = float(candles[-i-1]['close'])
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)
    
    return sum(trs) / len(trs)

def detect_momentum_surge(candles, lookback=5):
    """
    Detect if price is showing strong momentum based on recent candles.
    Returns True if strong momentum is detected
    """
    if len(candles) < lookback + 5:
        return False
        
    # Get recent candles and slightly older candles for comparison
    recent = candles[-lookback:]
    prior = candles[-(lookback+5):-lookback]
    
    # Calculate average volume increase
    recent_vol_avg = sum(float(c['volume']) for c in recent) / len(recent)
    prior_vol_avg = sum(float(c['volume']) for c in prior) / len(prior)
    vol_increase = recent_vol_avg / prior_vol_avg if prior_vol_avg > 0 else 1
    
    # Calculate price momentum
    recent_opens = [float(c['open']) for c in recent]
    recent_closes = [float(c['close']) for c in recent]
    
    # Count consecutive up/down candles
    if recent_closes[-1] > recent_opens[-1]:  # Current candle is up
        consecutive_up = 1
        for i in range(len(recent)-2, -1, -1):
            if recent_closes[i] > recent_opens[i]:
                consecutive_up += 1
            else:
                break
                
        # Strong momentum criteria: 3+ consecutive up candles with 2x+ volume
        if consecutive_up >= 3 and vol_increase >= 2.0:
            return True
    
    # For downward momentum (for shorts)
    if recent_closes[-1] < recent_opens[-1]:  # Current candle is down
        consecutive_down = 1
        for i in range(len(recent)-2, -1, -1):
            if recent_closes[i] < recent_opens[i]:
                consecutive_down += 1
            else:
                break
                
        # Strong momentum criteria: 3+ consecutive down candles with 2x+ volume
        if consecutive_down >= 3 and vol_increase >= 2.0:
            return True
    
    return False

def calculate_adaptive_trailing(symbol, candles, direction, current_price, base_trail_pct):
    """
    Adjust trailing percentage based on recent volatility and momentum.
    Returns an adjusted trailing percentage
    """
    # Use 7-period ATR for current volatility
    atr_short = calculate_atr(candles, period=7)
    # Use 21-period ATR for baseline volatility
    atr_long = calculate_atr(candles, period=21)
    
    volatility_factor = 1.0
    
    if atr_short and atr_long and atr_long > 0:
        # Calculate volatility ratio
        vol_ratio = atr_short / atr_long
        
        if vol_ratio > 1.5:
            # Higher volatility = wider trailing to avoid noise
            volatility_factor = 1.3
            print(f"📊 High volatility detected for {symbol}: {vol_ratio:.2f}x - widening trail")
        elif vol_ratio < 0.7:
            # Lower volatility = tighter trailing to lock profits
            volatility_factor = 0.8
            print(f"📊 Low volatility detected for {symbol}: {vol_ratio:.2f}x - tightening trail")
    
    # Check for momentum surge - uses wider trailing to catch bigger moves
    if detect_momentum_surge(candles):
        momentum_factor = 1.5  # Much wider trail during strong momentum
        print(f"🚀 Momentum surge detected for {symbol} - using wider trailing ({momentum_factor}x)")
        volatility_factor = max(volatility_factor, momentum_factor)
    
    adjusted_pct = base_trail_pct * volatility_factor
    print(f"🔄 Adjusted trailing % for {symbol}: {base_trail_pct:.2f}% → {adjusted_pct:.2f}%")
    return adjusted_pct

def should_trail_stop(symbol, entry_price, current_price, direction="long", candles=None, trigger_pct=0.018, trail_pct=0.009, current_trailing_sl=None):
    """
    Checks if trailing stop should activate:
      - price exceeds trigger threshold
      - volume is at least 1.2x average (optional)
      - SL must improve (never downgrade)
      - Adjusts trailing based on volatility and momentum
    """
    # Check if we have enough volume to justify trailing
    if candles:
        avg_volume = sum(float(c['volume']) for c in candles[-15:]) / 15
        current_volume = float(candles[-1]['volume'])
        
        # Check for mega pump pattern - in strong momentum don't require high volume for trailing
        in_momentum_surge = detect_momentum_surge(candles)
        
        if current_volume < avg_volume * 1.2 and not in_momentum_surge:
            print(f"🔕 Volume too low for trailing: {current_volume:.2f} < 1.2x avg {avg_volume:.2f}")
            return None
            
        # Use adaptive trailing based on volatility
        adjusted_trail_pct = calculate_adaptive_trailing(symbol, candles, direction, current_price, trail_pct)
    else:
        adjusted_trail_pct = trail_pct

    # Calculate potential new SL value
    new_sl = calculate_trailing_stop(symbol, entry_price, current_price, direction, trigger_pct, adjusted_trail_pct)
    if not new_sl:
        return None

    # Only update SL if it's better (tighter) than current
    if current_trailing_sl:
        if direction.lower() == "long" and new_sl <= current_trailing_sl:
            return None
        if direction.lower() == "short" and new_sl >= current_trailing_sl:
            return None

    return new_sl

def calculate_trailing_stop(symbol, entry_price, current_price, direction="long", trigger_pct=0.01, trail_pct=0.005):
    """
    Calculates new SL price using trailing logic once trigger threshold is passed.
    """
    # For long positions
    if direction.lower() == "long":
        # Check if price has moved up enough to trigger trailing
        if current_price > entry_price * (1 + trigger_pct):
            # Calculate trailing stop below current price
            new_sl = round(current_price * (1 - trail_pct/100), 6)
            print(f"🔐 Trailing SL calc for {symbol} (long): new SL = {new_sl}")
            return new_sl
    # For short positions
    elif direction.lower() == "short":
        # Check if price has moved down enough to trigger trailing
        if current_price < entry_price * (1 - trigger_pct):
            # Calculate trailing stop above current price
            new_sl = round(current_price * (1 + trail_pct/100), 6)
            print(f"🔐 Trailing SL calc for {symbol} (short): new SL = {new_sl}")
            return new_sl

    # Return None if trailing should not be activated yet
    return None

async def simulate_tp1_and_trailing_test():
    """
    Simulate a full TP1 and trailing stop test with mock data
    """
    # Test configuration
    symbol = "BTCUSDT"
    entry_price = 50000
    direction = "Long"
    original_sl = 49000  # 2% below entry
    tp1_level = entry_price * 1.018  # 1.8% above entry for TP1
    trailing_pct = 0.5  # 0.5% trailing percentage
    
    print("=" * 80)
    print(f"🧪 TP1 & TRAILING STOP TEST - {symbol} {direction}")
    print("=" * 80)
    print(f"📉 Entry Price: {entry_price}")
    print(f"📉 Original SL: {original_sl} ({((original_sl - entry_price) / entry_price) * 100:.2f}%)")
    print(f"📈 TP1 Target: {tp1_level} ({((tp1_level - entry_price) / entry_price) * 100:.2f}%)")
    print(f"📊 Trailing %: {trailing_pct}%")
    print("-" * 80)
    
    # Create a mock trade object similar to what's in active_trades
    trade = {
        "score_history": [7.5],
        "trade_type": "Intraday",
        "entry_price": entry_price,
        "direction": direction,
        "cycles": 0,
        "exited": False,
        "trailing_pct": trailing_pct,
        "trailing_sl": None,
        "original_sl": original_sl,
        "tp1_hit": False,
        "tp1_partial_exit": False,
        "tp2_hit": False,
        "tp2_exit_executed": False,
        "sl_order_id": "mock-sl-order-123",
        "qty": 0.01,  # 0.01 BTC position
        "break_even_triggered": False,
        "tp1_price": None,
        "tp2_price": None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exit_tranches": [0.003, 0.003, 0.004],  # Mock exit tranches
        "smart_pump_alerted": False,
        "in_momentum": False,
        "has_pump_potential": True  # Set to True to test pump-optimized logic
    }
    
    # Create mock candles for testing
    mock_candles = MockCandles(entry_price, direction="up")
    candles_by_tf = {'1': mock_candles.candles}
    
    # STEP 1: Normal Trading Until TP1
    print("\n[STEP 1] SIMULATING PRICE MOVEMENT UNTIL TP1\n")
    
    current_price = entry_price
    steps_to_tp1 = 5
    
    for i in range(steps_to_tp1):
        # Simulate price movement (0.4% per step up to TP1)
        price_change = (tp1_level - current_price) / (steps_to_tp1 - i)
        price_change_pct = price_change / current_price
        
        current_price = mock_candles.add_candle(price_change_pct)
        candles_by_tf = {'1': mock_candles.candles}
        
        print(f"📊 Price update #{i+1}: {current_price:.2f} ({((current_price - entry_price) / entry_price) * 100:.2f}% from entry)")
        
        # Check for TP1 hit
        if not trade.get("tp1_hit") and current_price >= tp1_level:
            print("\n🎯 TP1 HIT DETECTED!")
            
            # Mark TP1 as hit
            trade["tp1_hit"] = True
            trade["tp1_hit_cycle"] = trade["cycles"]
            trade["break_even_triggered"] = True
            trade["tp1_price"] = current_price
            
            # Execute partial exit for first tranche
            await mock_execute_partial_exit(symbol, trade, 33)  # Exit 33% of position
            trade["tp1_partial_exit"] = True
            
            # Move SL to breakeven
            await mock_update_stop_loss(symbol, trade, entry_price)
            
            print(f"✅ SL moved to breakeven: {entry_price}")
            print(f"✅ Partial exit executed: 33% of position")
            print(f"✅ Remaining position: {trade['qty']}")
        
        # Update cycle counter
        trade["cycles"] += 1
        
        await asyncio.sleep(0.2)  # Small delay for readability
    
    # STEP 2: After TP1, Continue Price Movement with Trailing SL
    print("\n[STEP 2] SIMULATING CONTINUED PRICE MOVEMENT WITH TRAILING SL\n")
    
    # Target a 5% total move for a good test
    target_price = entry_price * 1.05
    steps_after_tp1 = 8
    
    for i in range(steps_after_tp1):
        # Simulate price movement (gradually moving up to target)
        # For step 5, simulate a small pullback to test trailing behavior
        if i == 4:
            # Small pullback
            current_price = current_price * 0.992  # 0.8% pullback
            mock_candles.update_price(current_price)
            print(f"📉 Simulating pullback: {current_price:.2f} ({((current_price - entry_price) / entry_price) * 100:.2f}% from entry)")
        else:
            # Continue upward
            price_change = (target_price - current_price) / (steps_after_tp1 - i)
            price_change_pct = price_change / current_price
            
            current_price = mock_candles.add_candle(price_change_pct)
            print(f"📈 Price update #{i+1}: {current_price:.2f} ({((current_price - entry_price) / entry_price) * 100:.2f}% from entry)")
            
            # For the middle of the simulation, inject momentum signals for testing
            if i == 2:
                # Artificially boost volume to trigger momentum
                for j in range(5):
                    mock_candles.candles[-j-1]['volume'] = str(float(mock_candles.candles[-j-1]['volume']) * 3)
                    # Make consecutive up candles
                    open_val = float(mock_candles.candles[-j-1]['open'])
                    close_val = float(mock_candles.candles[-j-1]['close'])
                    if close_val <= open_val:
                        mock_candles.candles[-j-1]['close'] = str(open_val * 1.005)  # Ensure candle is up
                
                print("🚀 Artificially injected momentum signals")
        
        # Update candles reference
        candles_by_tf = {'1': mock_candles.candles}
        
        # Check for trailing stop update
        if trade.get("tp1_hit"):
            # Calculate if we should update trailing stop
            new_sl = should_trail_stop(
                symbol=symbol,
                entry_price=entry_price,
                current_price=current_price,
                direction=direction.lower(),
                candles=candles_by_tf['1'],
                trigger_pct=0.018,  # Same as TP1 level (1.8%)
                trail_pct=trade.get("trailing_pct", 0.5),
                current_trailing_sl=trade.get("trailing_sl")
            )
            
            if new_sl and (trade.get("trailing_sl") is None or 
                          (direction.lower() == "long" and new_sl > trade.get("trailing_sl", 0)) or
                          (direction.lower() == "short" and new_sl < trade.get("trailing_sl", 0))):
                
                # Update trailing stop
                await mock_update_stop_loss(symbol, trade, new_sl)
                
                # Calculate profit protected
                profit_pct = ((new_sl - entry_price) / entry_price) * 100
                print(f"✅ Now protecting: {profit_pct:.2f}% profit")
            
            # Check for pump detection and second exit tranche
            if not trade.get("tp2_exit_executed") and detect_momentum_surge(candles_by_tf['1']):
                print("\n🚀 MOMENTUM SURGE DETECTED AFTER TP1!")
                
                if not trade.get("smart_pump_alerted"):
                    trade["smart_pump_alerted"] = True
                    print("📣 Smart Pump Alert triggered!")
                
                # Check if we're far enough from TP1 to take second exit
                current_move = ((current_price - trade["tp1_price"]) / trade["tp1_price"]) * 100
                if current_move >= 1.0:  # At least 1% move after TP1
                    print(f"💰 Significant move after TP1: +{current_move:.2f}%")
                    
                    # Execute second exit tranche
                    await mock_execute_partial_exit(symbol, trade, 50)  # Exit 50% of remaining position
                    trade["tp2_exit_executed"] = True
                    
                    print("✅ Second partial exit executed during momentum surge")
                    print(f"✅ Remaining position: {trade['qty']}")
        
        # Check if trailing SL would be hit
        if trade.get("trailing_sl") and (
            (direction.lower() == "long" and current_price <= trade.get("trailing_sl")) or
            (direction.lower() == "short" and current_price >= trade.get("trailing_sl"))
        ):
            print(f"\n⛔ TRAILING STOP HIT: {current_price:.2f} <= {trade.get('trailing_sl'):.2f}")
            trade["exited"] = True
            
            # Calculate final results
            initial_qty = sum(trade["exit_tranches"])
            final_qty = trade["qty"]
            
            # Calculate profit from each tranche
            tp1_price = trade.get("tp1_price", tp1_level)
            tp1_profit_pct = ((tp1_price - entry_price) / entry_price) * 100
            tp2_price = current_price * 1.005  # Assume slightly better price for 2nd exit
            tp2_profit_pct = ((tp2_price - entry_price) / entry_price) * 100
            final_profit_pct = ((trade.get("trailing_sl") - entry_price) / entry_price) * 100
            
            # Exit remaining position
            print(f"💰 Final position exit: {final_qty}")
            
            print("\n📊 TRADE SUMMARY:")
            print(f"  Initial Position: {initial_qty} {symbol}")
            print(f"  First Exit (33%): {0.003} at {tp1_price:.2f} (+{tp1_profit_pct:.2f}%)")
            if trade.get("tp2_exit_executed"):
                print(f"  Second Exit (~33%): {0.003} at {tp2_price:.2f} (+{tp2_profit_pct:.2f}%)")
            print(f"  Final Exit (~33%): {final_qty} at {trade.get('trailing_sl'):.2f} (+{final_profit_pct:.2f}%)")
            
            # Calculate weighted average result
            if trade.get("tp2_exit_executed"):
                weighted_result = (0.33 * tp1_profit_pct + 0.33 * tp2_profit_pct + 0.34 * final_profit_pct)
            else:
                weighted_result = (0.33 * tp1_profit_pct + 0.67 * final_profit_pct)
                
            print(f"  Overall Result: +{weighted_result:.2f}%")
            break
        
        # Update cycle counter
        trade["cycles"] += 1
        
        await asyncio.sleep(0.2)  # Small delay for readability
    
    print("\n" + "=" * 80)
    if not trade.get("exited"):
        print("🏁 TEST COMPLETED WITHOUT TRAILING SL HIT")
        print(f"  Final Price: {current_price:.2f} ({((current_price - entry_price) / entry_price) * 100:.2f}% from entry)")
        print(f"  Current SL: {trade.get('trailing_sl'):.2f} ({((trade.get('trailing_sl') - entry_price) / entry_price) * 100:.2f}% from entry)")
    else:
        print("🏁 TEST COMPLETED WITH TRAILING SL HIT")
    print("=" * 80)

if __name__ == "__main__":
    # Run the simulation
    asyncio.run(simulate_tp1_and_trailing_test())
