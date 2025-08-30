# comprehensive_backtest.py - Complete Strategy Backtesting System
# Test ALL your trading strategies: Core, Mean Reversion, Breakout Sniper, Pattern Matching, Range Break, Stealth Detection, Pump Detection

import asyncio
import json
import os
import pandas as pd
import bisect
import random
import csv
from datetime import datetime, timedelta
from collections import defaultdict
import time
from logger import log
from bybit_api import signed_request

# Import all your strategies
from score import enhanced_score_symbol, score_symbol, determine_direction, calculate_confidence, has_pump_potential, detect_momentum_strength
from mean_reversion import score_mean_reversion
from breakout_sniper import score_breakout_sniper
from pattern_matcher import pattern_match_scan
from pattern_discovery import pattern_discovery_scan
from range_break_detector import range_break_detector, scan_for_breaks_and_pumps
from stealth_detector import detect_stealth_accumulation_advanced, calculate_accumulation_score
from pump_detector import detect_early_pump
from trend_filters import get_trend_context_cached
from trade_executor import calculate_dynamic_sl_tp

FEE_PCT = 0.0006     # 0.06% taker per side
SLIP_PCT = 0.0002    # 0.02% slippage per side
CATEGORY = 'linear'  # 'linear' for USDT-perps, 'spot' for spot
LEVERAGE = 5
MAX_HOLD_MIN = {"Scalp": 60, "Intraday": 240, "Swing": 1440}


