import httpx
import hmac
import hashlib
import json
import time
from logger import log

# === CONFIG ===
BYBIT_API_URL = "https://api.bybit.com"
# Replace with your API keys - DO NOT expose these in code
BYBIT_API_KEY = "NuGJJSlzNeQG2bMb8h"  
BYBIT_API_SECRET = "njckVADwWy8YQ3BbcXrgkp68yw1r6lYyGedj"  

# === SIGNATURE UTILITY ===
def create_signature(secret, payload):
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

# === SIGNATURE UTILITY ===
def create_signature(secret, payload):
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

# === SIGNED REQUEST WRAPPER ===
async def signed_request(method, endpoint, params=None):
    try:
        if params is None:
            params = {}

        url = BYBIT_API_URL + endpoint
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"

        if method.upper() == "GET":
            query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            sign_payload = f"{timestamp}{BYBIT_API_KEY}{recv_window}{query_string}"
            full_url = f"{url}?{query_string}" if query_string else url
            body = None
        else:
            body = json.dumps(params, separators=(",", ":"))
            sign_payload = f"{timestamp}{BYBIT_API_KEY}{recv_window}{body}"
            full_url = url

        signature = create_signature(BYBIT_API_SECRET, sign_payload)

        headers = {
            "X-BAPI-API-KEY": BYBIT_API_KEY,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json"
        }

        log(f"🔗 {method} {full_url}")
        # Avoid logging sensitive info
        log(f"📦 Params: {json.dumps({k: v for k, v in params.items() if k not in ['apiKey', 'secret']})}" if params else "📦 No params")

        async with httpx.AsyncClient(timeout=30.0) as client:  # Added timeout to prevent hanging
            if method.upper() == "GET":
                response = await client.get(full_url, headers=headers)
            elif method.upper() == "POST":
                response = await client.post(full_url, headers=headers, data=body)
            else:
                raise ValueError("Unsupported HTTP method")

        result = response.json()
        log(f"📨 Response: {result}")
        return result
    except Exception as e:
        log(f"❌ API Request Error: {str(e)}", level="ERROR")
        return {"retCode": -1, "retMsg": f"API Request Error: {str(e)}"}

# === BALANCE FUNCTIONS ===
async def get_wallet_balance():
    try:
        return await signed_request("GET", "/v5/account/wallet-balance", {
            "accountType": "UNIFIED"
        })
    except Exception as e:
        log(f"❌ Failed to get wallet balance: {e}", level="ERROR")
        return {"retCode": -1, "retMsg": str(e)}

# === FUTURES BALANCE FUNCTION (FIXED DUPLICATE) ===
async def get_futures_available_balance():
    try:
        response = await signed_request("GET", "/v5/account/wallet-balance", {
            "accountType": "CONTRACT",  # Specifically request CONTRACT account type
            "coin": "USDT"  # Specifically request USDT balance
        })
        
        log(f"📊 Futures balance response: {response}")
        
        if response.get("retCode") != 0:
            log(f"❌ Failed to fetch futures wallet balance: {response.get('retMsg')}", level="ERROR")
            
            # Try fallback to UNIFIED account if CONTRACT fails
            fallback = await signed_request("GET", "/v5/account/wallet-balance", {
                "accountType": "UNIFIED"
            })
            
            log(f"📊 Fallback balance response: {fallback}")
            
            if fallback.get("retCode") != 0:
                log(f"❌ All balance fetch attempts failed", level="ERROR")
                return 0.0
                
            try:
                # Try to get USDT from UNIFIED account
                usdt = next(
                    coin for coin in fallback["result"]["list"][0]["coin"] if coin["coin"] == "USDT"
                )
                balance = float(usdt.get("availableToTrade", 0))
                log(f"💰 Using fallback UNIFIED USDT balance: {balance}")
                return balance
            except Exception as e:
                log(f"❌ Failed to extract USDT from fallback: {e}", level="ERROR")
                return 0.0
                
        # Parse CONTRACT account USDT balance
        try:
            if "list" in response["result"] and len(response["result"]["list"]) > 0:
                account_info = response["result"]["list"][0]
                
                # Check if we have a direct USDT coin entry
                if "coin" in account_info and len(account_info["coin"]) > 0:
                    usdt_coins = [coin for coin in account_info["coin"] if coin["coin"] == "USDT"]
                    
                    if usdt_coins:
                        usdt = usdt_coins[0]
                        # Try multiple possible field names for available balance
                        available = usdt.get("availableBalance", usdt.get("walletBalance", usdt.get("equity", usdt.get("available", 0))))
                        balance = float(available)
                        log(f"💰 Using CONTRACT USDT balance: {balance}")
                        return balance
                
                # Fallback to account-level available balance
                if "availableBalance" in account_info:
                    balance = float(account_info["availableBalance"])
                    log(f"💰 Using CONTRACT account balance: {balance}")
                    return balance
            
            log("⚠️ No suitable balance field found in response")
            return 0.0
            
        except Exception as e:
            log(f"❌ Failed to parse CONTRACT balance: {e}", level="ERROR")
            
            # One more fallback attempt - try to get any available balance we can find
            try:
                if "list" in response["result"] and len(response["result"]["list"]) > 0:
                    account = response["result"]["list"][0]
                    for key in ["availableBalance", "totalAvailableBalance", "walletBalance"]:
                        if key in account and float(account[key]) > 0:
                            balance = float(account[key])
                            log(f"💰 Using fallback balance field {key}: {balance}")
                            return balance
            except:
                pass
                
            return 0.0
            
    except Exception as e:
        log(f"❌ Failed to fetch available futures balance: {e}", level="ERROR")
        log(f"💡 Full error: {traceback.format_exc()}")
        return 0.0

