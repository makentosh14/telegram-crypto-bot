import httpx
import hmac
import hashlib
import json
import time
import traceback
import asyncio
from logger import log

# === CONFIG ===
BYBIT_API_URL = "https://api.bybit.com"
# Replace with your API keys - DO NOT expose these in code
BYBIT_API_KEY = "NuGJJSlzNeQG2bMb8h"  
BYBIT_API_SECRET = "njckVADwWy8YQ3BbcXrgkp68yw1r6lYyGedj"  

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
            "accountType": "UNIFIED"
        })
        
        log(f"📊 Unified balance response: {response}")
        
        if response.get("retCode") != 0:
            log(f"❌ Failed to fetch unified wallet balance: {response.get('retMsg')}", level="ERROR")
            return 0.0
                
        try:
            if "list" in response["result"] and len(response["result"]["list"]) > 0:
                account_info = response["result"]["list"][0]
                
                # For margin trading, use totalAvailableBalance (this is what you can trade with)
                if "totalAvailableBalance" in account_info:
                    balance = float(account_info["totalAvailableBalance"])
                    log(f"💰 Margin trading balance (totalAvailableBalance): {balance} USDT")
                    return balance
                
                # Fallback to totalMarginBalance
                elif "totalMarginBalance" in account_info:
                    balance = float(account_info["totalMarginBalance"])
                    log(f"💰 Margin balance (totalMarginBalance): {balance} USDT")
                    return balance
                
                # Last fallback to totalWalletBalance
                elif "totalWalletBalance" in account_info:
                    balance = float(account_info["totalWalletBalance"])
                    log(f"💰 Wallet balance (totalWalletBalance): {balance} USDT")
                    return balance
                
                else:
                    log(f"❌ No recognizable balance fields found in account")
                    return 0.0
            
            log("❌ No account list found in response")
            return 0.0
            
        except Exception as e:
            log(f"❌ Failed to parse unified account balance: {e}", level="ERROR")
            log(f"💡 Full parsing error: {traceback.format_exc()}")
            return 0.0
            
    except Exception as e:
        log(f"❌ Failed to fetch unified account balance: {e}", level="ERROR")
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


async def cleanup_orphaned_stop_orders(symbol=None):
    """
    Clean up orphaned stop orders to prevent hitting the 10 order limit
    """
    try:
        # Get all stop orders
        params = {"category": "linear", "orderFilter": "Stop"}
        if symbol:
            params["symbol"] = symbol
            
        orders_resp = await signed_request("GET", "/v5/order/realtime", params)
        
        if orders_resp.get("retCode") == 0:
            orders = orders_resp.get("result", {}).get("list", [])
            log(f"🧹 Found {len(orders)} stop orders{'for ' + symbol if symbol else ''}")
            
            cancelled_count = 0
            for order in orders:
                order_symbol = order.get("symbol")
                order_id = order.get("orderId")
                
                try:
                    # Cancel the order
                    cancel_resp = await signed_request("POST", "/v5/order/cancel", {
                        "category": "linear",
                        "symbol": order_symbol,
                        "orderId": order_id
                    })
                    
                    if cancel_resp.get("retCode") == 0:
                        cancelled_count += 1
                        log(f"✅ Cancelled orphaned stop order: {order_id} for {order_symbol}")
                    else:
                        log(f"⚠️ Failed to cancel order {order_id}: {cancel_resp.get('retMsg')}")
                        
                    # Brief delay to avoid rate limits
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    log(f"❌ Error cancelling order {order_id}: {e}")
                    
            log(f"🧹 Cleanup complete: Cancelled {cancelled_count} orphaned stop orders")
            return cancelled_count
            
    except Exception as e:
        log(f"❌ Error in stop order cleanup: {e}", level="ERROR")
        return 0

