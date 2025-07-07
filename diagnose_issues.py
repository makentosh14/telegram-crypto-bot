#!/usr/bin/env python3
"""
diagnose_issues.py - Check current state of trades and positions
"""

import asyncio
import json
from datetime import datetime

try:
    from bybit_api import signed_request
    from monitor import active_trades
    from logger import log
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running this from your bot directory")
    exit(1)

async def diagnose_current_state():
    """Diagnose current issues"""
    print("🔍 DIAGNOSING TRADING BOT ISSUES")
    print("=" * 50)
    
    # Step 1: Check active_trades in memory
    print(f"\n📊 STEP 1: Active trades in bot memory")
    active_count = 0
    exited_count = 0
    
    print(f"Total trades in active_trades dict: {len(active_trades)}")
    
    for symbol, trade in active_trades.items():
        if trade.get("exited"):
            exited_count += 1
        else:
            active_count += 1
            qty = trade.get("qty", 0)
            dca_count = trade.get("dca_count", 0)
            original_qty = trade.get("original_qty", "N/A")
            print(f"  {symbol}: qty={qty}, dca_count={dca_count}, original_qty={original_qty}")
    
    print(f"Active (not exited): {active_count}")
    print(f"Exited: {exited_count}")
    
    # Step 2: Check actual positions on Bybit
    print(f"\n📊 STEP 2: Actual positions on Bybit")
    try:
        response = await signed_request("GET", "/v5/position/list", {
            "category": "linear",
            "settleCoin": "USDT"
        })
        
        if response.get("retCode") != 0:
            print(f"❌ API Error: {response.get('retMsg')}")
            return
        
        positions = response.get("result", {}).get("list", [])
        actual_positions = []
        
        print(f"Total positions returned by API: {len(positions)}")
        
        for pos in positions:
            symbol = pos.get("symbol")
            size = float(pos.get("size", "0"))
            if abs(size) > 0:
                actual_positions.append({
                    "symbol": symbol,
                    "size": abs(size),
                    "side": pos.get("side"),
                    "avg_price": float(pos.get("avgPrice", "0"))
                })
                print(f"  {symbol}: size={abs(size)}, side={pos.get('side')}, avg_price={pos.get('avgPrice')}")
        
        print(f"Active positions on Bybit: {len(actual_positions)}")
        
    except Exception as e:
        print(f"❌ Error getting Bybit positions: {e}")
        return
    
    # Step 3: Compare and find mismatches
    print(f"\n🔍 STEP 3: Finding mismatches")
    
    # Find ghost trades (in bot but not on Bybit)
    ghost_trades = []
    for symbol, trade in active_trades.items():
        if not trade.get("exited"):
            found_on_bybit = any(pos["symbol"] == symbol for pos in actual_positions)
            if not found_on_bybit:
                ghost_trades.append(symbol)
    
    if ghost_trades:
        print(f"👻 Ghost trades (in bot but not on Bybit): {len(ghost_trades)}")
        for symbol in ghost_trades:
            print(f"  - {symbol}")
    else:
        print("✅ No ghost trades found")
    
    # Find size mismatches
    size_mismatches = []
    for pos in actual_positions:
        symbol = pos["symbol"]
        if symbol in active_trades and not active_trades[symbol].get("exited"):
            trade = active_trades[symbol]
            trade_size = trade.get("qty", 0)
            actual_size = pos["size"]
            
            if abs(actual_size - trade_size) > 0.01:  # More than 0.01 difference
                size_mismatches.append({
                    "symbol": symbol,
                    "trade_size": trade_size,
                    "actual_size": actual_size,
                    "difference": actual_size - trade_size,
                    "dca_count": trade.get("dca_count", 0)
                })
    
    if size_mismatches:
        print(f"📏 Size mismatches: {len(size_mismatches)}")
        for mismatch in size_mismatches:
            print(f"  {mismatch['symbol']}: bot={mismatch['trade_size']}, bybit={mismatch['actual_size']}, diff={mismatch['difference']:.4f}, dca_count={mismatch['dca_count']}")
    else:
        print("✅ No size mismatches found")
    
    # Step 4: Summary
    print(f"\n📋 SUMMARY")
    print(f"Bot says: {active_count} active trades")
    print(f"Bybit has: {len(actual_positions)} actual positions")
    print(f"Ghost trades to remove: {len(ghost_trades)}")
    print(f"Size mismatches to fix: {len(size_mismatches)}")
    
    if len(ghost_trades) > 0 or len(size_mismatches) > 0:
        print(f"\n🔧 RECOMMENDED ACTIONS:")
        if ghost_trades:
            print(f"1. Remove {len(ghost_trades)} ghost trades")
        if size_mismatches:
            print(f"2. Fix {len(size_mismatches)} size mismatches")
    else:
        print(f"\n✅ No issues found!")

if __name__ == "__main__":
    asyncio.run(diagnose_current_state())
