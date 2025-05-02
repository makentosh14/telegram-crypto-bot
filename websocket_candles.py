import asyncio
import json
import websockets
from collections import defaultdict, deque
from scanner import symbol_category_map
from logger import log
from telegram_bot import send_error_to_telegram  # NEW: send critical errors to Telegram

live_candles = defaultdict(lambda: defaultdict(lambda: deque(maxlen=100)))
SUPPORTED_INTERVALS = ['1', '3', '5', '15', '30', '60', '240']

RECONNECT_DELAY = 5

async def handle_stream(url, symbols, category, interval):
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                args = [f"kline.{interval}.{symbol}" for symbol in symbols if symbol_category_map.get(symbol) == category]
                if not args:
                    return

                await ws.send(json.dumps({"op": "subscribe", "args": args}))
                log(f"📡 Subscribed to {len(args)} {category.upper()} @ {interval}m")

                while True:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(message)

                        topic = data.get("topic", "")
                        symbol = topic.split(".")[-1] if topic else None
                        interval_from_topic = topic.split(".")[1] if topic else None

                        if not symbol or "data" not in data or not interval_from_topic:
                            continue

                        candles = data["data"]

                        if isinstance(candles, list):
                            for k in candles:
                                candle = {
                                    "timestamp": int(k["start"]),
                                    "open": k["open"],
                                    "high": k["high"],
                                    "low": k["low"],
                                    "close": k["close"],
                                    "volume": k["volume"]
                                }
                                live_candles[symbol][interval_from_topic].append(candle)

                        elif isinstance(candles, dict):
                            k = candles
                            candle = {
                                "timestamp": int(k["start"]),
                                "open": k["open"],
                                "high": k["high"],
                                "low": k["low"],
                                "close": k["close"],
                                "volume": k["volume"]
                            }
                            live_candles[symbol][interval_from_topic].append(candle)

                        log(f"📈 {symbol} [{category}] @{interval_from_topic} updated | total: {len(live_candles[symbol][interval_from_topic])}")

                    except asyncio.TimeoutError:
                        warning = f"⚠️ No data received for {category} {interval}m in 30s — reconnecting..."
                        log(warning, level="WARNING")
                        await send_error_to_telegram(warning)
                        break

                    except Exception as e:
                        error = f"❌ WebSocket stream error in {category} {interval}m: {e}"
                        log(error, level="ERROR")
                        await send_error_to_telegram(error)
                        break

        except Exception as e:
            error = f"❌ Connection failed for {category} {interval}m: {e}"
            log(error, level="ERROR")
            await send_error_to_telegram(error)

        reconnect_msg = f"🔁 Reconnecting {category} {interval}m in {RECONNECT_DELAY}s..."
        log(reconnect_msg)
        await send_error_to_telegram(reconnect_msg)
        await asyncio.sleep(RECONNECT_DELAY)

async def stream_candles(symbols):
    futures_url = "wss://stream.bybit.com/v5/public/linear"
    spot_url = "wss://stream.bybit.com/v5/public/spot"

    tasks = []
    for interval in SUPPORTED_INTERVALS:
        tasks.append(asyncio.create_task(handle_stream(futures_url, symbols, "linear", interval)))
        tasks.append(asyncio.create_task(handle_stream(spot_url, symbols, "spot", interval)))

    await asyncio.gather(*tasks)
