# news_scanner.py

import re

# Example news-based keywords that may impact market
BULLISH_KEYWORDS = [
    "binance listing", "coinbase listing", "etf approved", "elon", "airdrop", "backed by", "invested in",
    "launch partner", "celeb tweet", "AI", "pump", "retweet", "mainnet", "token unlock"
]

BEARISH_KEYWORDS = [
    "hack", "delist", "sec", "fed", "lawsuit", "cease", "ban", "conflict", "fud", "rug"
]

MACRO_KEYWORDS = [
    "trump", "war", "inflation", "interest rate", "treasury", "usd", "debt ceiling", "china", "russia", "brics"
]

def scan_text_for_sentiment(text):
    t = text.lower()
    bull_hits = sum(1 for word in BULLISH_KEYWORDS if word in t)
    bear_hits = sum(1 for word in BEARISH_KEYWORDS if word in t)
    macro_hits = sum(1 for word in MACRO_KEYWORDS if word in t)

    sentiment = "neutral"
    if bull_hits > bear_hits and bull_hits > 0:
        sentiment = "bullish"
    elif bear_hits > bull_hits and bear_hits > 0:
        sentiment = "bearish"
    elif macro_hits > 0:
        sentiment = "macro"

    return {
        "sentiment": sentiment,
        "bull_hits": bull_hits,
        "bear_hits": bear_hits,
        "macro_hits": macro_hits
    }

# Sample use case
def should_trigger_news_alert(text):
    result = scan_text_for_sentiment(text)
    return result["sentiment"] in ["bullish", "bearish"]