async def cleanup_old_orders():
    """Clean up old/orphaned orders across all symbols"""
    try:
        # Get all open orders
        orders_resp = await signed_request("GET", "/v5/order/realtime", {
            "category": "linear",
            "orderFilter": "Stop"
        })
        
        if orders_resp.get("retCode") == 0:
            orders = orders_resp.get("result", {}).get("list", [])
            log(f"🧹 Found {len(orders)} stop orders to clean up")
            
            for order in orders:
                symbol = order.get("symbol")
                order_id = order.get("orderId")
                
                # Cancel orphaned orders
                await signed_request("POST", "/v5/order/cancel", {
                    "category": "linear",
                    "symbol": symbol,
                    "orderId": order_id
                })
                await asyncio.sleep(0.1)  # Rate limit protection
                
    except Exception as e:
        log(f"❌ Error in cleanup: {e}")

# === STOP LOSS FUNCTIONS ===
async def place_stop_loss(symbol, direction, qty, sl_price, market_type="linear"):
    """
    Enhanced stop loss placement with automatic cleanup and corrected trigger direction
    """
    # STEP 1: Clean up any existing stop orders for this symbol first
    log(f"🧹 Cleaning up existing stop orders for {symbol} before placing new SL")
    await cleanup_orphaned_stop_orders(symbol)
    
    # Brief pause after cleanup
    await asyncio.sleep(1)
    
    side = "Sell" if direction.lower() == "long" else "Buy"
    
    # STEP 2: CORRECTED trigger direction logic
    # For long positions: SL triggers when price FALLS below SL (triggerDirection = 2)
    # For short positions: SL triggers when price RISES above SL (triggerDirection = 1)
    trigger_direction = 2 if direction.lower() == "long" else 1
    
    # STEP 3: Validate the SL price is on correct side of market
    try:
        ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": market_type, "symbol": symbol})
        mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
        
        # Add safety buffer for SL placement
        buffer = 0.005  # 0.5% safety buffer
        
        if direction.lower() == "long" and sl_price >= mark_price:
            old_sl = sl_price
            sl_price = round(mark_price * (1 - buffer), 6)
            log(f"⚠️ Adjusted long SL from {old_sl} to {sl_price} (below mark price {mark_price})", level="WARN")
        elif direction.lower() == "short" and sl_price <= mark_price:
            old_sl = sl_price
            sl_price = round(mark_price * (1 + buffer), 6)
            log(f"⚠️ Adjusted short SL from {old_sl} to {sl_price} (above mark price {mark_price})", level="WARN")
            
    except Exception as e:
        log(f"❌ Failed to validate SL price: {e}", level="ERROR")
    
    # STEP 4: Construct the stop loss order payload
    sl_payload = {
        "category": market_type,
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "triggerPrice": str(sl_price),
        "triggerDirection": trigger_direction,  # FIXED: Correct trigger direction
        "triggerBy": "MarkPrice",
        "qty": str(qty),
        "reduceOnly": True,
        "timeInForce": "GTC",
        "orderFilter": "Stop"
    }
    
    log(f"🛡️ Placing SL order for {symbol}: {direction} | TriggerDir: {trigger_direction} | Price: {sl_price}")
    
    # STEP 5: Place the stop loss order
    result = await signed_request("POST", "/v5/order/create", sl_payload)
    
    if result.get("retCode") != 0:
        error_msg = result.get("retMsg", "Unknown error")
        log(f"❌ Failed to place SL order: {error_msg}", level="ERROR")
        
        # If still failing due to too many orders, do a broader cleanup
        if "10 working" in error_msg.lower():
            log("🧹 Performing broader stop order cleanup due to limit hit")
            await cleanup_orphaned_stop_orders()  # Clean all symbols
            await asyncio.sleep(2)
            
            # Retry after cleanup
            log("🔄 Retrying SL placement after cleanup")
            result = await signed_request("POST", "/v5/order/create", sl_payload)
            
        # If trigger direction error, try with LastPrice instead of MarkPrice
        elif "triggerdirection" in error_msg.lower():
            log("🔄 Retrying SL with LastPrice trigger")
            sl_payload["triggerBy"] = "LastPrice"
            result = await signed_request("POST", "/v5/order/create", sl_payload)
    
    return result

