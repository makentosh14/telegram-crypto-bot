# dca_manager.py - Dollar Cost Averaging strategy for handling fakeouts

import asyncio
import json
import time
from datetime import datetime
from logger import log, write_log
from bybit_api import place_market_order, place_stop_loss_with_retry, signed_request
from symbol_info import round_qty
from error_handler import send_telegram_message

# DCA Configuration
DCA_CONFIG = {
    "Scalp": {
        "trigger_drop_pct": 0.5,    # Trigger DCA at -0.5% drop
        "add_size_pct": 50,         # Add 50% of original position
        "max_adds": 2,              # Maximum 2 DCA adds
        "new_sl_adjustment": 0.6,   # New SL at 0.6% below average entry
        "new_tp_adjustment": 1.0    # New TP at 1.0% above average entry
    },
    "Intraday": {
        "trigger_drop_pct": 0.8,    # Trigger DCA at -0.8% drop
        "add_size_pct": 40,         # Add 40% of original position
        "max_adds": 3,              # Maximum 3 DCA adds
        "new_sl_adjustment": 0.8,   # New SL at 0.8% below average entry
        "new_tp_adjustment": 1.5    # New TP at 1.5% above average entry
    },
    "Swing": {
        "trigger_drop_pct": 1.5,    # Trigger DCA at -1.5% drop
        "add_size_pct": 30,         # Add 30% of original position
        "max_adds": 3,              # Maximum 3 DCA adds
        "new_sl_adjustment": 1.2,   # New SL at 1.2% below average entry
        "new_tp_adjustment": 3.0    # New TP at 3.0% above average entry
    }
}

# Track DCA operations
dca_tracking = {}

