import aiohttp
import re
import time

# Define keywords and sources that suggest early meme pump activity
KEYWORDS = [
    "100x", "moon", "next pepe", "buy now", "pump soon", "exploding",
    "gem", "undervalued", "sending", "new listing", "coinbase", "binance",
    "kucoin", "huge volume", "whale buying", "viral", "telegram call", "twitter trending"
]

EXCHANGES = ["binance", "bybit", "kucoin", "okx"]

# === Social Score Cache ===
MENTION_CACHE = {}
MENTION_EXPIRY = 300  # seconds

async def fetch_mentions(coin):
    now = time.time()
    if coin in MENTION_CACHE and now - MENTION_CACHE[coin]["timestamp"] < MENTION_EXPIRY:
        return MENTION_CACHE[coin]["count"], MENTION_CACHE[coin]["top_mentions"]

    query = f"{coin} ({' OR '.join(KEYWORDS)}) lang:en -is:retweet"
    url = f"https://api.mempulse.io/search?q={query}"  # Placeholder for a real API

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    count = data.get("count", 0)
                    top_mentions = data.get("top_mentions", [])
                    MENTION_CACHE[coin] = {
                        "count": count,
                        "top_mentions": top_mentions,
                        "timestamp": now
                    }
                    return count, top_mentions
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

async def check_social_sentiment(coin):
    count, mentions = await fetch_mentions(coin)
    social_score = score_mentions(mentions)
    return {
        "mention_count": count,
        "score": social_score,
        "mentions": mentions[:3]  # preview top 3
    }
