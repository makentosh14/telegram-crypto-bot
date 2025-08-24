# pattern_backfill.py - Historical Pattern Discovery and Testing (leak-proof)
# Rewritten to avoid data leakage, paginate klines, split train/test by time,
# and include a simple P&L simulator.

import asyncio
import json
import os
import math
import time
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Any, Optional

from logger import log
from bybit_api import signed_request
from pattern_detector import detect_pattern
from score import score_symbol

ISO = "%Y-%m-%dT%H:%M:%S"

# --- Backtest parameters (tweak here) ---
DISCOVERY_WINDOW_MIN = 20          # number of 1m bars in the *future* outcome window
PATTERN_MIN_BARS_5M = 10           # use last 10 x 5m bars to detect candle pattern
SIM_TP_PCT = 0.015                 # 1.5% take-profit
SIM_SL_PCT = 0.010                 # 1.0% stop-loss
SIM_MAX_MINUTES = 60               # fail-safe timeout (minutes after entry)
FEE_PCT = 0.0006                   # 0.06% taker fee per side
SLIP_PCT = 0.0002                  # 0.02% slippage per side

WRITE_LIVE = os.getenv("BACKTEST_WRITE_MEMORY", "0") == "1"
LIVE_DB_FILE = "pattern_memory.json"
BACKFILL_DB_FILE = "pattern_discovered_backfill.json"
REPORT_FILE = "pattern_backfill_report.json"

def iso_to_ms(s: str) -> int:
    # tolerate "2025-08-24T21:10:00" and "2025-08-24 21:10:00"
    s = s.replace("Z", "").replace(" ", "T")
    dt = datetime.fromisoformat(s)
    return int(dt.timestamp() * 1000)

def ms_to_iso(ms: int) -> str:
    return datetime.utcfromtimestamp(ms / 1000).isoformat()