class DCAManager:
    def __init__(self):
        self.active_dca = {}
        self.dca_history = {}
        
    async def check_dca_opportunity(self, symbol, trade, current_price):
        """
        Check if a trade qualifies for DCA entry
        
        Args:
            symbol: Trading symbol
            trade: Active trade data
            current_price: Current market price
            
        Returns:
            bool: True if DCA should be triggered
        """
        try:
            # Skip if already exited or no entry price
            if trade.get("exited") or not trade.get("entry_price"):
                return False
                
            # Get trade details
            direction = trade.get("direction", "").lower()
            entry_price = trade.get("entry_price")
            trade_type = trade.get("trade_type", "Intraday")
            
            # Get DCA config for this trade type
            dca_config = DCA_CONFIG.get(trade_type, DCA_CONFIG["Intraday"])
            
            # Check if we've already done maximum DCA adds
            dca_count = trade.get("dca_count", 0)
            if dca_count >= dca_config["max_adds"]:
                return False
            
            # Calculate current drawdown
            if direction == "long":
                drawdown_pct = ((entry_price - current_price) / entry_price) * 100
            else:  # short
                drawdown_pct = ((current_price - entry_price) / entry_price) * 100
            
            # Check if drawdown exceeds trigger threshold
            trigger_threshold = dca_config["trigger_drop_pct"] * (dca_count + 1)
            
            if drawdown_pct >= trigger_threshold:
                # Check cooldown (don't DCA too frequently)
                last_dca_time = trade.get("last_dca_time")
                if last_dca_time:
                    time_since_last = (datetime.utcnow() - datetime.fromisoformat(last_dca_time)).total_seconds()
                    if time_since_last < 300:  # 5 minute cooldown
                        return False
                
                log(f"💰 DCA opportunity for {symbol}: Drawdown {drawdown_pct:.2f}% exceeds threshold {trigger_threshold:.2f}%")
                return True
                
            return False
            
        except Exception as e:
            log(f"❌ Error checking DCA opportunity: {e}", level="ERROR")
            return False
    
    async def execute_dca_add(self, symbol, trade, current_price, account_balance):
        """
        Execute a DCA addition to the position
        
        Args:
            symbol: Trading symbol
            trade: Active trade data
            current_price: Current market price
            account_balance: Current account balance
            
        Returns:
            dict: Updated trade data if successful, None otherwise
        """
        try:
            # Get trade details
            direction = trade.get("direction", "").lower()
            original_qty = trade.get("original_qty") or trade.get("qty")
            current_qty = trade.get("qty")
            entry_price = trade.get("entry_price")
            trade_type = trade.get("trade_type", "Intraday")
            
            # Get DCA config
            dca_config = DCA_CONFIG.get(trade_type, DCA_CONFIG["Intraday"])
            
            # Calculate DCA size
            add_size = original_qty * (dca_config["add_size_pct"] / 100)
            add_size = round_qty(symbol, add_size)
            
            # Check if we have enough balance
            required_margin = (add_size * current_price) / 5  # Assuming 5x leverage
            if required_margin > account_balance * 0.1:  # Don't use more than 10% of balance
                log(f"⚠️ Insufficient balance for DCA: Required ${required_margin:.2f}, limit ${account_balance * 0.1:.2f}")
                return None
            
            # Execute the DCA market order
            side = "Buy" if direction == "long" else "Sell"
            
            log(f"📤 Executing DCA add for {symbol}: {side} {add_size} at ~{current_price}")
            
            result = await place_market_order(
                symbol=symbol,
                side=side,
                qty=str(add_size),
                market_type="linear"
            )
            
            if result.get("retCode") != 0:
                log(f"❌ DCA order failed: {result.get('retMsg')}", level="ERROR")
                return None
            
            # Get actual execution price
            order_data = result.get("result", {})
            dca_price = float(order_data.get("avgPrice") or order_data.get("price") or current_price)
            
            # Calculate new average entry price
            total_cost = (entry_price * original_qty) + (dca_price * add_size)
            new_total_qty = current_qty + add_size
            new_avg_entry = total_cost / new_total_qty
            
            # Update trade data
            trade["entry_price"] = new_avg_entry
            trade["qty"] = new_total_qty
            trade["dca_count"] = trade.get("dca_count", 0) + 1
            trade["last_dca_time"] = datetime.utcnow().isoformat()
            
            # Store original quantity if first DCA
            if "original_qty" not in trade:
                trade["original_qty"] = original_qty
            
            # Add DCA history
            if "dca_history" not in trade:
                trade["dca_history"] = []
            
            trade["dca_history"].append({
                "timestamp": datetime.utcnow().isoformat(),
                "price": dca_price,
                "qty": add_size,
                "new_avg_entry": new_avg_entry
            })
            
            # Calculate new SL and TP based on average entry
            if direction == "long":
                new_sl = new_avg_entry * (1 - dca_config["new_sl_adjustment"] / 100)
                new_tp = new_avg_entry * (1 + dca_config["new_tp_adjustment"] / 100)
            else:  # short
                new_sl = new_avg_entry * (1 + dca_config["new_sl_adjustment"] / 100)
                new_tp = new_avg_entry * (1 - dca_config["new_tp_adjustment"] / 100)
            
            # Cancel old SL order
            if trade.get("sl_order_id"):
                try:
                    await signed_request("POST", "/v5/order/cancel", {
                        "category": "linear",
                        "symbol": symbol,
                        "orderId": trade["sl_order_id"]
                    })
                except:
                    pass
            
            # Place new SL order
            sl_result = await place_stop_loss_with_retry(
                symbol=symbol,
                direction=direction,
                qty=new_total_qty,
                sl_price=new_sl
            )
            
            if sl_result.get("retCode") == 0:
                trade["sl_order_id"] = sl_result.get("result", {}).get("orderId")
                trade["original_sl"] = new_sl
            
            # Update TP levels
            trade["tp1_target"] = new_tp
            
            # Send notification
            await send_telegram_message(
                f"💰 <b>DCA Added</b> for <b>{symbol}</b>\n"
                f"Add Price: {dca_price:.8f}\n"
                f"Add Size: {add_size}\n"
                f"New Avg Entry: {new_avg_entry:.8f}\n"
                f"New Total Size: {new_total_qty}\n"
                f"New SL: {new_sl:.8f}\n"
                f"New TP: {new_tp:.8f}\n"
                f"DCA Count: {trade['dca_count']}/{dca_config['max_adds']}"
            )
            
            log(f"✅ DCA executed for {symbol}: Added {add_size} at {dca_price}, new avg entry: {new_avg_entry}")
            write_log(f"DCA_EXECUTED: {symbol} | Add: {add_size} @ {dca_price} | New Avg: {new_avg_entry}")
            
            return trade
            
        except Exception as e:
            log(f"❌ Error executing DCA: {e}", level="ERROR")
            import traceback
            log(traceback.format_exc(), level="ERROR")
            return None
    
    def get_dca_stats(self, symbol=None):
        """Get DCA statistics for reporting"""
        if symbol:
            return self.dca_history.get(symbol, {})
        return self.dca_history

# Global DCA manager instance
dca_manager = DCAManager()