# === TRADE FUNCTION ===
async def place_market_order(symbol, side, qty, market_type="linear", reduce_only=False):
    return await signed_request("POST", "/v5/order/create", {
        "category": market_type,
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": str(qty),
        "timeInForce": "IOC",
        "reduceOnly": reduce_only
    })

# === STOP LOSS FUNCTIONS ===
async def place_stop_loss(symbol, direction, qty, sl_price, market_type="linear"):
    """
    Places a stop loss order for the given symbol
    
    Args:
        symbol: Trading pair symbol
        direction: 'long' or 'short'
        qty: Position quantity
        sl_price: Stop loss price
        market_type: 'linear' for USDT Perpetual
        
    Returns:
        API response from Bybit
    """
    side = "Sell" if direction.lower() == "long" else "Buy"
    trigger_direction = 1 if direction.lower() == "long" else 2
    
    # Verify the SL price is valid
    try:
        ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": market_type, "symbol": symbol})
        mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
        
        # IMPORTANT FIX: Make sure SL is on the correct side of mark price
        if direction.lower() == "long" and sl_price >= mark_price:
            # For long positions, SL must be below current price
            sl_price = round(mark_price * 0.995, 6)  # 0.5% below mark price
            log(f"⚠️ Adjusted long SL to be below mark price: {sl_price}", level="WARN")
        elif direction.lower() == "short" and sl_price <= mark_price:
            # For short positions, SL must be above current price
            sl_price = round(mark_price * 1.005, 6)  # 0.5% above mark price
            log(f"⚠️ Adjusted short SL to be above mark price: {sl_price}", level="WARN")
    except Exception as e:
        log(f"❌ Failed to fetch mark price for SL check: {e}", level="ERROR")
    
    sl_payload = {
        "category": market_type,
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "triggerPrice": str(sl_price),
        "triggerDirection": trigger_direction,
        "triggerBy": "MarkPrice",  # Use MarkPrice for more reliable triggering
        "qty": str(qty),
        "reduceOnly": True,
        "timeInForce": "GTC",
        "orderFilter": "Stop"
    }
    
    log(f"🛡️ Placing SL order for {symbol}: {sl_payload}")
    result = await signed_request("POST", "/v5/order/create", sl_payload)
    
    if result.get("retCode") != 0:
        log(f"❌ Failed to place SL order: {result.get('retMsg')}", level="ERROR")
        
        # Retry with LastPrice if MarkPrice failed
        sl_payload["triggerBy"] = "LastPrice"
        log(f"🔄 Retrying SL with LastPrice: {sl_payload}")
        result = await signed_request("POST", "/v5/order/create", sl_payload)
    
    return result

async def check_order_exists(order_id, symbol, category="linear"):
    """Check if a specific order exists"""
    try:
        response = await signed_request("GET", "/v5/order/realtime", {
            "category": category,
            "symbol": symbol,
            "orderId": order_id
        })
        
        if response.get("retCode") == 0:
            orders = response.get("result", {}).get("list", [])
            return len(orders) > 0 and orders[0].get("orderId") == order_id
        return False
    except Exception as e:
        log(f"❌ Failed to check order {order_id}: {e}", level="ERROR")
        return False
