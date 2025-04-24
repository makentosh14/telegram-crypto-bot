# sentiment_detector.py

import aiohttp
import re

REDDIT_KEYWORDS = [
    "next pepe", "next 100x", "hidden gem", "new coin", "moonshot", "undervalued",
    "just launched", "low cap gem", "pump incoming", "sending soon"
]

TWITTER_KEYWORDS = [
    "100x", "buy now", "next pepe", "listing", "pump soon", "whale buying",
    "exploding", "going parabolic", "new gem"
]

COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
REDDIT_URL = "https://api.pushshift.io/reddit/search/submission/?subreddit=cryptomoonshots&size=30"

async def fetch_twitter_mentions(coin):
    # Simulate sentiment score based on keyword matching (stubbed for free version)
    score = 0
    try:
        mentions = [
            f"This coin {coin} is going to 100x!",  # simulated data
            f"{coin} is a new hidden gem, buy now"
        ]
        for text in mentions:
            for kw in TWITTER_KEYWORDS:
                if kw in text.lower():
                    score += 1
    except:
        pass
    return score

async def fetch_reddit_mentions():
    score_map = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(REDDIT_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    posts = data.get("data", [])
                    for post in posts:
                        title = post.get("title", "").lower()
                        for kw in REDDIT_KEYWORDS:
                            if kw in title:
                                for word in title.split():
                                    if word.isupper() and len(word) <= 6:
                                        score_map[word] = score_map.get(word, 0) + 1
    except:
        pass
    return score_map

async def fetch_coingecko_trending():
    trending = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(COINGECKO_TRENDING_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("coins", []):
                        trending.append(item["item"]["symbol"].upper())
    except:
        pass
    return trending

async def check_social_sentiment(coin):
    coin = coin.replace("USDT", "").upper()
    reddit_scores = await fetch_reddit_mentions()
    twitter_score = await fetch_twitter_mentions(coin)
    trending = await fetch_coingecko_trending()

    reddit_score = reddit_scores.get(coin, 0)
    trending_hit = coin in trending

    total_score = reddit_score + twitter_score + (2 if trending_hit else 0)
    return total_score >= 3  # can adjust threshold
