import aiohttp
import re

KEYWORDS = [
    "100x", "moon", "next pepe", "buy now", "pump soon", "exploding", "gem", "undervalued",
    "sending", "new listing", "coinbase", "binance", "huge volume", "whale buying"
]

EXCHANGES = ["binance", "bybit", "kucoin", "okx"]

async def fetch_mentions(coin):
    query = f"{coin} ({' OR '.join(KEYWORDS)}) lang:en -is:retweet"
    url = f"https://api.mempulse.io/search?q={query}"  # This is placeholder; replace with real sentiment API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("count", 0), data.get("top_mentions", [])
    except Exception as e:
        print(f"Sentiment fetch error for {coin}: {e}")
    return 0, []

def score_mentions(mentions):
    score = 0
    for text in mentions:
        text_lower = text.lower()
        for kw in KEYWORDS:
            if kw in text_lower:
                score += 1
        for ex in EXCHANGES:
            if ex in text_lower:
                score += 2
    return score