class ComprehensiveBacktester:
    def __init__(self):
        self.historical_data = {}
        self.all_trades = []
        self.strategy_performance = defaultdict(list)
        self.daily_pnl = defaultdict(float)
        self._ts_index = {}
        self.sig_stats = defaultdict(lambda: defaultdict(int))
        self.debug_signals = []
        
        # Enhanced strategy configurations with ALL your strategies
        self.strategies = {
            'core_strategy': {
                'function': self.test_core_strategy,
                'min_score': 7.0,
                'enabled': True,
                'description': 'Main trend-following strategy',
                'needs': ['1','3','5','15','30','60','240']
            },
            'enhanced_core': {
                'function': self.test_enhanced_core_strategy,
                'min_score': 8.0,
                'enabled': True,
                'description': 'Enhanced core with advanced scoring',
                'needs': ['1','3','5','15','30','60','240']
            },
            'mean_reversion': {
                'function': self.test_mean_reversion,
                'min_score': 4.0,
                'enabled': True,
                'description': 'Mean reversion for ranging markets',
                'needs': ['1','5','15','60']
            },
            'breakout_sniper': {
                'function': self.test_breakout_sniper,
                'min_score': 4.0,
                'enabled': True,
                'description': 'Breakout detection with patterns',
                'needs': ['1','5','15']
            },
            'pattern_matching': {
                'function': self.test_pattern_matching,
                'min_score': 0.6,
                'enabled': True,
                'description': 'Historical pattern matching',
                'needs': ['1','5']
            },
            'pattern_discovery': {
                'function': self.test_pattern_discovery,
                'min_score': 0.7,
                'enabled': True,
                'description': 'Dynamic pattern discovery',
                'needs': ['1','5']
            },
            'range_break': {
                'function': self.test_range_break,
                'min_score': 6.0,
                'enabled': True,
                'description': 'Range breakout detection',
                'needs': ['1','15']
            },
            'stealth_accumulation': {
                'function': self.test_stealth_accumulation,
                'min_score': 0.6,
                'enabled': True,
                'description': 'Stealth accumulation detection',
                'needs': ['1','5']
            },
            'pump_detector': {
                'function': self.test_pump_detector,
                'min_score': 0.7,
                'enabled': True,
                'description': 'Early pump detection',
                'needs': ['1','3']
            },
            'momentum_surge': {
                'function': self.test_momentum_surge,
                'min_score': 8.0,
                'enabled': True,
                'description': 'Strong momentum detection',
                'needs': ['1','3','15']
            }
        }

        self.sig_stats = defaultdict(lambda: defaultdict(int))
        self.debug_signals = []

    async def run_comprehensive_backtest(self, symbols, days=30, initial_balance=10000):
        """Run complete backtest on all strategies"""
        
        log(f"🚀 Starting comprehensive {days}-day backtest")
        log(f"💰 Initial balance: ${initial_balance:,.2f}")
        log(f"📊 Testing {len(symbols)} symbols")
        log(f"🎯 Strategies: {[name for name, config in self.strategies.items() if config['enabled']]}")
        
        # Step 1: Download historical data
        await self.download_all_historical_data(symbols, days)
        
        # Step 2: Run backtests for each strategy
        await self.backtest_all_strategies(symbols, days, initial_balance)
        
        # Step 3: Generate comprehensive report
        self.generate_comprehensive_report(initial_balance)
        
        log("✅ Comprehensive backtest completed!")

    async def _fetch_klines_cursor(self, symbol, tf, start_ms, end_ms):
        candles, cursor, first = [], None, True
        while True:
            params = {
                'category': CATEGORY,
                'symbol': symbol,
                'interval': tf,
                'start': start_ms,
                'end': end_ms,
                'limit': 1000,
            }
            if cursor:
                params['cursor'] = cursor
            if first:
                log(f"🔗 GET /v5/market/kline {symbol} {tf}m "
                    f"{datetime.utcfromtimestamp(start_ms/1000).isoformat()}→"
                    f"{datetime.utcfromtimestamp(end_ms/1000).isoformat()} UTC")
                first = False

            resp = await signed_request('GET', '/v5/market/kline', params)
            if resp.get('retCode') != 0:
                log(f"❌ API error {symbol} {tf}m: {resp}", level='ERROR'); break
            lst = resp.get('result', {}).get('list', []) or []
            for k in lst:
                candles.append({
                    'timestamp': int(k[0]),
                    'open': float(k[1]), 'high': float(k[2]),
                    'low': float(k[3]),  'close': float(k[4]),
                    'volume': float(k[5]),
                })
            cursor = resp.get('result', {}).get('nextPageCursor')
            if not cursor or not lst:
                break
            await asyncio.sleep(0.02)

        candles.sort(key=lambda x: x['timestamp'])
        return candles

    async def download_all_historical_data(self, symbols, days):
        log(f"📥 Downloading {days} days of historical data...")
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - days * 24 * 60 * 60 * 1000

        needed_tfs = sorted({tf for s in self.strategies.values() if s["enabled"] for tf in s["needs"]})
        sem = asyncio.Semaphore(10)
        self.historical_data = {}
        self._ts_index = {}

        async def fetch_one(sym, tf):
            async with sem:
                candles = await self._fetch_klines_cursor(sym, tf, start_ms, end_ms)  # your cursor fetcher
                self.historical_data.setdefault(sym, {})[tf] = candles
                self._ts_index.setdefault(sym, {})[tf] = [c["timestamp"] for c in candles]
                log(f"   ✅ {sym} {tf}m: {len(candles)} candles")

        tasks = [asyncio.create_task(fetch_one(s, tf)) for s in symbols for tf in needed_tfs]
        await asyncio.gather(*tasks)
        log("✅ Historical download complete")

    def _latency_ms(self):
        v = random.normalvariate(3000, 1000)  # ~3s ±1s, clamped
        return int(min(12000, max(0, v)))

    def _candle_at(self, symbol, ts):
        series = self.historical_data.get(symbol, {}).get("1")
        if not series: return None
        ts_list = self._ts_index[symbol]["1"]
        i = bisect.bisect_left(ts_list, ts)
        if i < len(series) and series[i]["timestamp"] == ts:
            return series[i]
        return None

    def get_price_at_timestamp(self, symbol, timestamp):
        """Get price at specific timestamp (using 1m candles)"""
        series = self.historical_data.get(symbol, {}).get('1')
        if not series:
            return None
        
        ts_list = self._ts_index[symbol]['1']
        i = bisect.bisect_right(ts_list, timestamp)
        
        return series[i-1]['close'] if i > 0 else None

    def get_next_open(self, symbol, ts):
        series = self.historical_data.get(symbol, {}).get("1")
        if not series: return None
        i = bisect.bisect_right(self._ts_index[symbol]["1"], ts)
        return series[i]["open"] if 0 <= i < len(series) else None

    async def backtest_all_strategies(self, symbols, days, initial_balance):
        """Run backtest simulation across all enabled strategies"""
        log("🧪 Running comprehensive strategy backtests...")
        
        current_balance = initial_balance
        open_trades = {}
        trade_id = 0
        
        # Get all timestamps for simulation (using 1m candles as base)
        all_timestamps = set()
        for symbol in symbols:
            if symbol in self.historical_data and '1' in self.historical_data[symbol]:
                timestamps = [c['timestamp'] for c in self.historical_data[symbol]['1']]
                all_timestamps.update(timestamps)
        
        sorted_timestamps = sorted(all_timestamps)
        
        log(f"📈 Processing {len(sorted_timestamps)} timestamps...")
        
        # Simulate trading at each timestamp
        for i, timestamp in enumerate(sorted_timestamps):
            if i % 2000 == 0:  # Progress update every 2000 timestamps
                progress = (i / len(sorted_timestamps)) * 100
                log(f"📊 Progress: {progress:.1f}% ({i}/{len(sorted_timestamps)})")
            
            current_time = datetime.fromtimestamp(timestamp / 1000)
            
            # Check exits first
            trades_to_close = []
            for trade_id_key, trade in open_trades.items():
                exit_result = self.check_trade_exit(trade, timestamp)
                if exit_result:
                    trades_to_close.append((trade_id_key, trade, exit_result))
            
            # Close trades and update balance
            for trade_id_key, trade, exit_result in trades_to_close:
                pnl = exit_result['pnl']
                current_balance += (trade.get('reserved_margin', 0) + pnl)
                
                # Record completed trade
                completed_trade = {
                    **trade,
                    'exit_time': datetime.fromtimestamp(timestamp / 1000).isoformat(),
                    'exit_price': exit_result['exit_price'],
                    'exit_reason': exit_result['reason'],
                    'pnl': pnl,
                    'pnl_pct': (pnl / trade['position_value']) * 100,
                    'duration_minutes': (timestamp - trade['entry_timestamp']) // 60000
                }
                
                self.all_trades.append(completed_trade)
                self.strategy_performance[trade['strategy']].append(completed_trade)
                
                del open_trades[trade_id_key]
            
            # Don't open new trades if we have too many open
            if len(open_trades) >= 5:  # Max 5 concurrent trades
                continue
                
            # Check for new signals for each symbol
            for symbol in symbols:
                if len(open_trades) >= 5:
                    break
                
                # Skip if already have a trade on this symbol
                if any(trade['symbol'] == symbol for trade in open_trades.values()):
                    continue
                
                candles_by_tf = self._candle_at(symbol, timestamp)
                if not candles_by_tf or '1' not in candles_by_tf:
                    continue
                
                # Test each enabled strategy
                candidates = []
                for strategy_name, strategy_config in self.strategies.items():
                    if not strategy_config['enabled']:
                        continue
                    if len(open_trades) >= 5:
                        break

                    # Ensure TF coverage for this strategy
                    missing = [tf for tf in strategy_config.get('needs', []) if tf not in candles_by_tf]
                    if missing:
                        self.sig_stats[strategy_name]["missing_tf"] += 1
                        continue

                    try:
                        sig = await strategy_config['function'](symbol, candles_by_tf, timestamp)
                    except Exception as e:
                        self.sig_stats[strategy_name]["exception"] += 1
                        continue

                    if not sig:
                        self.sig_stats[strategy_name]["no_signal"] += 1
                        continue
                    if sig.get('score', 0) < strategy_config['min_score']:
                        self.sig_stats[strategy_name]["below_threshold"] += 1
                        if len(self.debug_signals) < 200:
                            self.debug_signals.append({"t": timestamp, "sym": symbol, "strat": strategy_name, "score": sig.get("score", 0)})
                        continue

                    self.sig_stats[strategy_name]["fired"] += 1
                    candidates.append((strategy_name, sig))

                # --- pick the strongest candidate (by score)
                if not candidates:
                    continue
                strategy_name, signal = max(candidates, key=lambda x: x[1].get('score', 0))
                            
                # --- ENTRY EXECUTION (latency -> next 1m open) ---
                delay_ms = random.randint(2000, 6000)
                exec_ts = timestamp + delay_ms
                entry_price = self.get_next_open(symbol, exec_ts)
                if not entry_price:
                    continue

                # --- RECOMPUTE SL/TP AROUND THE REAL ENTRY ---
                try:
                    sl_price, tp1_price, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                        candles_by_tf=candles_by_tf,
                        price=entry_price,
                        trade_type=signal.get('trade_type', 'Intraday'),
                        direction=signal['direction'],
                        score=signal.get('score', 0),
                        confidence=signal.get('confidence', 0),
                        regime='trending'
                    )
                except Exception:
                    if signal.get('sl_price') and signal.get('tp1_price'):
                        old_entry = self.get_price_at_timestamp(symbol, timestamp) or entry_price
                        scale = entry_price / old_entry if old_entry else 1.0
                        sl_price = signal['sl_price'] * scale
                        tp1_price = signal['tp1_price'] * scale
                        sl_pct = abs((entry_price - sl_price) / entry_price) * 100
                        tp1_pct = abs((tp1_price - entry_price) / entry_price) * 100
                    else:
                        if signal['direction'] == 'Long':
                            sl_price, tp1_price, sl_pct, tp1_pct = entry_price*0.99, entry_price*1.015, 1.0, 1.5
                        else:
                            sl_price, tp1_price, sl_pct, tp1_pct = entry_price*1.01, entry_price*0.985, 1.0, 1.5

                  # --- LEVERAGE-AWARE SIZING (reserve margin, not full notional) ---
                risk_ccy = current_balance * 0.02                   # 2% risk
                sl_dist_pct = max(1e-6, abs(sl_pct)) / 100.0
                target_notional = risk_ccy / sl_dist_pct
                max_margin = current_balance * 0.05                 # cap margin per trade
                margin = min(target_notional / LEVERAGE, max_margin)
                notional = margin * LEVERAGE
                if margin < 50:                                     # ignore tiny orders
                    continue

                # --- OPEN THE TRADE ---
                trade_id += 1
                trade = {
                    "id": trade_id,
                    "strategy": strategy_name,
                    "symbol": symbol,
                    "entry_time": datetime.utcfromtimestamp(exec_ts/1000).isoformat(),
                    "entry_timestamp": exec_ts,
                    "entry_price": entry_price,
                    "direction": signal["direction"],
                    "position_value": notional,
                    "score": float(signal.get("score", 0)),
                    "confidence": float(signal.get("confidence", 0)),
                    "sl_price": sl_price,
                    "tp1_price": tp1_price,
                    "trade_type": signal.get("trade_type", "Intraday"),
                    "reserved_margin": margin,
                }
                open_trades[trade_id] = trade
                current_balance -= margin  # Reserve margin

                # Only take one signal per symbol per timestamp
                break
                                
        
        # Close any remaining open trades at the end
        final_timestamp = sorted_timestamps[-1] if sorted_timestamps else int(time.time() * 1000)
        for trade in list(open_trades.values()):
            last_c = self._candle_at(trade['symbol'], final_timestamp)
            if not last_c:
                continue
            cls = last_c['close']
            dirn = trade['direction']
            exit_px = cls*(1+SLIP_PCT) if dirn == 'Long' else cls*(1-SLIP_PCT)

            def pnl_net(entry, exit_):
                gross = (exit_ - entry)/entry if dirn == 'Long' else (entry - exit_)/entry
                net = gross - (2*FEE_PCT) - (2*SLIP_PCT)
                return net * trade['position_value']

            pnl = pnl_net(trade['entry_price'], exit_px)
            current_balance += (trade.get('reserved_margin', 0) + pnl)

            completed_trade = {
                **trade,
                'exit_time': datetime.fromtimestamp(final_timestamp / 1000).isoformat(),
                'exit_price': exit_px,
                'exit_reason': 'backtest_end',
                'pnl': pnl,
                'pnl_pct': (pnl / trade['position_value']) * 100,
                'duration_minutes': (final_timestamp - trade['entry_timestamp']) // 60000
            }
            self.all_trades.append(completed_trade)
            self.strategy_performance[trade['strategy']].append(completed_trade)

        final_balance = current_balance
        log(f"💰 Final balance: ${final_balance:,.2f}")
        log(f"📈 Total return: {total_return:+.2f}%")
        log(f"📊 Total trades: {len(self.all_trades)}")

    def _candle_at(self, symbol, ts):
        series = self.historical_data.get(symbol, {}).get('1')
        if not series: return None
        ts_list = self._ts_index[symbol]['1']
        i = bisect.bisect_left(ts_list, ts)
        if i < len(series) and series[i]['timestamp'] == ts:
            return series[i]
        return None

    def check_trade_exit(self, trade, timestamp):
        
        c = self._candle_at(trade['symbol'], timestamp)
        if not c: 
            return None
        hi, lo, cls = c['high'], c['low'], c['close']
        entry, sl, tp, dirn = trade['entry_price'], trade.get('sl_price'), trade.get('tp1_price'), trade['direction']

        def pnl_with_costs(exit_px):
            # taker + simple slippage on both sides
            gross = ((exit_px - entry)/entry) if dirn == 'Long' else ((entry - exit_px)/entry)
            net = gross - (2*FEE_PCT) - (2*SLIP_PCT)
            return net * trade['position_value']

        # stop-first (conservative path)
        if dirn == 'Long':
            if sl and lo <= sl:
                return {'exit_price': sl*(1-SLIP_PCT), 'reason':'stop_loss', 'pnl': pnl_with_costs(sl*(1-SLIP_PCT))}
            if tp and hi >= tp:
                return {'exit_price': tp*(1+SLIP_PCT), 'reason':'take_profit', 'pnl': pnl_with_costs(tp*(1+SLIP_PCT))}
        else:
            if sl and hi >= sl:
                return {'exit_price': sl*(1+SLIP_PCT), 'reason':'stop_loss', 'pnl': pnl_with_costs(sl*(1+SLIP_PCT))}
            if tp and lo <= tp:
                return {'exit_price': tp*(1-SLIP_PCT), 'reason':'take_profit', 'pnl': pnl_with_costs(tp*(1-SLIP_PCT))}

        # time-based exit using caps per type
        held = (timestamp - trade['entry_timestamp']) // 60000
        limit_min = MAX_HOLD_MIN.get(trade.get('trade_type','Intraday'), 240)
        if held >= limit_min:
            exit_px = cls*(1+SLIP_PCT) if dirn=='Long' else cls*(1-SLIP_PCT)
            return {'exit_price': exit_px, 'reason': 'time_exit', 'pnl': pnl_with_costs(exit_px)}


        return None


    # STRATEGY TESTING FUNCTIONS

    async def test_core_strategy(self, symbol, candles_by_tf, timestamp):
        """Test core strategy at specific timestamp"""
        try:
            score, tf_scores, trade_type, indicator_scores, used_indicators = score_symbol(
                symbol, candles_by_tf
            )
            
            if score < 7.0:
                return None
            
            direction = determine_direction(tf_scores)
            if not direction:
                return None

            try:
                trend_ctx = await get_trend_context_cached()
            except Exception:
                trend_ctx = {"btc_trend": "ranging", "regime": "volatile"}
            
            confidence = calculate_confidence(score, tf_scores, trend_ctx, trade_type)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Calculate SL/TP
            try:
                sl_price, tp1_price, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                    candles_by_tf=candles_by_tf,
                    price=self.get_price_at_timestamp(symbol, timestamp) or 0.0,
                    trade_type=trade_type,
                    direction=direction,
                    score=score,
                    confidence=confidence,
                    regime=trend_ctx.get('regime', 'trending') if isinstance(trend_ctx, dict) else 'trending'
                )
            except:
                # Fallback SL/TP calculation
                if direction == "Long":
                    sl_price = entry_price * 0.98  # 2% SL
                    tp1_price = entry_price * 1.04  # 4% TP
                else:
                    sl_price = entry_price * 1.02
                    tp1_price = entry_price * 0.96
                sl_pct, tp1_pct = 2.0, 4.0
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': trade_type,
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': sl_pct,
                'tp1_pct': tp1_pct
            }
            
        except Exception as e:
            return None

    async def test_enhanced_core_strategy(self, symbol, candles_by_tf, timestamp):
        """Test enhanced core strategy"""
        try:
            score, tf_scores, trade_type, indicator_scores, used_indicators = enhanced_score_symbol(
                symbol, candles_by_tf
            )
            
            if score < 8.0:
                return None
            
            direction = determine_direction(tf_scores)
            if not direction:
                return None

            try:
                trend_ctx = await get_trend_context_cached()
            except Exception:
                trend_ctx = {"btc_trend": "ranging", "regime": "volatile"}
            
            confidence = calculate_confidence(score, tf_scores, trend_ctx, trade_type)
            strategy_name, signal = max(candidates, key=lambda x: x[1].get('score', 0))
            
            delay_ms = random.randint(2000, 6000)
            exec_ts = timestamp + delay_ms
            entry_price = self.get_next_open(symbol, exec_ts)
            if not entry_price is not None:

                # Recompute SL/TP around the real entry
                try:
                    sl_price, tp1_price, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                        candles_by_tf=candles_by_tf,
                        price=entry_price,
                        trade_type=signal.get('trade_type', 'Intraday'),
                        direction=signal['direction'],
                        score=signal.get('score', 0),
                        confidence=signal.get('confidence', 0),
                        regime='trending'
                    )
                except Exception:
                    if signal.get('sl_price') and signal.get('tp1_price'):
                        old_entry = self.get_price_at_timestamp(symbol, timestamp) or entry_price
                        scale = entry_price / old_entry if old_entry else 1.0
                        sl_price = signal['sl_price'] * scale
                        tp1_price = signal['tp1_price'] * scale
                        sl_pct = abs((entry_price - sl_price) / entry_price) * 100
                        tp1_pct = abs((tp1_price - entry_price) / entry_price) * 100
                    else:
                        if signal['direction'] == 'Long':
                            sl_price, tp1_price, sl_pct, tp1_pct = entry_price*0.99, entry_price*1.015, 1.0, 1.5
                        else:
                            sl_price, tp1_price, sl_pct, tp1_pct = entry_price*1.01, entry_price*0.985, 1.0, 1.5

            # Leverage-aware sizing (reserve margin, not full notional)
            risk_ccy = current_balance * 0.02
            sl_dist_pct = max(1e-6, abs(sl_pct)) / 100.0
            target_notional = risk_ccy / sl_dist_pct
            max_margin = current_balance * 0.05
            margin = min(target_notional / LEVERAGE, max_margin)
            notional = margin * LEVERAGE
            if margin < 50:
                trade_id += 1
                trade = {
                    "id": trade_id,
                    "strategy": strategy_name,
                    "symbol": symbol,
                    "entry_time": datetime.utcfromtimestamp(exec_ts/1000).isoformat(),
                    "entry_timestamp": exec_ts,
                    "entry_price": entry_price,
                    "direction": signal["direction"],
                    "position_value": notional,
                    "score": float(signal.get("score", 0)),
                    "confidence": float(signal.get("confidence", 0)),
                    "sl_price": sl_price,
                    "tp1_price": tp1_price,
                    "trade_type": signal.get("trade_type", "Intraday"),
                    "reserved_margin": margin,
                } 
                open_trades[trade_id] = trade
                current_balance -= margin

        except Exception as e:
            return None

    async def test_mean_reversion(self, symbol, candles_by_tf, timestamp):
        """Test mean reversion strategy"""
        try:
            score, direction, confidence, reasons = score_mean_reversion(
                symbol, candles_by_tf, "ranging"
            )
            
            if score < 4.0:
                return None
            
            delay_ms = random.randint(2000, 6000)
            exec_ts = timestamp + delay_ms
            entry_price = self.get_next_open(symbol, exec_ts)
            if not entry_price is not None:

                # Recompute SL/TP around the real entry
                try:
                    sl_price, tp1_price, sl_pct, trailing_pct, tp1_pct = calculate_dynamic_sl_tp(
                    candles_by_tf=candles_by_tf,
                    price=entry_price,
                    trade_type=signal.get('trade_type', 'Intraday'),
                    direction=signal['direction'],
                    score=signal.get('score', 0),
                    confidence=signal.get('confidence', 0),
                    regime='trending'
                   )
                except Exception:
                    if signal.get('sl_price') and signal.get('tp1_price'):
                        old_entry = self.get_price_at_timestamp(symbol, timestamp) or entry_price
                        scale = entry_price / old_entry if old_entry else 1.0
                        sl_price = signal['sl_price'] * scale
                        tp1_price = signal['tp1_price'] * scale
                        sl_pct = abs((entry_price - sl_price) / entry_price) * 100
                        tp1_pct = abs((tp1_price - entry_price) / entry_price) * 100
                    else:
                        if signal['direction'] == 'Long':
                            sl_price, tp1_price, sl_pct, tp1_pct = entry_price*0.99, entry_price*1.015, 1.0, 1.5
                        else:
                            sl_price, tp1_price, sl_pct, tp1_pct = entry_price*1.01, entry_price*0.985, 1.0, 1.5

            # Leverage-aware sizing (reserve margin, not full notional)
            risk_ccy = current_balance * 0.02
            sl_dist_pct = max(1e-6, abs(sl_pct)) / 100.0
            target_notional = risk_ccy / sl_dist_pct
            max_margin = current_balance * 0.05
            margin = min(target_notional / LEVERAGE, max_margin)
            notional = margin * LEVERAGE
            if margin < 50:
                trade_id += 1
                trade = {
                    "id": trade_id,
                    "strategy": strategy_name,
                    "symbol": symbol,
                    "entry_time": datetime.utcfromtimestamp(exec_ts/1000).isoformat(),
                    "entry_timestamp": exec_ts,
                    "entry_price": entry_price,
                    "direction": signal["direction"],
                    "position_value": notional,
                    "score": float(signal.get("score", 0)),
                    "confidence": float(signal.get("confidence", 0)),
                    "sl_price": sl_price,
                    "tp1_price": tp1_price,
                    "trade_type": signal.get("trade_type", "Intraday"),
                    "reserved_margin": margin,
                } 
                open_trades[trade_id] = trade
                current_balance -= margin

        except Exception as e:
            return None


    async def test_breakout_sniper(self, symbol, candles_by_tf, timestamp):
        """Test breakout sniper strategy"""
        try:
            score, direction, confidence, reasons = score_breakout_sniper(
                symbol, candles_by_tf, "volatile"
            )
            
            if score < 4.0:
                return None
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Breakout SL/TP (wider stops for volatility)
            if direction == "Long":
                sl_price = entry_price * 0.975  # 2.5% SL
                tp1_price = entry_price * 1.06   # 6% TP
            else:
                sl_price = entry_price * 1.025
                tp1_price = entry_price * 0.94
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.5,
                'tp1_pct': 6.0
            }
            
        except Exception as e:
            return None

    async def test_pattern_matching(self, symbol, candles_by_tf, timestamp):
        """Test pattern matching strategy"""
        try:
            if '5' not in candles_by_tf:
                return None
                
            result = pattern_match_scan(symbol, candles_by_tf['5'])
            if not result or result.get('similarity', 0) < 0.6:
                return None
            
            direction = result.get('expected_direction', 'Long')
            similarity = result.get('similarity', 0)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Pattern-based SL/TP
            if direction == "Long":
                sl_price = entry_price * 0.98
                tp1_price = entry_price * 1.04
            else:
                sl_price = entry_price * 1.02
                tp1_price = entry_price * 0.96
            
            return {
                'score': similarity * 10,  # Convert to score
                'direction': direction,
                'confidence': similarity,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.0,
                'tp1_pct': 4.0
            }
            
        except Exception as e:
            return None

    async def test_pattern_discovery(self, symbol, candles_by_tf, timestamp):
        """Test pattern discovery strategy"""
        try:
            if '5' not in candles_by_tf:
                return None
                
            result = pattern_discovery_scan(symbol, candles_by_tf['5'])
            if not result or result.get('confidence', 0) < 0.7:
                return None
            
            direction = result.get('direction', 'Long')
            confidence = result.get('confidence', 0)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Discovery pattern SL/TP
            if direction == "Long":
                sl_price = entry_price * 0.98
                tp1_price = entry_price * 1.045
            else:
                sl_price = entry_price * 1.02
                tp1_price = entry_price * 0.955
            
            return {
                'score': confidence * 10,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.0,
                'tp1_pct': 4.5
            }
            
        except Exception as e:
            return None

    async def test_range_break(self, symbol, candles_by_tf, timestamp):
        """Test range break strategy"""
        try:
            if '15' not in candles_by_tf:
                return None
                
            result = range_break_detector(symbol, candles_by_tf, "ranging")
            if not result or result.get('score', 0) < 6.0:
                return None
            
            direction = result.get('direction', 'Long')
            score = result.get('score', 0)
            confidence = result.get('confidence', 0.5)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Range break SL/TP
            if direction == "Long":
                sl_price = entry_price * 0.975
                tp1_price = entry_price * 1.055
            else:
                sl_price = entry_price * 1.025
                tp1_price = entry_price * 0.945
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.5,
                'tp1_pct': 5.5
            }
            
        except Exception as e:
            return None

    async def test_stealth_accumulation(self, symbol, candles_by_tf, timestamp):
        """Test stealth accumulation strategy"""
        try:
            if '5' not in candles_by_tf:
                return None
                
            # Test stealth accumulation
            stealth_result = detect_stealth_accumulation_advanced(candles_by_tf['5'])
            if not stealth_result.get('detected', False):
                return None
            
            strength = stealth_result.get('strength', 0)
            if strength < 0.6:
                return None
            
            # Calculate accumulation score
            accum_score = calculate_accumulation_score(candles_by_tf['5'])
            if accum_score < 0.6:
                return None
            
            # Stealth accumulation is typically bullish
            direction = 'Long'
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Conservative SL/TP for accumulation
            sl_price = entry_price * 0.985  # 1.5% SL
            tp1_price = entry_price * 1.035  # 3.5% TP
            
            return {
                'score': accum_score * 10,
                'direction': direction,
                'confidence': strength,
                'trade_type': 'Swing',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 1.5,
                'tp1_pct': 3.5
            }
            
        except Exception as e:
            return None

    async def test_pump_detector(self, symbol, candles_by_tf, timestamp):
        """Test early pump detection strategy"""
        try:
            if '1' not in candles_by_tf or '3' not in candles_by_tf:
                return None
                
            # Test for early pump signals
            pump_result = detect_early_pump(symbol, candles_by_tf)
            if not pump_result or pump_result.get('confidence', 0) < 0.7:
                return None
            
            # Also check for pump potential
            has_potential = has_pump_potential(symbol, candles_by_tf)
            if not has_potential:
                return None
            
            direction = pump_result.get('direction', 'Long')
            confidence = pump_result.get('confidence', 0)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Pump detection SL/TP (aggressive for quick moves)
            if direction == "Long":
                sl_price = entry_price * 0.97   # 3% SL
                tp1_price = entry_price * 1.08   # 8% TP
            else:
                sl_price = entry_price * 1.03
                tp1_price = entry_price * 0.92
            
            return {
                'score': confidence * 10,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Scalp',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 3.0,
                'tp1_pct': 8.0
            }
            
        except Exception as e:
            return None

    async def test_momentum_surge(self, symbol, candles_by_tf, timestamp):
        """Test momentum surge detection"""
        try:
            if '3' not in candles_by_tf or '15' not in candles_by_tf:
                return None
                
            # Detect strong momentum
            momentum_strength = detect_momentum_strength(symbol, candles_by_tf)
            if not momentum_strength or momentum_strength.get('score', 0) < 8.0:
                return None
            
            direction = momentum_strength.get('direction', 'Long')
            score = momentum_strength.get('score', 0)
            confidence = momentum_strength.get('confidence', 0.5)
            
            entry_price = self.get_price_at_timestamp(symbol, timestamp)
            if not entry_price:
                return None
            
            # Momentum SL/TP (wider TP for strong moves)
            if direction == "Long":
                sl_price = entry_price * 0.98
                tp1_price = entry_price * 1.065  # 6.5% TP
            else:
                sl_price = entry_price * 1.02
                tp1_price = entry_price * 0.935
            
            return {
                'score': score,
                'direction': direction,
                'confidence': confidence,
                'trade_type': 'Intraday',
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'sl_pct': 2.0,
                'tp1_pct': 6.5
            }
            
        except Exception as e:
            return None

    def generate_comprehensive_report(self, initial_balance):
        """Generate detailed performance report for all strategies"""
        
        if not self.all_trades:
            log("❌ No trades to analyze")
            return
        
        log("📊 Generating comprehensive performance report...")
        
        # Overall performance
        total_pnl = sum(trade['pnl'] for trade in self.all_trades)
        total_trades = len(self.all_trades)
        winning_trades = len([t for t in self.all_trades if t['pnl'] > 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Strategy-specific performance
        strategy_stats = {}
        for strategy_name in self.strategies.keys():
            strategy_trades = self.strategy_performance[strategy_name]
            
            if strategy_trades:
                strategy_pnl = sum(t['pnl'] for t in strategy_trades)
                strategy_wins = len([t for t in strategy_trades if t['pnl'] > 0])
                strategy_win_rate = strategy_wins / len(strategy_trades)
                avg_duration = sum(t['duration_minutes'] for t in strategy_trades) / len(strategy_trades)
                avg_pnl = strategy_pnl / len(strategy_trades)
                
                strategy_stats[strategy_name] = {
                    'total_trades': len(strategy_trades),
                    'total_pnl': strategy_pnl,
                    'win_rate': strategy_win_rate,
                    'avg_pnl_per_trade': avg_pnl,
                    'avg_duration_minutes': avg_duration,
                    'return_pct': (strategy_pnl / initial_balance) * 100
                }
            else:
                strategy_stats[strategy_name] = {
                    'total_trades': 0,
                    'total_pnl': 0,
                    'win_rate': 0,
                    'avg_pnl_per_trade': 0,
                    'avg_duration_minutes': 0,
                    'return_pct': 0
                }
        
        # Print summary
        print("\n" + "="*80)
        print("📈 COMPREHENSIVE STRATEGY BACKTEST RESULTS")
        print("="*80)
        
        print(f"\n💰 OVERALL PERFORMANCE:")
        print(f"   Initial Balance: ${initial_balance:,.2f}")
        print(f"   Final Balance: ${initial_balance + total_pnl:,.2f}")
        print(f"   Total PnL: ${total_pnl:+,.2f}")
        print(f"   Total Return: {(total_pnl / initial_balance) * 100:+.2f}%")
        print(f"   Total Trades: {total_trades}")
        print(f"   Win Rate: {win_rate:.1%}")
        print(f"   Avg PnL per Trade: ${total_pnl / total_trades:+.2f}")
        
        print(f"\n🎯 STRATEGY BREAKDOWN:")
        print("-" * 80)
        
        # Sort strategies by return percentage
        sorted_strategies = sorted(strategy_stats.items(), key=lambda x: x[1]['return_pct'], reverse=True)
        
        for i, (strategy, stats) in enumerate(sorted_strategies, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            strategy_description = self.strategies[strategy].get('description', strategy.replace('_', ' ').title())
            
            print(f"\n{emoji} {strategy_description}")
            print(f"   Return: {stats['return_pct']:+.2f}%")
            print(f"   PnL: ${stats['total_pnl']:+,.2f}")
            print(f"   Trades: {stats['total_trades']}")
            if stats['total_trades'] > 0:
                print(f"   Win Rate: {stats['win_rate']:.1%}")
                print(f"   Avg PnL/Trade: ${stats['avg_pnl_per_trade']:+.2f}")
                print(f"   Avg Duration: {stats['avg_duration_minutes']:.0f} min")
        
        # Save detailed report
        report_data = {
            'backtest_date': datetime.now().isoformat(),
            'initial_balance': initial_balance,
            'final_balance': initial_balance + total_pnl,
            'total_return_pct': (total_pnl / initial_balance) * 100,
            'total_pnl': total_pnl,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'strategy_performance': strategy_stats,
            'strategy_configurations': {name: config for name, config in self.strategies.items()},
            'all_trades': self.all_trades,
            'daily_pnl': dict(self.daily_pnl)
        }
        
        # Save JSON report
        with open('comprehensive_backtest_report.json', 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        # Save trades as CSV for analysis
        if self.all_trades:
            df = pd.DataFrame(self.all_trades)
            df.to_csv('backtest_trades.csv', index=False)
        
        print(f"\n📄 Detailed reports saved:")
        print(f"   📊 comprehensive_backtest_report.json - Full analysis")
        print(f"   📈 backtest_trades.csv - Individual trade details")
        print("\n🔎 Signal audit:")
        for name, m in self.sig_stats.items():
            print(f"  {name:24s} fired={m['fired']:4d}  below={m['below_threshold']:4d}  no_sig={m['no_signal']:4d}  missing_tf={m['missing_tf']:4d}  exc={m['exception']:3d}")

        if self.debug_signals:
            with open("suppressed_signals_sample.csv","w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["t","sym","strat","score"])
                w.writeheader(); w.writerows(self.debug_signals[:200])
            print("🧪 Saved sample suppressed signals → suppressed_signals_sample.csv")

        print("="*80)

# USAGE FUNCTIONS

async def run_quick_strategy_test():
    """Quick test of all strategies - 7 days"""
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
    
    backtester = ComprehensiveBacktester()
    await backtester.run_comprehensive_backtest(symbols, days=7, initial_balance=10000)

async def run_full_strategy_backtest():
    """Full strategy backtest - 30 days"""
    symbols = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
        'XRPUSDT', 'DOTUSDT', 'UNIUSDT', 'LINKUSDT', 'LTCUSDT',
        'AVAXUSDT', 'ATOMUSDT', 'NEARUSDT', 'FILUSDT', 'SANDUSDT',
        'MATICUSDT', 'ALGOUSDT', 'VETUSDT', 'FTMUSDT', 'ICPUSDT'
    ]
    
    backtester = ComprehensiveBacktester()
    await backtester.run_comprehensive_backtest(symbols, days=30, initial_balance=10000)

async def run_strategy_comparison():
    """Compare individual strategies head-to-head"""
    
    print("🥊 INDIVIDUAL STRATEGY COMPARISON")
    print("=" * 50)
    
    # Test each strategy individually
    strategies_to_test = {
        'core_only': ['core_strategy'],
        'enhanced_core_only': ['enhanced_core'],
        'mean_reversion_only': ['mean_reversion'],
        'breakout_only': ['breakout_sniper'],
        'pattern_matching_only': ['pattern_matching'],
        'pattern_discovery_only': ['pattern_discovery'],
        'range_break_only': ['range_break'],
        'stealth_accumulation_only': ['stealth_accumulation'],
        'pump_detector_only': ['pump_detector'],
        'momentum_surge_only': ['momentum_surge']
    }
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
    results = {}
    
    for test_name, enabled_strategies in strategies_to_test.items():
        print(f"\n🧪 Testing: {test_name.replace('_only', '').replace('_', ' ').title()}")
        
        backtester = ComprehensiveBacktester()
        
        # Disable all strategies except the one being tested
        for strategy in backtester.strategies:
            backtester.strategies[strategy]['enabled'] = strategy in enabled_strategies
        
        await backtester.run_comprehensive_backtest(symbols, days=10, initial_balance=10000)
        
        # Store results
        if backtester.all_trades:
            total_pnl = sum(t['pnl'] for t in backtester.all_trades)
            win_rate = len([t for t in backtester.all_trades if t['pnl'] > 0]) / len(backtester.all_trades)
            results[test_name] = {
                'total_pnl': total_pnl,
                'win_rate': win_rate,
                'total_trades': len(backtester.all_trades),
                'return_pct': (total_pnl / 10000) * 100
            }
        else:
            results[test_name] = {
                'total_pnl': 0,
                'win_rate': 0,
                'total_trades': 0,
                'return_pct': 0
            }
    
    # Print comparison
    print(f"\n🏆 INDIVIDUAL STRATEGY RESULTS")
    print(f"=" * 50)
    
    sorted_results = sorted(results.items(), key=lambda x: x[1]['return_pct'], reverse=True)
    
    for i, (strategy, stats) in enumerate(sorted_results, 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        strategy_name = strategy.replace('_only', '').replace('_', ' ').title()
        
        print(f"\n{emoji} {strategy_name}")
        print(f"   Return: {stats['return_pct']:+.2f}%")
        print(f"   Win Rate: {stats['win_rate']:.1%}")
        print(f"   Trades: {stats['total_trades']}")
        print(f"   PnL: ${stats['total_pnl']:+.2f}")

if __name__ == "__main__":
    print("🚀 COMPREHENSIVE STRATEGY BACKTESTER")
    print("=" * 60)
    print()
    print("Available Tests:")
    print("1. 🏃‍♂️ Quick Test (7 days, 5 symbols)")
    print("2. 📊 Full Test (30 days, 20 symbols)")
    print("3. 🥊 Strategy Comparison (individual performance)")
    print("4. 🎯 Custom Test")
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    if choice == "1":
        print("\n⚡ Running quick test...")
        asyncio.run(run_quick_strategy_test())
    elif choice == "2":
        print("\n📈 Running full backtest...")
        asyncio.run(run_full_strategy_backtest())
    elif choice == "3":
        print("\n🔍 Running strategy comparison...")
        asyncio.run(run_strategy_comparison())
    elif choice == "4":
        print("\n🛠️ Custom Test Configuration:")
        days = int(input("Number of days (1-90): ") or "14")
        balance = int(input("Initial balance ($): ") or "10000")
        
        print("\nSymbol options:")
        print("1. Top 5 (BTC, ETH, SOL, ADA, DOGE)")
        print("2. Top 10 (includes XRP, DOT, UNI, LINK, LTC)")
        print("3. Top 20 (full crypto selection)")
        
        symbol_choice = input("Symbol set (1-3): ").strip()
        
        if symbol_choice == "1":
            symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
        elif symbol_choice == "2":
            symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
                      'XRPUSDT', 'DOTUSDT', 'UNIUSDT', 'LINKUSDT', 'LTCUSDT']
        else:
            symbols = [
                'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT',
                'XRPUSDT', 'DOTUSDT', 'UNIUSDT', 'LINKUSDT', 'LTCUSDT',
                'AVAXUSDT', 'ATOMUSDT', 'NEARUSDT', 'FILUSDT', 'SANDUSDT',
                'MATICUSDT', 'ALGOUSDT', 'VETUSDT', 'FTMUSDT', 'ICPUSDT'
            ]
        
        print(f"\n🚀 Running custom backtest...")
        print(f"   📅 Duration: {days} days")
        print(f"   💰 Balance: ${balance:,}")
        print(f"   📊 Symbols: {len(symbols)} pairs")
        
        backtester = ComprehensiveBacktester()
        asyncio.run(backtester.run_comprehensive_backtest(symbols, days, balance))
    else:
        print("Invalid choice, running quick test...")
        asyncio.run(run_quick_strategy_test())
