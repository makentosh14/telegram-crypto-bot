import aiohttp

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
    """Simulated Twitter mentions detection (stubbed for free version)."""
    simulated_mentions = [
        f"This coin {coin} is going to 100x!",
        f"{coin} is a hidden gem, buy now!"
    ]
    score = sum(any(kw in text.lower() for kw in TWITTER_KEYWORDS) for text in simulated_mentions)
    return score

async def fetch_reddit_mentions():
    """Fetch and score Reddit mentions for trending meme coins."""
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
    except Exception as e:
        print(f"Reddit fetch error: {e}")
    return score_map

async def fetch_coingecko_trending():
    """Fetch currently trending coins from CoinGecko."""
    trending = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(COINGECKO_TRENDING_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    trending = [item["item"]["symbol"].upper() for item in data.get("coins", [])]
    except Exception as e:
        print(f"CoinGecko trending fetch error: {e}")
    return trending

async def check_social_sentiment(coin):
    """
    Check overall social sentiment:
    - Reddit mentions
    - Simulated Twitter mentions
    - CoinGecko trending hit
    """
    coin = coin.replace("USDT", "").upper()

    reddit_scores = await fetch_reddit_mentions()
    twitter_score = await fetch_twitter_mentions(coin)
    trending_list = await fetch_coingecko_trending()

    reddit_score = reddit_scores.get(coin, 0)
    trending_bonus = 2 if coin in trending_list else 0

    total_score = reddit_score + twitter_score + trending_bonus

    return total_score >= 3  # Threshold adjustable