class PatternBackfillSystem:
    def __init__(self):
        self.discovered_patterns: List[Dict[str, Any]] = []
        self.backtest_results: List[Dict[str, Any]] = []
        self.symbol_data_cache: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    # ---------------------------
    # End-to-end backfill runner
    # ---------------------------
    async def run_full_backfill(self, symbols: List[str], days: int = 30):
        log(f"🚀 Starting {days}-day pattern backfill for {len(symbols)} symbols")

        await self.download_historical_data(symbols, days)
        await self.discover_historical_patterns(symbols)
        await self.backtest_pattern_matching()
        self.generate_backfill_report()

        log("✅ Backfill process completed!")

    # ---------------------------
    # Historical data download
    # ---------------------------
    async def download_historical_data(self, symbols: List[str], days: int):
        log(f"📥 Downloading {days} days of historical data.")
        end_time = int(time.time() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)

        timeframes = ['1', '3', '5', '15', '30', '60', '240']

        for symbol in symbols:
            log(f"📊 Downloading {symbol}.")
            self.symbol_data_cache[symbol] = {}

            for tf in timeframes:
                try:
                    interval = tf  # Bybit uses same strings: '1','3','5','15','30','60','240'
                    candles = await self.fetch_historical_candles(
                        symbol, interval, start_time, end_time
                    )
                    if candles:
                        self.symbol_data_cache[symbol][tf] = candles
                        log(f"   ✅ {symbol} {tf}m: {len(candles)} candles")
                    else:
                        log(f"   ❌ {symbol} {tf}m: No data")
                    await asyncio.sleep(0.05)
                except Exception as e:
                    log(f"❌ Error downloading {symbol} {tf}m: {e}", level="ERROR")
                    continue

            await asyncio.sleep(0.2)

        log("✅ Historical data download completed")

    async def fetch_historical_candles(self, symbol: str, interval: str, start_time: int, end_time: int):
        """
        Paginated download from /v5/market/kline (Bybit).
        Prior code fetched once and silently truncated to 1000 rows. Fixed with cursor pagination.
        """
        try:
            candles: List[Dict[str, Any]] = []
            cursor: Optional[str] = None

            while True:
                params = {
                    "category": "linear",
                    "symbol": symbol,
                    "interval": interval,
                    "start": start_time,
                    "end": end_time,
                    "limit": 1000
                }
                if cursor:
                    params["cursor"] = cursor

                result = await signed_request("GET", "/v5/market/kline", params)
                if result.get("retCode") != 0:
                    log(f"API Error: {result}", level="ERROR")
                    break

                klines = result.get("result", {}).get("list", []) or []
                for k in klines:
                    candles.append({
                        "timestamp": int(k[0]),
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                    })

                cursor = result.get("result", {}).get("nextPageCursor")
                if not cursor or not klines:
                    break

                await asyncio.sleep(0.02)

            candles.sort(key=lambda x: x["timestamp"])
            return candles

        except Exception as e:
            log(f"Error fetching candles: {e}", level="ERROR")
            return []

    # ---------------------------
    # Pattern discovery (leak-proof)
    # ---------------------------
    async def discover_historical_patterns(self, symbols: List[str]):
        """
        Detect patterns using ONLY data available up to time t,
        then measure the outcome in the NEXT DISCOVERY_WINDOW_MIN 1m bars.
        The previous code labeled outcomes using the *same* window as the features,
        which inflates win-rates. Fixed here.
        """
        log("🔍 Discovering patterns from historical data (leak-proof).")

        for symbol in symbols:
            if symbol not in self.symbol_data_cache:
                continue

            try:
                candles_1m = self.symbol_data_cache[symbol].get('1', [])
                if len(candles_1m) < 120:
                    continue

                i = PATTERN_MIN_BARS_5M  # start after we can build a 5m context
                # Ensure we have room for the future window
                last_valid = len(candles_1m) - (DISCOVERY_WINDOW_MIN + 1)

                while i < last_valid:
                    ts = candles_1m[i]["timestamp"]

                    # Build candles_by_tf strictly up to time ts
                    candles_by_tf = self.build_historical_candles_by_tf(symbol, ts)
                    if not candles_by_tf:
                        i += 1
                        continue

                    # Detect pattern on the last PATTERN_MIN_BARS_5M x 5m candles
                    pattern_candles = candles_by_tf.get('5', [])[-PATTERN_MIN_BARS_5M:]
                    if len(pattern_candles) < max(3, PATTERN_MIN_BARS_5M):
                        i += 1
                        continue

                    detected_pattern = detect_pattern(pattern_candles)
                    if not detected_pattern:
                        i += 1
                        continue

                    # Entry is next bar OPEN after detection time
                    entry_idx = self._find_first_bar_index(candles_1m, ts)
                    if entry_idx is None or entry_idx + DISCOVERY_WINDOW_MIN >= len(candles_1m):
                        i += 1
                        continue

                    entry_open = candles_1m[entry_idx]["open"]

                    # Outcome measured ONLY in the next window
                    nxt = candles_1m[entry_idx : entry_idx + DISCOVERY_WINDOW_MIN]
                    max_high = max(c["high"] for c in nxt)
                    min_low  = min(c["low"]  for c in nxt)

                    move_up = (max_high - entry_open) / entry_open * 100.0
                    move_down = (entry_open - min_low) / entry_open * 100.0
                    direction = "pump" if move_up >= move_down else "dump"
                    move_pct = round(move_up if direction == "pump" else move_down, 2)

                    # Score/context at that time (best-effort; wrapped in try)
                    try:
                        score, tf_scores, trade_type, indicator_scores, used_indicators = score_symbol(
                            symbol, candles_by_tf
                        )
                    except Exception:
                        score, tf_scores, trade_type, indicator_scores, used_indicators = 0, {}, "Unknown", {}, []

                    record = {
                        "timestamp": ms_to_iso(ts),
                        "symbol": symbol,
                        "direction": direction,
                        "move_pct": move_pct,
                        "trade_type": trade_type,
                        "pattern": detected_pattern,
                        "score": score,
                        "tf_scores": tf_scores,
                        "indicator_scores": indicator_scores,
                        "used_indicators": used_indicators,
                        # lightweight context stub (you can expand)
                        "context": {
                            "window_min": DISCOVERY_WINDOW_MIN,
                            "entry_open": round(entry_open, 8),
                        }
                    }
                    self.discovered_patterns.append(record)

                    # Real skip to avoid overlapping detections
                    i += 10
                # end while

            except Exception as e:
                log(f"❌ Pattern discovery error for {symbol}: {e}", level="ERROR")
                continue

        log(f"✅ Discovered {len(self.discovered_patterns)} historical patterns")

    def _find_first_bar_index(self, candles_1m: List[Dict[str, Any]], ts_ms: int) -> Optional[int]:
        """First bar with timestamp >= ts_ms (entry bar)."""
        lo, hi = 0, len(candles_1m) - 1
        ans = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if candles_1m[mid]["timestamp"] >= ts_ms:
                ans = mid
                hi = mid - 1
            else:
                lo = mid + 1
        return ans

    def build_historical_candles_by_tf(self, symbol: str, timestamp: int):
        """Build candles_by_tf dictionary strictly up to a timestamp (no peeking)."""
        out: Dict[str, List[Dict[str, Any]]] = {}
        for tf in ['1', '3', '5', '15', '30', '60', '240']:
            series = self.symbol_data_cache.get(symbol, {}).get(tf)
            if not series:
                continue
            hist = [c for c in series if c["timestamp"] <= timestamp]
            if len(hist) >= 30:
                out[tf] = hist[-100:]
        return out or None

    # ---------------------------
    # Backtest (time-split) + P&L
    # ---------------------------
    async def backtest_pattern_matching(self):
        """
        Train on older half (by time), test on newer half (by time).
        Predict majority direction per pattern; simulate trade with TP/SL.
        """
        log("🧪 Backtesting pattern matching (time split + P&L).")

        if not self.discovered_patterns:
            log("❌ No patterns to test - run discovery first")
            return

        # Split by time (not by list index)
        times = sorted(iso_to_ms(r["timestamp"]) for r in self.discovered_patterns)
        mid_time = times[len(times)//2]

        training = [r for r in self.discovered_patterns if iso_to_ms(r["timestamp"]) <= mid_time]
        testing  = [r for r in self.discovered_patterns if iso_to_ms(r["timestamp"]) >  mid_time]

        log(f"📊 Training on {len(training)} patterns; 🧪 Testing on {len(testing)} patterns")

        # Group training by pattern type
        train_by_pattern: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in training:
            if r.get("pattern"):
                train_by_pattern[r["pattern"]].append(r)

        correct = 0
        total = 0

        for test in testing:
            pat = test["pattern"]
            symbol = test["symbol"]
            ts_ms = iso_to_ms(test["timestamp"])

            hist = train_by_pattern.get(pat)
            if not hist or len(hist) < 5:
                continue

            pred_dir, pred_move, conf = self.make_pattern_prediction(hist)

            if pred_dir and conf >= 0.55:
                total += 1
                actual_dir = test["direction"]
                if pred_dir == actual_dir:
                    correct += 1

                # Simulate a trade in the predicted direction from next 1m open
                pnl_pct, exit_reason = self.simulate_trade(symbol, ts_ms, pred_dir)
                self.backtest_results.append({
                    "symbol": symbol,
                    "pattern": pat,
                    "timestamp": test["timestamp"],
                    "predicted_direction": pred_dir,
                    "actual_direction": actual_dir,
                    "confidence": conf,
                    "predicted_move": pred_move,
                    "actual_move": test["move_pct"],
                    "pnl_pct": pnl_pct,
                    "exit": exit_reason,
                    "correct": pred_dir == actual_dir
                })

        acc = (correct / total) if total > 0 else 0.0
        log(f"🎯 Backtest Results: {correct}/{total} ({acc:.1%} accuracy)")

    def make_pattern_prediction(self, historical_data: List[Dict[str, Any]]):
        """Majority direction + average move from training set (simple baseline)."""
        dirs = [r.get("direction") for r in historical_data]
        pumps = dirs.count("pump")
        dumps = dirs.count("dump")
        if pumps >= dumps:
            pred = "pump"
            conf = pumps / max(1, len(dirs))
            moves = [r.get("move_pct", 0) for r in historical_data if r.get("direction") == "pump"]
        else:
            pred = "dump"
            conf = dumps / max(1, len(dirs))
            moves = [r.get("move_pct", 0) for r in historical_data if r.get("direction") == "dump"]
        pred_move = (sum(moves) / len(moves)) if moves else 0.0
        return pred, pred_move, conf

    def simulate_trade(self, symbol: str, ts_ms: int, direction: str):
        """
        One-shot TP/SL simulator:
        - Enter at next 1m bar open after ts_ms
        - Long: stop first policy if both TP/SL hit within a bar (conservative)
        - Includes fees + slippage both sides
        """
        series = self.symbol_data_cache.get(symbol, {}).get('1', [])
        if not series:
            return 0.0, "no_data"

        entry_idx = self._find_first_bar_index(series, ts_ms)
        if entry_idx is None or entry_idx + 1 >= len(series):
            return 0.0, "no_entry"

        entry_open = series[entry_idx]["open"]
        # Apply slippage on entry
        if direction == "pump":
            entry_px = entry_open * (1 + SLIP_PCT)
            tp = entry_px * (1 + SIM_TP_PCT)
            sl = entry_px * (1 - SIM_SL_PCT)
        else:
            entry_px = entry_open * (1 - SLIP_PCT)
            tp = entry_px * (1 - SIM_TP_PCT)
            sl = entry_px * (1 + SIM_SL_PCT)

        horizon_end = min(len(series), entry_idx + 1 + SIM_MAX_MINUTES)
        exit_px = series[horizon_end - 1]["close"]  # default timed exit
        exit_reason = "timeout"

        for i in range(entry_idx + 1, horizon_end):
            hi = series[i]["high"]
            lo = series[i]["low"]

            if direction == "pump":
                # stop-first policy when both are inside same bar (worst case)
                if lo <= sl:
                    exit_px = sl * (1 - SLIP_PCT)  # slippage on exit
                    exit_reason = "stop"
                    break
                if hi >= tp:
                    exit_px = tp * (1 + SLIP_PCT)
                    exit_reason = "tp"
                    break
            else:
                if hi >= sl:
                    exit_px = sl * (1 + SLIP_PCT)
                    exit_reason = "stop"
                    break
                if lo <= tp:
                    exit_px = tp * (1 - SLIP_PCT)
                    exit_reason = "tp"
                    break

        # PnL with fees both sides
        gross = (exit_px - entry_px) / entry_px if direction == "pump" else (entry_px - exit_px) / entry_px
        net = gross - (2 * FEE_PCT) - (2 * SLIP_PCT)
        return round(net * 100.0, 3), exit_reason

    # ---------------------------
    # Reporting
    # ---------------------------
    def generate_backfill_report(self):
        log("📊 Generating backfill report.")

        # Save discovered patterns (no live write unless opted in)
        self.save_discovered_patterns()

        pattern_stats = self.analyze_pattern_performance()
        backtest_stats = self.analyze_backtest_results()

        print("\n" + "=" * 60)
        print("🎯 PATTERN BACKFILL REPORT")
        print("=" * 60)

        print(f"\n📚 PATTERN DISCOVERY:")
        print(f"   Total patterns discovered: {len(self.discovered_patterns)}")
        print(f"   Unique pattern types: {len(pattern_stats['pattern_types'])}")
        print(f"   Average move size: {pattern_stats['avg_move']:.2f}%")
        print(f"   (directional) Pump ratio: {pattern_stats['pump_ratio']:.1%}")

        print(f"\n🔥 TOP PATTERNS BY SAMPLE SIZE:")
        for pattern, stats in pattern_stats['top_patterns'][:5]:
            print(f"   {pattern}: n={stats['count']}, avg move {stats['avg_move']:+.2f}%")

        if self.backtest_results:
            print(f"\n🧪 BACKTEST RESULTS:")
            print(f"   Total predictions: {len(self.backtest_results)}")
            print(f"   Accuracy: {backtest_stats['accuracy']:.1%}")
            print(f"   Profit factor: {backtest_stats['profit_factor']:.2f}")
            print(f"   Avg trade: {backtest_stats['avg_trade_pct']:+.3f}%")
            print(f"   Win rate: {backtest_stats['win_rate']:.1%}")

            print(f"\n📈 BEST PREDICTIONS (by confidence):")
            for r in backtest_stats['best_predictions'][:3]:
                print(f"   {r['pattern']} on {r['symbol']}: {r['confidence']:.1%} confidence, "
                      f"{'✅' if r['correct'] else '❌'}, PnL {r['pnl_pct']:+.2f}% ({r['exit']})")

        print("\n" + "=" * 60)
        self.save_backfill_report(pattern_stats, backtest_stats)

    def save_discovered_patterns(self):
        """Write to a separate file by default to avoid contaminating live DB."""
        out_file = LIVE_DB_FILE if WRITE_LIVE else BACKFILL_DB_FILE

        existing = []
        if os.path.exists(out_file):
            try:
                with open(out_file, "r") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        all_rows = existing + self.discovered_patterns
        with open(out_file, "w") as f:
            json.dump(all_rows, f, indent=2)

        log(f"✅ Saved {len(self.discovered_patterns)} new patterns to '{out_file}'")

    def analyze_pattern_performance(self):
        if not self.discovered_patterns:
            return {"pattern_types": {}, "avg_move": 0.0, "pump_ratio": 0.0, "top_patterns": []}

        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in self.discovered_patterns:
            if r.get("pattern"):
                groups[r["pattern"]].append(r)

        stats = {}
        all_moves = []
        all_dirs = []
        for pat, rows in groups.items():
            moves = [r.get("move_pct", 0.0) for r in rows]
            stats[pat] = {
                "count": len(rows),
                "avg_move": sum(moves) / max(1, len(moves)),
                "max_move": max(moves) if moves else 0.0,
                "min_move": min(moves) if moves else 0.0,
            }
            all_moves.extend(moves)
            all_dirs.extend([r.get("direction") for r in rows])

        pump_ratio = all_dirs.count("pump") / max(1, len(all_dirs))
        top = sorted(stats.items(), key=lambda kv: kv[1]["count"], reverse=True)

        return {
            "pattern_types": stats,
            "avg_move": (sum(all_moves) / max(1, len(all_moves))) if all_moves else 0.0,
            "pump_ratio": pump_ratio,
            "top_patterns": top,
        }

    def analyze_backtest_results(self):
        if not self.backtest_results:
            return {
                "accuracy": 0.0,
                "profit_factor": 0.0,
                "avg_trade_pct": 0.0,
                "win_rate": 0.0,
                "best_predictions": [],
            }

        acc = sum(1 for r in self.backtest_results if r["correct"]) / len(self.backtest_results)
        wins = [r["pnl_pct"] for r in self.backtest_results if r["pnl_pct"] > 0]
        losses = [abs(r["pnl_pct"]) for r in self.backtest_results if r["pnl_pct"] <= 0]
        pf = (sum(wins) / max(1e-9, sum(losses))) if losses else float("inf")
        avg_trade = sum(r["pnl_pct"] for r in self.backtest_results) / len(self.backtest_results)
        wr = len(wins) / len(self.backtest_results) if self.backtest_results else 0.0

        best = sorted(self.backtest_results, key=lambda r: r["confidence"], reverse=True)

        return {
            "accuracy": acc,
            "profit_factor": pf if pf != float("inf") else 999.0,
            "avg_trade_pct": avg_trade,
            "win_rate": wr,
            "best_predictions": best,
        }

    def save_backfill_report(self, pattern_stats: Dict[str, Any], backtest_stats: Dict[str, Any]):
        report = {
            "timestamp": datetime.now().isoformat(),
            "discovered_patterns": len(self.discovered_patterns),
            "pattern_stats": pattern_stats,
            "backtest_stats": backtest_stats,
            "results": self.backtest_results,
            "write_mode": "live" if WRITE_LIVE else "read_only"
        }
        with open(REPORT_FILE, "w") as f:
            json.dump(report, f, indent=2)
        log(f"✅ Detailed report saved to {REPORT_FILE}")


# --------- USAGE HELPERS (optional) ---------
async def run_quick_backfill(symbols=None, days=7):
    if symbols is None:
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
    backfill = PatternBackfillSystem()
    await backfill.run_full_backfill(symbols, days)


async def run_full_backfill(symbols=None, days=30):
    if symbols is None:
        try:
            from scanner import fetch_symbols
            symbols = await fetch_symbols()
            symbols = symbols[:50]
        except Exception:
            symbols = [
                'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
                'XRPUSDT', 'DOTUSDT', 'UNIUSDT', 'LINKUSDT', 'LTCUSDT'
            ]
    backfill = PatternBackfillSystem()
    await backfill.run_full_backfill(symbols, days)


async def run_extended_backfill(symbols=None, days=60):
    if symbols is None:
        try:
            from scanner import fetch_symbols
            symbols = await fetch_symbols()
        except Exception:
            symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    backfill = PatternBackfillSystem()
    await backfill.run_full_backfill(symbols, days)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "quick":
            asyncio.run(run_quick_backfill())
        elif sys.argv[1] == "full":
            asyncio.run(run_full_backfill())
        elif sys.argv[1] == "extended":
            asyncio.run(run_extended_backfill())
    else:
        print("Usage:")
        print("  python pattern_backfill.py quick    # 7 days, 5 symbols")
        print("  python pattern_backfill.py full     # 30 days, 50 symbols")
        print("  python pattern_backfill.py extended # 60 days, all symbols")
