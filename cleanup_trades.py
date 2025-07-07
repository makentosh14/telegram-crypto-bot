#!/usr/bin/env python3
"""
cleanup_trades.py - Remove ghost trades and fix position sizes
"""

import asyncio
import json
from datetime import datetime

try:
    from bybit_api import signed_request
    from monitor import active_trades, save_active_trades
    from logger import log
    from dca_manager import DCA_CONFIG
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running this from your bot directory")
    exit(1)

def calculate_expected_dca_size(original_qty, dca_count, dca_config):
    """Calculate expected position size after DCA"""
    if dca_count == 0:
        return original_qty
    
    total_added = original_qty * (dca_config["add_size_pct"] / 100) * dca_count
    return original_qty + total_added

async def cleanup_ghost_trades():
    """Remove trades that don't exist on Bybit"""
    print("👻 Removing ghost trades...")
    
    try:
        # Get actual positions
        response = await signed_request("GET", "/v5/position/list", {
            "category": "linear",
            "settleCoin": "USDT"
        })
        
        if response.get("retCode") != 0:
            print(f"❌ API Error: {response.get('retMsg')}")
            return False
        
        # Get symbols with actual positions
        actual_symbols = set()
        positions = response.get("result", {}).get("list", [])
        
        for pos in positions:
            symbol = pos.get("symbol")
            size = float(pos.get("size", "0"))
            if abs(size) > 0:
                actual_symbols.add(symbol)
        
        # Find and remove ghost trades
        ghost_count = 0
        for symbol, trade in list(active_trades.items()):
            if not trade.get("exited") and symbol not in actual_symbols:
                print(f"👻 Removing ghost trade: {symbol}")
                trade["exited"] = True
                trade["exit_reason"] = "Ghost_Trade_Cleanup"
                trade["exit_time"] = datetime.utcnow().isoformat()
                ghost_count += 1
        
        if ghost_count > 0:
            save_active_trades()
            print(f"✅ Removed {ghost_count} ghost trades")
        else:
            print("✅ No ghost trades found")
        
        return True
        
    except Exception as e:
        print(f"❌ Error removing ghost trades: {e}")
        return False

async def fix_position_sizes():
    """Fix position sizes to match Bybit"""
    print("📏 Fixing position sizes...")
    
    try:
        # Get actual positions
        response = await signed_request("GET", "/v5/position/list", {
            "category": "linear",
            "settleCoin": "USDT"
        })
        
        if response.get("retCode") != 0:
            print(f"❌ API Error: {response.get('retMsg')}")
            return False
        
        # Create position lookup
        bybit_positions = {}
        positions = response.get("result", {}).get("list", [])
        
        for pos in positions:
            symbol = pos.get("symbol")
            size = float(pos.get("size", "0"))
            if abs(size) > 0:
                bybit_positions[symbol] = {
                    "size": abs(size),
                    "avg_price": float(pos.get("avgPrice", "0"))
                }
        
        # Fix size mismatches
        fixes = 0
        for symbol, trade in active_trades.items():
            if trade.get("exited") or symbol not in bybit_positions:
                continue
            
            actual_pos = bybit_positions[symbol]
            actual_size = actual_pos["size"]
            actual_avg_price = actual_pos["avg_price"]
            
            trade_size = trade.get("qty", 0)
            
            # Check if size needs fixing
            if abs(actual_size - trade_size) > 0.01:
                print(f"📏 Fixing {symbol}: {trade_size} → {actual_size}")
                
                trade["qty"] = actual_size
                if actual_avg_price > 0:
                    trade["entry_price"] = actual_avg_price
                
                fixes += 1
        
        if fixes > 0:
            save_active_trades()
            print(f"✅ Fixed {fixes} position sizes")
        else:
            print("✅ All position sizes already correct")
        
        return True
        
    except Exception as e:
        print(f"❌ Error fixing position sizes: {e}")
        return False

async def main():
    """Run all cleanup operations"""
    print("🚀 STARTING TRADE CLEANUP")
    print("=" * 40)
    
    # Step 1: Remove ghost trades
    print("\nStep 1: Remove ghost trades")
    if not await cleanup_ghost_trades():
        print("❌ Failed to remove ghost trades")
        return
    
    # Step 2: Fix position sizes
    print("\nStep 2: Fix position sizes")
    if not await fix_position_sizes():
        print("❌ Failed to fix position sizes")
        return
    
    # Step 3: Final verification
    print("\nStep 3: Final verification")
    active_count = sum(1 for t in active_trades.values() if not t.get("exited"))
    print(f"✅ Bot now shows {active_count} active trades")
    
    print("\n🎉 CLEANUP COMPLETED!")
    print("Your bot should now show correct position counts.")

if __name__ == "__main__":
    asyncio.run(main())
