#!/usr/bin/env python3
# realistic_backtest.py — live-like backtester (latency, dynamic slippage, mark-style triggers, funding)
# Plugs into your stack:
# - bybit_api.signed_request  (API calls)            ← uses your client
# - logger.log                (logging)
# - score.enhanced_score_symbol, determine_direction ← your scoring/direction
# - trade_executor.calculate_dynamic_sl_tp           ← your SL/TP sizing (candles-aware)
# - pattern_detector.detect_pattern                  ← for the pattern strategy (optional)
# - trend_filters.get_trend_context_cached           ← optional regime flavor

import asyncio, time, math, json, random
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timedelta

from logger import log                                  # your logger
from bybit_api import signed_request                    # your API client  :contentReference[oaicite:0]{index=0}
from score import enhanced_score_symbol, score_symbol, determine_direction, calculate_confidence  # your scoring  :contentReference[oaicite:1]{index=1}
from trade_executor import calculate_dynamic_sl_tp      # your SL/TP calc (expects candles_by_tf first)  :contentReference[oaicite:2]{index=2}
from pattern_detector import detect_pattern             # your patterns  :contentReference[oaicite:3]{index=3}
from trend_filters import get_trend_context_cached      # optional regime  :contentReference[oaicite:4]{index=4}

# ---------- realism knobs (tune as you wish) ----------
FEE_TAKER_PCT = 0.0006      # 0.06% per side
BASE_SLIP_BPS = 2           # 2 bps = 0.02% base slippage per side (symbol-specific override possible)
RANGE_SLIP_K   = 0.20       # slippage add = k * (bar_range / open)
LATENCY_MEAN_S = 3.0        # avg 3s signal→fill latency
LATENCY_STD_S  = 1.0        # std 1s
LATENCY_MAX_S  = 12.0       # cap
MARK_BIAS_BPS  = 4          # mark vs last bias used for triggers (more sensitive stops)
RISK_PER_TRADE = 0.02       # 2% of balance reserved as margin
LEVERAGE       = 10.0
MAX_CONCURRENT = 5
MAX_HOLD_H = {"Scalp": 1, "Intraday": 24, "Swing": 168}

TIMEFRAMES = ['1', '3', '5', '15', '30', '60', '240']
CATEGORY = "linear"

# ----- utility -----
def ms_to_iso(ms:int) -> str: return datetime.utcfromtimestamp(ms/1000).isoformat()
def iso_to_ms(s:str) -> int:  return int(datetime.fromisoformat(s.replace('Z','')).timestamp()*1000)

def clamp(v,a,b): return a if v<a else b if v>b else v

def latency_seconds() -> float:
    x = random.normalvariate(LATENCY_MEAN_S, LATENCY_STD_S)
    return clamp(x, 0.0, LATENCY_MAX_S)

def dynamic_slip_pct(bar: Dict[str, float]) -> float:
    # base + k * (range/open)
    rng = max(0.0, float(bar["high"]) - float(bar["low"]))
    open_px = max(1e-9, float(bar["open"]))
    return (BASE_SLIP_BPS / 1e4) + RANGE_SLIP_K * (rng / open_px)

def mark_adjusted_hi_lo(hi: float, lo: float, side: str) -> Tuple[float,float]:
    """Approximate mark-price triggers: make stops slightly easier to hit, TPs slightly harder."""
    bias = MARK_BIAS_BPS / 1e4
    if side == "Long":
        # stop uses a slightly lower effective low; TP uses slightly lower effective high
        return hi * (1 - bias), lo * (1 + bias)
    else:
        # for shorts, invert
        return hi * (1 + bias), lo * (1 - bias)

# ---------- data fetch ----------
async def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> List[Dict[str, Any]]:
    candles, cursor = [], None
    first = True
    while True:
        params = {
            "category": CATEGORY, "symbol": symbol, "interval": interval,
            "start": start_ms, "end": end_ms, "limit": 1000
        }
        if cursor: params["cursor"] = cursor
        if first:
            log(f"🔗 GET /v5/market/kline {symbol} {interval}m {ms_to_iso(start_ms)}→{ms_to_iso(end_ms)} UTC")
            first = False
        resp = await signed_request("GET", "/v5/market/kline", params)
        if resp.get("retCode") != 0:
            log(f"❌ kline error {symbol} {interval}m: {resp}", level="ERROR"); break
        lst = resp.get("result", {}).get("list", []) or []
        for k in lst:
            candles.append({
                "timestamp": int(k[0]), "open": float(k[1]), "high": float(k[2]),
                "low": float(k[3]), "close": float(k[4]), "volume": float(k[5]),
            })
        cursor = resp.get("result", {}).get("nextPageCursor")
        if not cursor or not lst: break
        await asyncio.sleep(0.02)
    candles.sort(key=lambda x: x["timestamp"])
    log(f"✅ {symbol} {interval}m candles: {len(candles)}")
    return candles

