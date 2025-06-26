# bybit_api.py - Optimized version with reduced balance API calls

import asyncio
import time
import traceback
from logger import log

# Import the global balance manager
try:
    from balance_manager import get_cached_balance
    BALANCE_MANAGER_AVAILABLE = True
    log("✅ Using optimized balance manager")
except ImportError:
    BALANCE_MANAGER_AVAILABLE = False
    log("⚠️ Balance manager not available, using legacy balance caching")

# Legacy balance cache (fallback if balance_manager is not available)
_legacy_balance_cache = {
    "balance": None,
    "timestamp": 0,
    "ttl": 60  # 60 seconds TTL
}

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
        
        age = current_time - cache["timestamp"]
        log(f"💰 Using cached balance: {cache['balance']} USDT (age: {age:.0f}s, caller: {caller_name})")
        return cache["balance"]
    
    try:
        log(f"🔄 Fetching fresh balance (caller: {caller_name})")
        
        response = await signed_request("GET", "/v5/account/wallet-balance", {
            "accountType": "UNIFIED"
        })
        
        # Reduce logging to avoid spam - only log the parsed result, not full response
        if response.get("retCode") != 0:
            log(f"❌ Failed to fetch unified wallet balance: {response.get('retMsg')}", level="ERROR")
            return cache["balance"] if cache["balance"] is not None else 0.0
                
        # Parse balance efficiently
        balance = 0.0
        try:
            if "list" in response["result"] and len(response["result"]["list"]) > 0:
                account_info = response["result"]["list"][0]
                
                # Try different balance fields
                for field in ["totalAvailableBalance", "totalMarginBalance", "totalWalletBalance"]:
                    if field in account_info:
                        balance = float(account_info[field])
                        if balance > 0:
                            break
                
                if balance > 0:
                    cache["balance"] = balance
                    cache["timestamp"] = current_time
                    log(f"💰 Fresh balance: {balance} USDT (caller: {caller_name})")
                    return balance
                else:
                    log(f"❌ No valid balance found in response")
                    return cache["balance"] if cache["balance"] is not None else 0.0
            
            log("❌ No account list found in response")
            return cache["balance"] if cache["balance"] is not None else 0.0
            
        except Exception as e:
            log(f"❌ Failed to parse balance response: {e}", level="ERROR")
            return cache["balance"] if cache["balance"] is not None else 0.0
            
    except Exception as e:
        log(f"❌ Failed to fetch balance: {e}", level="ERROR")
        return cache["balance"] if cache["balance"] is not None else 0.0

# Remove the verbose logging from signed_request for balance calls
async def signed_request(method, endpoint, params, suppress_balance_logs=False):
    """
    Make signed request to Bybit API with optional log suppression for balance calls
    """
    try:
        import httpx
        import json
        import hmac
        import hashlib
        from datetime import datetime
        
        # Your existing signed_request logic here...
        # But modify the logging for balance endpoints
        
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        
        if method.upper() == "GET":
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            sign_payload = f"{timestamp}{BYBIT_API_KEY}{recv_window}{query_string}"
            full_url = f"{BYBIT_API_URL}{endpoint}?{query_string}" if query_string else f"{BYBIT_API_URL}{endpoint}"
            body = None
        else:
            body = json.dumps(params, separators=(",", ":"))
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

# Update the call to suppress logs for balance requests
async def signed_request_with_balance_optimization(method, endpoint, params):
    """Wrapper that automatically suppresses logs for balance calls"""
    suppress_logs = "/v5/account/wallet-balance" in endpoint
    return await signed_request(method, endpoint, params, suppress_logs)

# Replace the old get_wallet_balance function
async def get_wallet_balance(force_refresh=False):
    """Get wallet balance - redirects to optimized version"""
    return await get_futures_available_balance(force_refresh, "get_wallet_balance")
