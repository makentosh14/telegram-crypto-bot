# check_verification.py - Check if position verification is working

import asyncio
import json
import logging
import sys
import traceback
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import bot modules - adjust if needed
try:
    from trade_verification import verify_position_and_orders
    from bybit_api import signed_request
    from monitor import active_trades
    from logger import log
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.error("Make sure you're running this from your bot directory")
    sys.exit(1)

async def test_verification():
    logger.info("🔍 Testing position verification...")
    
    # 1. Count active trades in memory
    active_count = sum(1 for t in active_trades.values() if not t.get("exited"))
    logger.info(f"📊 Active trades in memory: {active_count}")
    
    # 2. Get actual positions from Bybit
    try:
        response = await signed_request("GET", "/v5/position/list", {"category": "linear"})
        if response.get("retCode") != 0:
            logger.error(f"API error: {response.get('retMsg')}")
            return
            
        positions = response.get("result", {}).get("list", [])
        active_positions = [p.get("symbol") for p in positions if abs(float(p.get("size", "0"))) > 0]
        logger.info(f"📊 Actual positions on Bybit: {len(active_positions)}")
        logger.info(f"Active positions: {active_positions}")
        
        # 3. Test verification on one position
        if active_positions:
            test_symbol = active_positions[0]
            if test_symbol in active_trades:
                logger.info(f"🧪 Testing verification on {test_symbol}...")
                result = await verify_position_and_orders(test_symbol, active_trades[test_symbol], auto_repair=False)
                logger.info(f"Verification result: {result}")
            else:
                logger.warning(f"⚠️ Position {test_symbol} exists on Bybit but not in bot memory")
                
        # 4. Check for ghost trades
        ghost_trades = []
        for symbol in active_trades:
            if not active_trades[symbol].get("exited") and symbol not in active_positions:
                ghost_trades.append(symbol)
                
        if ghost_trades:
            logger.warning(f"⚠️ Found {len(ghost_trades)} ghost trades (in memory but not on Bybit)")
            logger.warning(f"Sample: {ghost_trades[:5]}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(test_verification())