async def fetch_funding(symbol: str, start_ms: int, end_ms: int) -> List[Tuple[int, float]]:
    """
    Try to pull funding history. If the endpoint fails/absent, return empty list (no funding).
    """
    events: List[Tuple[int,float]] = []
    try:
        # Bybit v5: /v5/market/funding/history (symbol, startTime, endTime, limit)
        cursor = None
        while True:
            params = {"category": CATEGORY, "symbol": symbol, "limit": 200}
            # some deployments require 'startTime' (ms); if omitted, API returns recent
            # We'll use pagination only via cursor and post-filter locally:
            if cursor: params["cursor"] = cursor
            resp = await signed_request("GET", "/v5/market/funding/history", params)
            if resp.get("retCode") != 0:
                break
            lst = resp.get("result", {}).get("list", []) or []
            for row in lst:
                # expected fields can vary; try both
                ts = int(row.get("fundingRateTimestamp") or row.get("timestamp") or 0)
                rate = float(row.get("fundingRate") or row.get("rate") or 0.0)
                if start_ms <= ts <= end_ms:
                    events.append((ts, rate))
            cursor = resp.get("result", {}).get("nextPageCursor")
            if not cursor or not lst:
                break
            await asyncio.sleep(0.02)
        # Dedup & sort
        events = sorted(list({(t,r) for (t,r) in events}), key=lambda x: x[0])
    except Exception as e:
        log(f"⚠️ funding fetch fallback for {symbol}: {e}")
        events = []
    log(f"💸 Funding events {symbol}: {len(events)} in window")
    return events