# --- STOP LOSS WITH RETRY FUNCTION ---
async def place_stop_loss_with_retry(symbol, direction, qty, sl_price, market_type="linear", max_attempts=3):
    """Enhanced stop loss placement with exponential backoff retries"""
    attempt = 0
    delay = 1  # Start with 1 second delay
    
    while attempt < max_attempts:
        try:
            result = await place_stop_loss(symbol, direction, qty, sl_price, market_type)
            
            if result.get("retCode") == 0:
                log(f"✅ SL order placed successfully for {symbol} on attempt {attempt+1}")
                return result
                
            # Handle specific error codes that might be temporary
            if result.get("retCode") in [10002, 10006, 10010]:  # Rate limit or temporary server issues
                log(f"⚠️ Temporary error placing SL for {symbol}: {result.get('retMsg')}", level="WARN")
                await asyncio.sleep(delay)
                attempt += 1
                delay *= 2  # Exponential backoff
                continue
            else:
                # For permanent errors, try a different approach
                return await fallback_stop_loss(symbol, direction, qty, sl_price, market_type)
                
        except Exception as e:
            log(f"❌ Exception in SL placement for {symbol}: {e}", level="ERROR")
            await asyncio.sleep(delay)
            attempt += 1
            delay *= 2
            
    # If we get here, all attempts failed
    from error_handler import send_telegram_message
    await send_telegram_message(f"⚠️ <b>Critical SL Failure</b> for {symbol} after {max_attempts} attempts")
    return {"retCode": -1, "retMsg": f"Failed after {max_attempts} attempts"}

# --- FALLBACK STOP LOSS FUNCTION ---
async def fallback_stop_loss(symbol, direction, qty, sl_price, market_type="linear"):
    """Alternative approach for placing stop loss when standard method fails"""
    
    # Try a conditional order approach as fallback
    side = "Sell" if direction.lower() == "long" else "Buy"
    
    # CRITICAL FIX: Correctly set trigger direction
    trigger_direction = 2 if direction.lower() == "long" else 1
    
    # First, try a StopLimit order 
    fallback_payload = {
        "category": market_type,
        "symbol": symbol,
        "side": side,
        "orderType": "Limit",  # Try limit instead of market
        "price": str(sl_price),  # Add limit price
        "triggerPrice": str(sl_price),
        "triggerDirection": trigger_direction,  # FIXED: Use correct trigger direction
        "triggerBy": "LastPrice",  # Try LastPrice as another alternative
        "qty": str(qty),
        "reduceOnly": True,
        "timeInForce": "GTC",
        "orderFilter": "StopLimit"  # Change to StopLimit order
    }
    
    log(f"🔄 Using fallback StopLimit SL for {symbol}: {fallback_payload}")
    result = await signed_request("POST", "/v5/order/create", fallback_payload)
    
    # If StopLimit also fails, try a conditional TP order as SL (last resort)
    if result.get("retCode") != 0:
        log(f"❌ StopLimit fallback failed: {result.get('retMsg')}", level="ERROR")
        
        # Get current price
        try:
            ticker_resp = await signed_request("GET", "/v5/market/tickers", {"category": market_type, "symbol": symbol})
            mark_price = float(ticker_resp.get("result", {}).get("list", [{}])[0].get("markPrice", 0))
            
            # For long positions: if SL < mark, use TakeProfit
            # For short positions: if SL > mark, use TakeProfit
            if (direction.lower() == "long" and sl_price < mark_price) or (direction.lower() == "short" and sl_price > mark_price):
                last_resort_payload = {
                    "category": market_type,
                    "symbol": symbol,
                    "side": side,
                    "orderType": "Market",
                    "triggerPrice": str(sl_price),
                    "qty": str(qty),
                    "reduceOnly": True,
                    "timeInForce": "GTC",
                    "orderFilter": "tpslOrder",
                    "orderIv": "0",
                    "tpslMode": "Partial",
                    "tpOrderType": "Market",
                    "slOrderType": "Market",
                    "tpTriggerBy": "LastPrice",
                    "slTriggerBy": "LastPrice"
                }
                
                if direction.lower() == "long":
                    last_resort_payload["takeProfit"] = str(sl_price)
                else:
                    last_resort_payload["stopLoss"] = str(sl_price)
                
                log(f"🆘 Last resort TP/SL approach for {symbol}: {last_resort_payload}")
                result = await signed_request("POST", "/v5/order/create", last_resort_payload)
        except Exception as e:
            log(f"❌ Error in last resort SL approach: {e}", level="ERROR")
    
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
