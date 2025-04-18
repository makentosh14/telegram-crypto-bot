import time

# Simulated whale wallet activity store (extend with real data source or API)
WHALE_WALLETS = {
    'wallet1': [],
    'wallet2': [],
    'wallet3': [],
}

def simulate_wallet_activity(symbol, price, wallet="wallet1"):
    """
    Adds simulated buy activity to a whale wallet (for mock/demo use).
    """
    WHALE_WALLETS[wallet].append({
        'symbol': symbol,
        'price': price,
        'timestamp': time.time()
    })

def detect_coordinated_whale_activity(symbol, price, threshold=3, timeframe=180):
    """
    Detects if multiple whale wallets bought the same symbol within a short time window.
    """
    count = 0
    now = time.time()

    for wallet, txs in WHALE_WALLETS.items():
        for tx in txs:
            if tx['symbol'] == symbol and now - tx['timestamp'] <= timeframe:
                if abs(tx['price'] - price) / price < 0.01:  # within 1% price range
                    count += 1
                    break

    return count >= threshold


def detect_whale_heatmap(symbol, recent_buys, threshold=3):
    """
    Detects clusters of large buy volumes on the same coin in a short window.
    `recent_buys` should be a list of dicts like:
    [{'symbol': 'DOGEUSDT', 'amount': 100000, 'wallet': 'xyz', 'timestamp': 123456789}]
    """
    count = 0
    for tx in recent_buys:
        if tx['symbol'] == symbol and tx['amount'] > 50000:
            count += 1

    return count >= threshold


def debug_whale_log(symbol):
    print(f"[🐋] Whale check for {symbol}:")
    for wallet, txs in WHALE_WALLETS.items():
        for tx in txs:
            if tx['symbol'] == symbol:
                print(f"  → {wallet} bought at {tx['price']}")