# ---------- main class ----------
class RealisticBacktester:
    def __init__(self):
        self.hdata: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self.funding_events: Dict[str, List[Tuple[int,float]]] = {}
        self.trades: List[Dict[str, Any]] = []
        self.daily_pnl: Dict[str, float] = defaultdict(float)

    async def run(self, symbols: List[str], days:int=14, initial_balance: float=10_000.0):
        log(f"🚀 Starting realistic backtest — {days} days, {len(symbols)} symbols")
        end_ms   = int(time.time()*1000)
        start_ms = end_ms - days*24*60*60*1000

        # Download data
        await self._download(symbols, start_ms, end_ms)

        # Backtest loop
        balance = initial_balance
        open_trades: Dict[int, Dict[str, Any]] = {}
        trade_id = 0

        # union of 1m timestamps
        all_ts = set()
        for s in symbols:
            if s in self.hdata and '1' in self.hdata[s]:
                all_ts.update(c['timestamp'] for c in self.hdata[s]['1'])
        timeline = sorted(all_ts)

        for idx, ts in enumerate(timeline):
            # 1) process exits on this minute
            to_close = []
            for tid, tr in list(open_trades.items()):
                exit_info = self._check_exit(tr, ts)
                if exit_info:
                    pnl_ccy = exit_info["pnl"]
                    balance += (tr["reserved_margin"] + pnl_ccy)
                    tr_out = {**tr, **{
                        "exit_time": ms_to_iso(ts),
                        "exit_price": exit_info["exit_price"],
                        "exit_reason": exit_info["reason"],
                        "pnl_ccy": pnl_ccy,
                        "pnl_pct_pos": (pnl_ccy / tr["position_value"]) * 100 if tr["position_value"] else 0.0,
                        "minutes": (ts - tr["entry_ts"]) // 60000
                    }}
                    self.trades.append(tr_out)
                    self.daily_pnl[ms_to_iso(ts)[:10]] += pnl_ccy
                    del open_trades[tid]

            # 2) consider entries every 5 minutes & if capacity
            if idx % 5 == 0 and len(open_trades) < MAX_CONCURRENT:
                for s in symbols:
                    # one trade per symbol at a time
                    if any(t["symbol"] == s for t in open_trades.values()):
                        continue
                    cb = self._candles_up_to(s, ts)
                    if not cb: continue

                    # Score using your enhanced scorer; fallback to basic
                    try:
                        score, tf_scores, trade_type, ind_scores, used_inds = enhanced_score_symbol(s, cb)
                    except Exception:
                        score, tf_scores, trade_type, ind_scores, used_inds = score_symbol(s, cb), {}, "Intraday", {}, []

                    # Direction & confidence (your calc if available)
                    try:
                        direction = determine_direction(tf_scores, ind_scores)
                    except Exception:
                        direction = "Long" if score >= 0 else "Short"

                    try:
                        confidence = calculate_confidence(score, tf_scores, ind_scores, used_inds)  # if available
                    except Exception:
                        confidence = 60

                    # Basic thresholding to avoid spam
                    if score < 10.0:
                        continue

                    # Latency → delayed timestamp for entry pricing
                    delay_ms = int(latency_seconds() * 1000)
                    entry_ts = ts + delay_ms
                    entry_open = self._next_open(s, entry_ts)
                    if entry_open is None:
                        continue

                    # SL/TP from your executor (expects candles_by_tf first)
                    try:
                        sl_px, tp_px, sl_pct, trailing_pct, tp_pct = calculate_dynamic_sl_tp(
                            candles_by_tf=cb,
                            price=entry_open,
                            trade_type=trade_type,
                            direction=direction,
                            score=score,
                            confidence=confidence,
                            regime="trending"
                        )
                    except Exception as e:
                        # Fallback: modest asymmetrical targets
                        if direction.lower() == "long":
                            sl_px = entry_open * 0.99; tp_px = entry_open * 1.015
                        else:
                            sl_px = entry_open * 1.01; tp_px = entry_open * 0.985
                        sl_pct, tp_pct, trailing_pct = 0.01, 0.015, 0.0

                    # Build trade
                    risk_ccy = balance * RISK_PER_TRADE
                    pos_val  = risk_ccy * LEVERAGE

                    trade_id += 1
                    open_trades[trade_id] = {
                        "id": trade_id,
                        "symbol": s,
                        "strategy": "core_strategy",
                        "entry_time": ms_to_iso(entry_ts),
                        "entry_ts": entry_ts,
                        "direction": "Long" if direction.lower().startswith("l") else "Short",
                        "entry_price": entry_open,
                        "sl_price": sl_px,
                        "tp1_price": tp_px,
                        "score": score,
                        "confidence": confidence,
                        "trade_type": trade_type if trade_type in MAX_HOLD_H else "Intraday",
                        "reserved_margin": risk_ccy,
                        "position_value": pos_val,
                        "_funding_paid": 0.0
                    }
                    balance -= risk_ccy  # reserve margin
                    # one strategy per symbol at this instant
                    # (remove this 'break' if you want to try more strategies per symbol)
                    # break

        # force-close leftovers
        if timeline:
            final_ts = timeline[-1]
            for tr in list(open_trades.values()):
                exit_info = self._force_close(tr, final_ts)
                pnl_ccy = exit_info["pnl"]
                balance += (tr["reserved_margin"] + pnl_ccy)
                tr_out = {**tr, **{
                    "exit_time": ms_to_iso(final_ts),
                    "exit_price": exit_info["exit_price"],
                    "exit_reason": "backtest_end",
                    "pnl_ccy": pnl_ccy,
                    "pnl_pct_pos": (pnl_ccy / tr["position_value"]) * 100 if tr["position_value"] else 0.0,
                    "minutes": (final_ts - tr["entry_ts"]) // 60000
                }}
                self.trades.append(tr_out)

        self._report(balance_start=initial_balance, balance_end=balance)

    async def _download(self, symbols: List[str], start_ms: int, end_ms: int):
        for s in symbols:
            self.hdata[s] = {}
            for tf in TIMEFRAMES:
                try:
                    self.hdata[s][tf] = await fetch_klines(s, tf, start_ms, end_ms)
                except Exception as e:
                    log(f"❌ fetch {s} {tf}m failed: {e}", level="ERROR")
            # funding (best-effort)
            self.funding_events[s] = await fetch_funding(s, start_ms, end_ms)
            await asyncio.sleep(0.05)

    # ---------- slicing helpers ----------
    def _candles_up_to(self, symbol: str, ts: int) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        if symbol not in self.hdata: return None
        out: Dict[str, List[Dict[str, Any]]] = {}
        for tf in TIMEFRAMES:
            arr = self.hdata[symbol].get(tf)
            if not arr: continue
            # slice ≤ ts
            # (list is sorted; we can binary search, but simple filter is fine for clarity)
            sub = [c for c in arr if c["timestamp"] <= ts]
            if len(sub) >= 30:
                out[tf] = sub[-100:]
        return out or None

    def _next_open(self, symbol: str, ts: int) -> Optional[float]:
        arr = self.hdata.get(symbol, {}).get('1')
        if not arr: return None
        lo, hi, ans = 0, len(arr)-1, None
        while lo <= hi:
            mid = (lo+hi)//2
            if arr[mid]["timestamp"] > ts:
                ans = mid; hi = mid-1
            else:
                lo = mid+1
        return arr[ans]["open"] if ans is not None else None

    def _candle_at(self, symbol: str, ts: int) -> Optional[Dict[str, Any]]:
        arr = self.hdata.get(symbol, {}).get('1')
        if not arr: return None
        lo, hi = 0, len(arr)-1
        while lo <= hi:
            mid = (lo+hi)//2
            t = arr[mid]["timestamp"]
            if t == ts: return arr[mid]
            if t < ts: lo = mid+1
            else: hi = mid-1
        return None

    # ---------- exit logic with mark-style triggers, costs & funding ----------
    def _check_exit(self, tr: Dict[str, Any], ts: int) -> Optional[Dict[str, Any]]:
        c = self._candle_at(tr["symbol"], ts)
        if c is None: return None

        hi_raw, lo_raw = float(c["high"]), float(c["low"])
        hi_eff, lo_eff = mark_adjusted_hi_lo(hi_raw, lo_raw, tr["direction"])
        sl, tp = tr.get("sl_price"), tr.get("tp1_price")

        # funding accrual if a funding timestamp crossed this bar (approx per 8h)
        tr["_funding_paid"] += self._funding_accrual(tr, ts)

        # decide exit (stop-first for conservative outcome)
        if tr["direction"] == "Long":
            # stop?
            if sl and lo_eff <= sl:
                exit_px = sl * (1 - dynamic_slip_pct(c))
                pnl = self._pnl_net(tr["entry_price"], exit_px, "Long", tr["position_value"]) - tr["_funding_paid"]
                return {"exit_price": exit_px, "reason": "stop", "pnl": pnl}
            # tp?
            if tp and hi_eff >= tp:
                exit_px = tp * (1 + dynamic_slip_pct(c))
                pnl = self._pnl_net(tr["entry_price"], exit_px, "Long", tr["position_value"]) - tr["_funding_paid"]
                return {"exit_price": exit_px, "reason": "tp", "pnl": pnl}
        else: # Short
            if sl and hi_eff >= sl:
                exit_px = sl * (1 + dynamic_slip_pct(c))
                pnl = self._pnl_net(tr["entry_price"], exit_px, "Short", tr["position_value"]) - tr["_funding_paid"]
                return {"exit_price": exit_px, "reason": "stop", "pnl": pnl}
            if tp and lo_eff <= tp:
                exit_px = tp * (1 - dynamic_slip_pct(c))
                pnl = self._pnl_net(tr["entry_price"], exit_px, "Short", tr["position_value"]) - tr["_funding_paid"]
                return {"exit_price": exit_px, "reason": "tp", "pnl": pnl}

        # time exit
        held_h = (ts - tr["entry_ts"]) / 3_600_000
        if held_h >= MAX_HOLD_H.get(tr["trade_type"], 24):
            exit_px = float(c["close"])
            # apply exit slippage even on time exit
            slip_factor = (1 + dynamic_slip_pct(c)) if tr["direction"] == "Long" else (1 - dynamic_slip_pct(c))
            exit_px = exit_px * slip_factor
            pnl = self._pnl_net(tr["entry_price"], exit_px, tr["direction"], tr["position_value"]) - tr["_funding_paid"]
            return {"exit_price": exit_px, "reason": "time", "pnl": pnl}

        return None

    def _force_close(self, tr: Dict[str, Any], ts: int) -> Dict[str, Any]:
        c = self._candle_at(tr["symbol"], ts)
        px = float(c["close"]) if c else tr["entry_price"]
        pnl = self._pnl_net(tr["entry_price"], px, tr["direction"], tr["position_value"]) - tr["_funding_paid"]
        return {"exit_price": px, "pnl": pnl}

    def _pnl_net(self, entry: float, exit_: float, side: str, notional: float) -> float:
        gross_pct = ((exit_ - entry) / entry) if side == "Long" else ((entry - exit_) / entry)
        net_pct = gross_pct - (2*FEE_TAKER_PCT) - (2*BASE_SLIP_BPS/1e4)  # baseline fee+slip baked in; dynamic added via prices
        return notional * net_pct

    def _funding_accrual(self, tr: Dict[str, Any], ts: int) -> float:
        """
        Approx funding: sum rate * notional for each 8h event crossed.
        If we don't have events, return 0.
        """
        sym = tr["symbol"]
        events = self.funding_events.get(sym) or []
        if not events: return 0.0

        # If the bar crosses a funding timestamp (ts is bar timestamp), and entry < event <= ts ⇒ accrue.
        accrual = 0.0
        for (t_ev, rate) in events:
            if tr["entry_ts"] < t_ev <= ts:
                # Payer depends on direction and sign convention; assuming positive rate ⇒ longs pay
                pay = (rate if tr["direction"] == "Long" else -rate) * tr["position_value"]
                accrual += pay
        return accrual

    # ---------- report ----------
    def _report(self, balance_start: float, balance_end: float):
        n = len(self.trades)
        wins = [t for t in self.trades if t["pnl_ccy"] > 0]
        losses = [t for t in self.trades if t["pnl_ccy"] < 0]
        win_rate = len(wins)/n if n else 0
        pf = (sum(t["pnl_ccy"] for t in wins) / max(1e-9, abs(sum(t["pnl_ccy"] for t in losses)))) if losses else 999.0
        avg_trade_pct = sum(t["pnl_pct_pos"] for t in self.trades)/n if n else 0.0

        print("\n" + "="*72)
        print("🎯 REALISTIC BACKTEST REPORT")
        print("="*72)
        print(f"Trades: {n} | Win rate: {win_rate:.1%} | Profit Factor: {pf:.2f} | Avg trade: {avg_trade_pct:+.3f}%")
        print(f"Equity: ${balance_start:,.2f} → ${balance_end:,.2f}  (Return: {(balance_end-balance_start)/balance_start*100:+.2f}%)")
        if self.trades:
            with open("realistic_trades.csv","w") as f:
                # minimal CSV
                f.write("time,symbol,dir,entry,exit,reason,pnl_ccy,pnl_pct,minutes,score,conf\n")
                for t in self.trades:
                    f.write(f"{t['entry_time']},{t['symbol']},{t['direction']},{t['entry_price']:.6f},"
                            f"{t.get('exit_price', t['entry_price']):.6f},{t.get('exit_reason','')},"
                            f"{t['pnl_ccy']:.2f},{t['pnl_pct_pos']:.3f},{t['minutes']},"
                            f"{t['score']:.2f},{t['confidence']}\n")
        with open("realistic_backtest_report.json","w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "trades": self.trades,
                "daily_pnl": self.daily_pnl,
                "equity_start": balance_start,
                "equity_end": balance_end
            }, f, indent=2)
        print("📄 Saved: realistic_backtest_report.json, realistic_trades.csv")
        print("="*72)

# ---------- runners ----------
async def run_quick():
    symbols = ["BTCUSDT","ETHUSDT","SOLUSDT","LINKUSDT","AVAXUSDT"]
    rb = RealisticBacktester()
    await rb.run(symbols, days=7, initial_balance=10_000)

async def run_full():
    symbols = [
        "BTCUSDT","ETHUSDT","SOLUSDT","LINKUSDT","AVAXUSDT",
        "ADAUSDT","XRPUSDT","DOTUSDT","UNIUSDT","LTCUSDT",
    ]
    rb = RealisticBacktester()
    await rb.run(symbols, days=14, initial_balance=10_000)

if __name__ == "__main__":
    print("1) Quick (7d, 5 syms)  2) Full (14d, 10 syms)")
    choice = input("> ").strip()
    if choice == "2":
        asyncio.run(run_full())
    else:
        asyncio.run(run_quick())
