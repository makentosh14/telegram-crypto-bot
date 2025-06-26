# bybit_api.py - Complete Bybit API implementation with all required functions

import asyncio
import time
import traceback
import json
import hmac
import hashlib
import httpx
import os
from logger import log

# Import the global balance manager
try:
    from balance_manager import get_cached_balance
    BALANCE_MANAGER_AVAILABLE = True
    log("✅ Using optimized balance manager")
except ImportError:
    BALANCE_MANAGER_AVAILABLE = False
    log("⚠️ Balance manager not available, using legacy balance caching")

# Get API credentials from environment
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_API_URL = "https://api.bybit.com"

# Legacy balance cache (fallback if balance_manager is not available)
_legacy_balance_cache = {
    "balance": None,
    "timestamp": 0,
    "ttl": 60  # 60 seconds TTL
}

def create_signature(api_secret, sign_payload):
    """Create signature for API requests"""
    return hmac.new(
        api_secret.encode("utf-8"),
        sign_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

async def signed_request(method, endpoint, params, suppress_balance_logs=False):
    """
    Make signed request to Bybit API with optional log suppression for balance calls
    """
    try:
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        
        if method.upper() == "GET":
            query_string = "&".join(f"{k}={v}" for k, v in params.items()) if params else ""
            sign_payload = f"{timestamp}{BYBIT_API_KEY}{recv_window}{query_string}"
            full_url = f"{BYBIT_API_URL}{endpoint}?{query_string}" if query_string else f"{BYBIT_API_URL}{endpoint}"
            body = None
        else:
            body = json.dumps(params, separators=(",", ":")) if params else "{}"
            sign_payload = f"{timestamp}{BYBIT_API_KEY}{recv_window}{body}"
            full_url = f"{BYBIT_API_URL}{endpoint}"

        signature = create_signature(BYBIT_API_SECRET, sign_payload)

        headers = {
            "X-BAPI-API-KEY": BYBIT_API_KEY,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json"
        }

        # Suppress verbose logging for balance calls
        is_balance_call = "/v5/account/wallet-balance" in endpoint
        
        if not (is_balance_call and suppress_balance_logs):
            log(f"🔗 {method} {full_url}")
            if params:
                safe_params = {k: v for k, v in params.items() if k not in ['apiKey', 'secret']}
                log(f"📦 Params: {json.dumps(safe_params)}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.upper() == "GET":
                response = await client.get(full_url, headers=headers)
            elif method.upper() == "POST":
                response = await client.post(full_url, headers=headers, data=body)
            else:
                raise ValueError("Unsupported HTTP method")

        result = response.json()
        
        # Suppress response logging for balance calls to reduce spam
        if not (is_balance_call and suppress_balance_logs):
            log(f"📨 Response: {result}")
        elif is_balance_call:
            # Just log success/failure for balance calls
            if result.get("retCode") == 0:
                log(f"✅ Balance API call successful")
            else:
                log(f"❌ Balance API call failed: {result.get('retMsg')}")
        
        return result
        
    except Exception as e:
        log(f"❌ API Request Error: {str(e)}", level="ERROR")
        return {"retCode": -1, "retMsg": f"API Request Error: {str(e)}"}

async def get_futures_available_balance(force_refresh=False, caller_name="unknown"):
    """
    Get futures available balance with intelligent caching
    
    Args:
        force_refresh (bool): Force fresh API call
        caller_name (str): Identifier for the calling module
    
    Returns:
        float: Available balance in USDT
    """
    if BALANCE_MANAGER_AVAILABLE:
        # Use the optimized global balance manager
        return await get_cached_balance(force_refresh, caller_name)
    else:
        # Fallback to legacy caching
        return await _get_balance_legacy(force_refresh, caller_name)

async def _get_balance_legacy(force_refresh=False, caller_name="unknown"):
    """Legacy balance fetching with basic caching"""
    global _legacy_balance_cache
    
    current_time = time.time()
    cache = _legacy_balance_cache
    
    # Use cache if valid and not forcing refresh
    if (not force_refresh and 
        cache["balance"] is not None and 
        current_time - cache["timestamp"] < cache["ttl"]):
        log(f"💰 Using cached balance: {cache['balance']} USDT (caller: {caller_name})")
        return cache["balance"]
    
    try:
        log(f"🔄 Fetching fresh balance (caller: {caller_name})")
        
        result = await signed_request("GET", "/v5/account/wallet-balance", {
            "accountType": "UNIFIED"
        }, suppress_balance_logs=True)
        
        if result.get("retCode") == 0:
            accounts = result.get("result", {}).get("list", [])
            for account in accounts:
                coins = account.get("coin", [])
                for coin in coins:
                    if coin.get("coin") == "USDT":
                        balance = float(coin.get("walletBalance", 0))
                        # Update cache
                        cache["balance"] = balance
                        cache["timestamp"] = current_time
                        log(f"💰 Fresh balance retrieved: {balance} USDT (caller: {caller_name})")
                        return balance
            
            log(f"❌ No USDT found in account")
            return cache["balance"] if cache["balance"] is not None else 0.0
            
        log(f"❌ Failed to get balance: {result.get('retMsg')}")
        return cache["balance"] if cache["balance"] is not None else 0.0
        
    except Exception as e:
        log(f"❌ Failed to fetch balance: {e}", level="ERROR")
        return cache["balance"] if cache["balance"] is not None else 0.0

async def place_market_order(symbol, side, qty, market_type="linear"):
    """
    Place a market order
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        side: "Buy" or "Sell"
        qty: Quantity as string
        market_type: Market type ("linear" for futures)
    
    Returns:
        dict: API response
    """
    try:
        params = {
            "category": market_type,
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "IOC"  # Immediate or Cancel for market orders
        }
        
        log(f"🚀 Placing market order: {side} {qty} {symbol}")
        
        result = await signed_request("POST", "/v5/order/create", params)
        
        if result.get("retCode") == 0:
            log(f"✅ Market order placed successfully")
        else:
            log(f"❌ Market order failed: {result.get('retMsg')}", level="ERROR")
        
        return result
        
    except Exception as e:
        log(f"❌ Error placing market order: {e}", level="ERROR")
        return {"retCode": -1, "retMsg": f"Error placing market order: {str(e)}"}

async def place_stop_loss(symbol, direction, qty, sl_price, market_type="linear"):
    """
    Place a stop loss order
    
    Args:
        symbol: Trading symbol
        direction: "long" or "short" 
        qty: Position quantity as string
        sl_price: Stop loss price
        market_type: Market type
    
    Returns:
        dict: API response
    """
    try:
        # Convert direction to side
        side = "Sell" if direction.lower() == "long" else "Buy"
        
        params = {
            "category": market_type,
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "stopLoss": str(sl_price),
            "timeInForce": "GTC"
        }
        
        log(f"🛡️ Placing stop loss: {side} {qty} {symbol} at {sl_price}")
        
        result = await signed_request("POST", "/v5/order/create", params)
        
        if result.get("retCode") == 0:
            log(f"✅ Stop loss placed successfully")
        else:
            log(f"❌ Stop loss failed: {result.get('retMsg')}", level="ERROR")
        
        return result
        
    except Exception as e:
        log(f"❌ Error placing stop loss: {e}", level="ERROR")
        return {"retCode": -1, "retMsg": f"Error placing stop loss: {str(e)}"}

async def place_stop_loss_with_retry(symbol, direction, qty, sl_price, market_type="linear", max_retries=3):
    """
    Place a stop loss order with retry logic
    
    Args:
        symbol: Trading symbol
        direction: "long" or "short"
        qty: Position quantity
        sl_price: Stop loss price
        market_type: Market type
        max_retries: Maximum retry attempts
    
    Returns:
        dict: API response
    """
    for attempt in range(max_retries):
        try:
            result = await place_stop_loss(symbol, direction, qty, sl_price, market_type)
            
            if result.get("retCode") == 0:
                return result
            
            # If not the last attempt, wait and retry
            if attempt < max_retries - 1:
                log(f"⚠️ Stop loss attempt {attempt + 1} failed, retrying in 2 seconds...")
                await asyncio.sleep(2)
                
        except Exception as e:
            log(f"❌ Stop loss attempt {attempt + 1} error: {e}", level="ERROR")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
    
    log(f"❌ Stop loss failed after {max_retries} attempts", level="ERROR")
    return {"retCode": -1, "retMsg": f"Stop loss failed after {max_retries} attempts"}

async def check_order_exists(order_id, symbol, market_type="linear"):
    """
    Check if an order exists
    
    Args:
        order_id: Order ID to check
        symbol: Trading symbol
        market_type: Market type
    
    Returns:
        bool: True if order exists, False otherwise
    """
    try:
        result = await signed_request("GET", "/v5/order/realtime", {
            "category": market_type,
            "symbol": symbol,
            "orderId": order_id
        })
        
        if result.get("retCode") == 0:
            orders = result.get("result", {}).get("list", [])
            return len(orders) > 0
        
        return False
        
    except Exception as e:
        log(f"❌ Error checking order existence: {e}", level="ERROR")
        return False

async def get_wallet_balance(force_refresh=False):
    """Get wallet balance - redirects to optimized version"""
    return await get_futures_available_balance(force_refresh, "get_wallet_balance")

async def signed_request_with_balance_optimization(method, endpoint, params):
    """Wrapper that automatically suppresses logs for balance calls"""
    suppress_logs = "/v5/account/wallet-balance" in endpoint
    return await signed_request(method, endpoint, params, suppress_logs)
