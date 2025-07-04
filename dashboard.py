import pandas as pd
import streamlit as st
import os
from datetime import datetime
import json
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import time
import shutil

LOG_PATH = "/mnt/data/trade_logs/trade_setups.csv"

# Map of indicator short keys to readable names
INDICATOR_MAP = {
    "1": "RSI",
    "2": "MACD",
    "3": "EMA",
    "4": "Supertrend",
    "5": "Bollinger",
    "6": "Pattern",
    "7": "Volume",
    "8": "Whale",
    "9": "Divergence",
    "10": "Breakout"
}

TF_LABELS = {
    "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m", "60": "1h", "240": "4h"
}

# New: Strategy classification
STRATEGY_MAP = {
    "core_strategy": "Core Trend Strategy",
    "mean_reversion": "Mean Reversion",
    "breakout_sniper": "Breakout Sniper"
}

def load_data():
    if os.path.exists(LOG_PATH):
        df = pd.read_csv(LOG_PATH, engine="python", quotechar='"', skip_blank_lines=True, on_bad_lines='skip')
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
        df = df.sort_values(by="timestamp", ascending=False)

        # Calculate key metrics
        df["exit_price"] = df.apply(lambda row: row["tp2"] if row["result"] == "win" else (row["tp1"] if "tp1" in str(row["result"]) else row["sl"]), axis=1)
        df["move_pct"] = ((df["exit_price"] - df["entry_price"]) / df["entry_price"] * 100).round(2)
        df["move_pct"] = df.apply(lambda row: row["move_pct"] if row["direction"] == "Long" else -row["move_pct"], axis=1)
        
        # Handling numeric columns
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")
        df["score_delta"] = df["score"] - df["confidence"]
        
        # New: Identify strategy type
        df["strategy_type"] = df.apply(identify_strategy_type, axis=1)
        
        # Enhanced classification with more detailed categories
        df["signal_tag"] = df.apply(classify_signal, axis=1)
        
        # New: Calculate SL distance percentage
        df["sl_distance_pct"] = df.apply(
            lambda row: abs((row["sl"] - row["entry_price"]) / row["entry_price"] * 100) 
            if pd.notna(row["sl"]) and pd.notna(row["entry_price"]) else None, 
            axis=1
        )
        
        # New: Calculate risk-reward ratio
        df["risk_reward"] = df.apply(
            lambda row: abs((row["tp1"] - row["entry_price"]) / (row["entry_price"] - row["sl"])) 
            if pd.notna(row["sl"]) and pd.notna(row["tp1"]) and pd.notna(row["entry_price"]) 
              and abs(row["entry_price"] - row["sl"]) > 0 else None,
            axis=1
        )
        
        # New: Add trade duration column if possible from timestamp data
        if "exit_timestamp" in df.columns:
            df["duration"] = (pd.to_datetime(df["exit_timestamp"]) - df["timestamp"]).dt.total_seconds() / 60
        else:
            df["duration"] = None
            
        return df
    else:
        return pd.DataFrame()

def get_live_active_trades():
    """Get current active trades from JSON file"""
    try:
        if os.path.exists("monitor_active_trades.json"):
            with open("monitor_active_trades.json", 'r') as f:
                trades = json.load(f)
            return {k: v for k, v in trades.items() if not v.get("exited", False)}
        return {}
    except:
        return {}

def identify_strategy_type(row):
    """Identify which trading strategy was used based on available indicators"""
    try:
        if isinstance(row.get("tf_scores"), str) and "mean_reversion" in row["tf_scores"]:
            return "Mean Reversion"
        elif isinstance(row.get("tf_scores"), str) and "breakout_sniper" in row["tf_scores"]:
            return "Breakout Sniper"
        elif row.get("sl_strategy") == "ATR-Swing":
            return "Swing Trade"
        elif row.get("trade_type") == "Scalp":
            return "Scalp Trade"
        elif row.get("trade_type") == "Intraday":
            return "Intraday Trade"
        else:
            return "Core Strategy"
    except:
        return "Unknown"

def classify_signal(row):
    """Enhanced signal classification with more detailed categories"""
    try:
        # Define signal categories with specific criteria
        if row.get("whale_signal") == True:
            return "🐳 Whale Entry"
        elif row.get("volume_spike") == True and row.get("confidence", 0) >= 85:
            return "🔥 High-Volume Prime Setup"
        elif row.get("pattern_detected") and row.get("confidence", 0) >= 75:
            return "📊 Pattern-Confirmed Setup"
        elif row.get("confidence", 0) >= 85:
            return "🔥 High-Confidence Setup"
        elif row.get("score", 0) >= 8.0:
            return "✅ Strong Score"
        elif row.get("volume_spike") == False:
            return "💤 Low Volume"
        elif row.get("score", 0) < 6.5:
            return "⚠️ Weak Setup"
        return "📈 Standard Setup"
    except:
        return "🧪 Unknown"

def format_indicator_scores(raw):
    """Format indicator scores for display - FIXED to handle non-numeric values"""
    try:
        if isinstance(raw, str) and raw.strip():
            data = json.loads(raw)
        else:
            data = raw

        if isinstance(data, dict):
            def safe_format_value(value):
                """Safely format value for display"""
                try:
                    if isinstance(value, str):
                        # Try to parse as float
                        try:
                            return f"{float(value):.2f}"
                        except ValueError:
                            # If it's a non-numeric string, just return it
                            return value
                    elif isinstance(value, (int, float)):
                        return f"{float(value):.2f}"
                    else:
                        return str(value)
                except:
                    return str(value)
            
            # Only include indicators with meaningful values
            readable = []
            for k, v in data.items():
                try:
                    # Skip empty or zero values
                    if v is None or v == "" or v == 0:
                        continue
                    
                    formatted_value = safe_format_value(v)
                    indicator_name = INDICATOR_MAP.get(k, k)
                    readable.append(f"{indicator_name}: {formatted_value}")
                    
                except Exception as e:
                    print(f"Error formatting indicator {k}: {v}, error: {e}")
                    continue
                    
        elif isinstance(data, list):
            readable = [INDICATOR_MAP.get(str(item), str(item)) for item in data if item]
        else:
            readable = []

        return "\n".join(readable) if readable else "—"
        
    except Exception as e:
        print(f"Error in format_indicator_scores: {e}, raw data: {raw}")
        return "—"

def top_indicator(raw):
    """Extract top indicator from scores - FIXED to handle non-numeric values"""
    try:
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw

        if isinstance(data, dict):
            # FIXED: Handle non-numeric values properly
            def safe_float_parse(value):
                """Safely parse value to float, return 0 if not numeric"""
                try:
                    # Handle string values like 'range_break'
                    if isinstance(value, str):
                        # Try to parse as float first
                        try:
                            return float(value)
                        except ValueError:
                            # If it's a non-numeric string, return 1.0 as indicator presence
                            return 1.0 if value else 0.0
                    # Handle numeric values
                    elif isinstance(value, (int, float)):
                        return float(value)
                    else:
                        return 0.0
                except (ValueError, TypeError):
                    return 0.0
            
            # Sort indicators by their numeric value
            sorted_items = sorted(
                data.items(), 
                key=lambda x: safe_float_parse(x[1]), 
                reverse=True
            )
            
            if sorted_items:
                top_key, top_value = sorted_items[0]
                # Return the indicator name with its value
                return f"{INDICATOR_MAP.get(top_key, top_key)}: {safe_float_parse(top_value):.2f}"
            else:
                return "—"
        else:
            return "—"
            
    except Exception as e:
        # Log the error for debugging
        print(f"Error in top_indicator: {e}, raw data: {raw}")
        return "—"

def format_tf_scores(raw):
    """Format timeframe scores for display"""
    try:
        if isinstance(raw, str):
            scores = json.loads(raw)
            return ", ".join(f"{TF_LABELS.get(tf, tf)}: {val}" for tf, val in scores.items())
        return "—"
    except:
        return "—"

def display_trade_table(df, title):
    """Display trade table with improved column selection and formatting"""
    st.write(f"### 📋 {title}")
    
    # New: Allow user to customize visible columns
    all_columns = df.columns.tolist()
    default_columns = [
        "timestamp", "symbol", "direction", "entry_price", "exit_price", "move_pct",
        "score", "confidence", "strategy_type", "signal_tag",
        "result", "trade_type", "sl_distance_pct", "risk_reward", "top_indicator",
        "missed_upside", "pullback_after"
    ]
    
    # Only use columns that exist in the dataframe
    default_columns = [col for col in default_columns if col in all_columns]
    
    # Add a unique key based on the title parameter
    key_suffix = title.lower().replace(" ", "_")
    
    with st.expander(f"Customize Table Columns - {title}"):
        selected_columns = st.multiselect(
            "Select columns to display",
            options=all_columns,
            default=default_columns,
            key=f"cols_select_{key_suffix}"  # Add unique key here
        )
    
    if not selected_columns:  # Fallback if no columns selected
        selected_columns = default_columns
    
    df_display = df[selected_columns].copy()

    # Apply conditional formatting
    def highlight_result(val):
        if val == "win": return "background-color: #b7f7b0"
        elif val == "loss": return "background-color: #f8b8b8"
        elif val == "breakeven": return "background-color: #f5f5a0"
        elif val == "open": return "background-color: #cce5ff"
        elif val in ["tp1", "tp1-partial"]: return "background-color: #d4eaff"
        return ""

    if "result" in df_display.columns:
        styled_df = df_display.style.map(highlight_result, subset=["result"])
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.dataframe(df_display, use_container_width=True)

def display_result_breakdown(df):
    """Display trade result statistics with enhanced metrics"""
    st.write("### 📊 Trade Result Breakdown")

    # Basic result counters
    tp2_hits = len(df[(df.result == "win") & df.tp2.notna()])
    tp1_only = len(df[df.result.isin(["tp1", "tp1-partial", "breakeven"])])
    sl_hits = len(df[df.result == "loss"])
    open_trades = len(df[df.result == "open"])
    
    # Calculate win rate
    total_closed = tp2_hits + tp1_only + sl_hits
    win_rate = (tp2_hits + tp1_only) / total_closed * 100 if total_closed > 0 else 0
    
    # Calculate average metrics
    avg_win = df[df.result.isin(["win", "tp1", "tp1-partial", "breakeven"])]["move_pct"].mean() if not df.empty else 0
    avg_loss = df[df.result == "loss"]["move_pct"].mean() if not df.empty else 0
    
    # Enhanced metrics layout with more information
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("TP2 Wins", f"{tp2_hits} ({round(tp2_hits/total_closed*100, 1)}%)" if total_closed > 0 else "0")
    col2.metric("TP1/BE", f"{tp1_only} ({round(tp1_only/total_closed*100, 1)}%)" if total_closed > 0 else "0")
    col3.metric("SL Hits", f"{sl_hits} ({round(sl_hits/total_closed*100, 1)}%)" if total_closed > 0 else "0")
    col4.metric("Open Trades", open_trades)
    
    # Second row with performance metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Win Rate", f"{round(win_rate, 1)}%")
    col2.metric("Avg Win %", f"{round(avg_win, 2)}%" if not pd.isna(avg_win) else "N/A")
    col3.metric("Avg Loss %", f"{round(avg_loss, 2)}%" if not pd.isna(avg_loss) else "N/A")
    col4.metric("Profit Factor", f"{round(abs(avg_win * (tp2_hits + tp1_only) / (avg_loss * sl_hits)), 2)}" 
                if sl_hits > 0 and not pd.isna(avg_win) and not pd.isna(avg_loss) else "N/A")

def display_performance_charts(df):
    """New function to display performance visualization charts"""
    st.write("### 📈 Performance Visualization")
    
    if df.empty or len(df[df.result != "open"]) < 3:
        st.warning("Not enough completed trades to generate meaningful visualizations.")
        return
    
    # Only use completed trades
    completed_df = df[df.result != "open"].copy()
    
    # Create tabs for different charts
    tab1, tab2, tab3, tab4 = st.tabs(["Win Rate by Strategy", "Return by Strategy", "SL Analysis", "Missed Opportunities"])
    
    with tab1:
        # Win rate by strategy type
        strategy_results = completed_df.groupby(['strategy_type', 'result']).size().unstack(fill_value=0)
        
        if not strategy_results.empty and len(strategy_results.columns) > 0:
            # Calculate total trades and win rate
            strategy_results['total'] = strategy_results.sum(axis=1)
            win_cols = [col for col in strategy_results.columns if col in ['win', 'tp1', 'breakeven', 'tp1-partial']]
            loss_cols = [col for col in strategy_results.columns if col == 'loss']
            
            # Sum wins and calculate win rate
            strategy_results['wins'] = strategy_results[win_cols].sum(axis=1) if win_cols else 0
            strategy_results['win_rate'] = (strategy_results['wins'] / strategy_results['total'] * 100).round(1)
            
            fig = px.bar(
                strategy_results.reset_index(), 
                x='strategy_type', 
                y='win_rate',
                color='strategy_type',
                labels={'strategy_type': 'Strategy', 'win_rate': 'Win Rate (%)'},
                title='Win Rate by Strategy Type'
            )
            
            # Add trade count as text
            for i, row in strategy_results.reset_index().iterrows():
                fig.add_annotation(
                    x=row['strategy_type'],
                    y=row['win_rate'],
                    text=f"{int(row['total'])} trades",
                    showarrow=False,
                    yshift=10
                )
                
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough data to create strategy win rate chart")
    
    with tab2:
        # Average return by strategy
        if 'move_pct' in completed_df.columns and 'strategy_type' in completed_df.columns:
            avg_returns = completed_df.groupby('strategy_type')['move_pct'].agg(['mean', 'count']).reset_index()
            avg_returns['mean'] = avg_returns['mean'].round(2)
            
            fig = px.bar(
                avg_returns, 
                x='strategy_type', 
                y='mean',
                color='strategy_type',
                labels={'strategy_type': 'Strategy', 'mean': 'Average Return (%)'},
                title='Average Return by Strategy Type'
            )
            
            # Add trade count as text
            for i, row in avg_returns.iterrows():
                fig.add_annotation(
                    x=row['strategy_type'],
                    y=row['mean'],
                    text=f"{int(row['count'])} trades",
                    showarrow=False,
                    yshift=10
                )
                
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Missing data for return by strategy chart")
    
    with tab3:
        # SL hit analysis - what percent of trades hit SL and what was common among them
        sl_hits = completed_df[completed_df.result == 'loss'].copy()
        
        if not sl_hits.empty and len(sl_hits) >= 3:
            # Top reasons for SL hits chart
            
            # Create a function to extract top negative indicators
            def extract_negative_indicators(row):
                try:
                    if isinstance(row, str):
                        data = json.loads(row)
                        neg_indicators = [INDICATOR_MAP.get(k, k) for k, v in data.items() 
                                          if str(v).replace('-','',1).replace('.','',1).isdigit() and float(v) < 0]
                        return neg_indicators
                    return []
                except:
                    return []
            
            # Extract negative indicators
            sl_hits['neg_indicators'] = sl_hits['indicator_scores'].apply(extract_negative_indicators)
            
            # Flatten the list of lists to count occurrences
            all_neg_indicators = [item for sublist in sl_hits['neg_indicators'] for item in sublist]
            
            if all_neg_indicators:
                from collections import Counter
                indicator_counts = Counter(all_neg_indicators).most_common(5)
                
                fig = px.bar(
                    x=[item[0] for item in indicator_counts],
                    y=[item[1] for item in indicator_counts],
                    labels={'x': 'Indicator', 'y': 'Count'},
                    title='Top 5 Negative Indicators in SL Hits'
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # SL distance analysis
            if 'sl_distance_pct' in sl_hits.columns:
                fig = px.histogram(
                    sl_hits, 
                    x='sl_distance_pct',
                    nbins=20,
                    title='SL Distance Distribution in Failed Trades'
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough SL hits to analyze patterns")
    
    with tab4:
        # Missed opportunities analysis
        if 'missed_upside' in completed_df.columns:
            missed_upside = completed_df[completed_df.result.isin(['loss', 'tp1', 'tp1-partial', 'breakeven'])].copy()
            missed_upside = missed_upside[missed_upside['missed_upside'].notna() & (missed_upside['missed_upside'] > 0)]
            
            if not missed_upside.empty and len(missed_upside) >= 3:
                # Sort by missed upside and take top instances
                top_missed = missed_upside.sort_values('missed_upside', ascending=False).head(10)
                
                fig = px.bar(
                    top_missed,
                    x='symbol',
                    y='missed_upside',
                    color='result',
                    title='Top 10 Trades with Highest Missed Upside (%)'
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Also show average missed upside by result type
                avg_missed = missed_upside.groupby('result')['missed_upside'].mean().reset_index()
                
                fig = px.bar(
                    avg_missed,
                    x='result',
                    y='missed_upside',
                    color='result',
                    title='Average Missed Upside by Result Type (%)'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Not enough data on missed upside opportunities")
        else:
            st.info("Missed upside data not available")

def display_indicator_details(df):
    """Display indicator scores chart - FIXED to handle non-numeric values properly"""
    if "indicator_scores" in latest and pd.notna(latest["indicator_scores"]):
        try:
            # Parse the indicator scores
            if isinstance(latest["indicator_scores"], str):
                try:
                    indicator_data = json.loads(latest["indicator_scores"])
                except json.JSONDecodeError:
                    st.warning("Could not parse indicator scores")
                    return
            else:
                indicator_data = latest["indicator_scores"]
            
            if isinstance(indicator_data, dict) and indicator_data:
                # Convert to readable format and filter numeric values
                sorted_indicators = {}
                
                # Known indicator mappings for non-numeric values
                indicator_defaults = {
                    'range_break': 1.0,
                    'breakout': 1.0,
                    'pump_signal': 1.0,
                    'pre_breakout': 0.8,
                    'volume_spike': 0.7,
                    'momentum': 0.6,
                    'trend_aligned': 1.0,
                    'stealth_accumulation': 0.9,
                    'range_direction_aligned': 1.0,
                    'active': 1.0,
                    'detected': 1.0,
                    'confirmed': 1.0
                }
                
                for key, value in indicator_data.items():
                    try:
                        # Handle different value types safely
                        if isinstance(value, (int, float)):
                            # Already numeric
                            numeric_value = float(value)
                        elif isinstance(value, str):
                            # String value - try conversion
                            value_clean = value.strip().lower()
                            
                            if not value_clean:
                                # Empty string
                                numeric_value = 0.0
                            else:
                                try:
                                    # Try direct float conversion first
                                    numeric_value = float(value)
                                except ValueError:
                                    # Handle named indicators
                                    numeric_value = indicator_defaults.get(value_clean, 1.0)
                        elif isinstance(value, bool):
                            # Boolean values
                            numeric_value = 1.0 if value else 0.0
                        else:
                            # Unknown type - skip or use default
                            continue
                        
                        # Only include positive, valid values
                        if (numeric_value > 0 and 
                            not (isinstance(numeric_value, float) and 
                                 (numeric_value != numeric_value or  # NaN check
                                  numeric_value == float('inf') or
                                  numeric_value == float('-inf')))):
                            
                            # Clean up the key name for display
                            display_key = key.replace('_', ' ').title()
                            sorted_indicators[display_key] = round(numeric_value, 3)
                            
                    except Exception as e:
                        # Log the specific error for debugging
                        st.warning(f"Skipping indicator '{key}' with value '{value}': {str(e)}")
                        continue
                
                # Display the chart if we have valid indicators
                if sorted_indicators:
                    # Sort by value for better visualization
                    sorted_indicators = dict(sorted(sorted_indicators.items(), 
                                                  key=lambda x: x[1], reverse=True))
                    
                    # Create DataFrame for plotting
                    indicator_df = pd.DataFrame(
                        list(sorted_indicators.items()), 
                        columns=['Indicator', 'Score']
                    )
                    
                    # Display as bar chart
                    st.subheader("📊 Indicator Scores")
                    fig = px.bar(
                        indicator_df, 
                        x='Score', 
                        y='Indicator',
                        orientation='h',
                        title="Current Signal Strength by Indicator"
                    )
                    fig.update_layout(height=max(300, len(sorted_indicators) * 30))
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Also show as metrics
                    st.subheader("📈 Top Indicators")
                    cols = st.columns(min(4, len(sorted_indicators)))
                    for i, (indicator, score) in enumerate(list(sorted_indicators.items())[:4]):
                        with cols[i % len(cols)]:
                            st.metric(indicator, f"{score:.2f}")
                else:
                    st.info("No valid indicator scores to display")
            else:
                st.info("No indicator data available")
                
        except Exception as e:
            st.error(f"Error displaying indicators: {str(e)}")
            # Show the raw data for debugging if needed
            if st.checkbox("Show raw indicator data for debugging"):
                st.json(latest.get("indicator_scores", {}))
    else:
        st.info("Indicator scores not available for this signal")

def display_trade_drilldown(df):
    """Enhanced trade drilldown analysis with more metrics and insights"""
    st.write("### 🧬 Trade Deep Analysis")
    
    if df.empty:
        st.warning("No trade data available for analysis.")
        return
        
    df = df.sort_values("timestamp", ascending=False)
    
    # Group by symbol for better organization
    symbols = df["symbol"].unique()
    selected_symbol = st.selectbox("Select a symbol", symbols, key="drilldown_symbol_select")
    
    # Filter trades for the selected symbol
    symbol_trades = df[df.symbol == selected_symbol].copy()
    
    # Allow selection of specific trade by timestamp
    trade_options = symbol_trades["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist()
    
    if not trade_options:
        st.warning(f"No trades found for {selected_symbol}")
        return
        
    selected_timestamp = st.selectbox("Select trade timestamp", trade_options, key="drilldown_timestamp_select")
    row = symbol_trades[symbol_trades["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S") == selected_timestamp].iloc[0]

    # Create nice layout with multiple columns and sections
    st.markdown(f"#### 🧾 Trade Analysis: {row['symbol']} — {row['direction']} ({row['result']})")
    
    # Main trade metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("##### 📉 Entry/Exit")
        st.markdown(f"**Entry**: {row['entry_price']}")
        st.markdown(f"**Exit**: {row['exit_price'] if 'exit_price' in row else '—'}")
        st.markdown(f"**Move**: {row['move_pct']}%")
        
    with col2:
        st.markdown("##### 🛡️ Risk Management")
        st.markdown(f"**SL**: {row['sl']}")
        st.markdown(f"**TP1**: {row['tp1']}")
        st.markdown(f"**TP2**: {row['tp2'] if 'tp2' in row and pd.notna(row['tp2']) else '—'}")
        
    with col3:
        st.markdown("##### 📊 Setup Quality")
        st.markdown(f"**Score**: {row['score']}")
        st.markdown(f"**Confidence**: {row.get('confidence', '—')}%")
        st.markdown(f"**Type**: {row['trade_type']}")
        
    # Strategy and indicators
    st.markdown("##### 🧠 Strategy Info")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Strategy**: {row.get('strategy_type', 'Core Strategy')}")
        st.markdown(f"**Signal Tag**: {row.get('signal_tag', '—')}")
        st.markdown(f"**Top Indicator**: {row.get('top_indicator', '—')}")
        
    with col2:
        st.markdown(f"**Pattern**: {row.get('pattern_detected', '—')}")
        st.markdown(f"**Whale Signal**: {'Yes' if row.get('whale_signal') else 'No'}")
        st.markdown(f"**Volume Spike**: {'Yes' if row.get('volume_spike') else 'No'}")
        
    # Post-trade analysis
    st.markdown("##### 📈 Post-Trade Analysis")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Missed Upside**: {row.get('missed_upside', '—')}%")
        st.markdown(f"**Pullback After Exit**: {row.get('pullback_after', '—')}%")
        
    with col2:
        # Calculate SL distance and R:R ratio if not already in DataFrame
        sl_distance = round(abs((row['sl'] - row['entry_price']) / row['entry_price'] * 100), 2) if pd.notna(row['sl']) else "—"
        
        if pd.notna(row['sl']) and pd.notna(row['tp1']):
            risk = abs(row['entry_price'] - row['sl'])
            reward = abs(row['tp1'] - row['entry_price'])
            rr_ratio = round(reward / risk, 2) if risk > 0 else "—"
        else:
            rr_ratio = "—"
            
        st.markdown(f"**SL Distance**: {sl_distance}%")
        st.markdown(f"**Risk/Reward**: {rr_ratio}")
        
    # Display timeframe scores
    if pd.notna(row.get("tf_scores")):
        st.markdown("##### 📊 Timeframe Scores")
        st.markdown(format_tf_scores(row["tf_scores"]))
        
        # Try to visualize TF scores
        try:
            tf_data = json.loads(row["tf_scores"])
            if isinstance(tf_data, dict) and tf_data:
                # Prepare data in a format for visualization
                tf_values = []
                tf_labels = []
                
                for tf, score in tf_data.items():
                    if str(score).replace('-','',1).replace('.','',1).isdigit():
                        tf_labels.append(TF_LABELS.get(tf, tf))
                        tf_values.append(float(score))
                
                if tf_values and tf_labels:
                    # Create a bar chart
                    fig = px.bar(
                        x=tf_labels,
                        y=tf_values,
                        labels={'x': 'Timeframe', 'y': 'Score'},
                        title='Timeframe Scores'
                    )
                    
                    # Color bars based on positive/negative
                    fig.update_traces(marker_color=[
                        'green' if v > 0 else 'red' for v in tf_values
                    ])
                    
                    st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            pass  # Silently handle visualization errors
    
    # Display detailed indicator scores with visualization
    if pd.notna(row["indicator_scores"]):
        st.markdown("##### 📊 Indicator Scores")
        
        try:
            scores = json.loads(row["indicator_scores"])
            readable = {INDICATOR_MAP.get(k, k): v for k, v in scores.items() if str(v).replace('-','',1).replace('.','',1).isdigit()}
            
            if readable:
                # Sort by absolute value
                sorted_indicators = dict(sorted(readable.items(), 
                                               key=lambda item: abs(float(item[1])), 
                                               reverse=True))
                
                # Create horizontal bar chart
                fig = px.bar(
                    x=list(sorted_indicators.values()),
                    y=list(sorted_indicators.keys()),
                    orientation='h',
                    labels={'x': 'Score', 'y': 'Indicator'},
                    title='Indicator Scores'
                )
                
                # Color bars based on positive/negative
                fig.update_traces(marker_color=[
                    'green' if float(v) > 0 else 'red' for v in sorted_indicators.values()
                ])
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.markdown("No numeric indicator scores available")
        except Exception as e:
            st.error(f"Error analyzing indicator scores: {e}")
            
    # Display used indicators
    if pd.notna(row["used_indicators"]):
        st.markdown("##### ✅ Used Indicators")
        try:
            indicators = json.loads(row["used_indicators"])
            st.markdown(", ".join([INDICATOR_MAP.get(i, i) for i in indicators]))
        except Exception as e:
            st.error(f"Error parsing used indicators: {e}")
    
    # Add recommendation for improvement based on trade outcome
    st.markdown("##### 🧩 Analysis & Recommendations")
    
    if row['result'] == 'loss':
        st.markdown("**Trade Lost - Potential Improvements:**")
        
        # Check if SL was too tight
        if pd.notna(row.get('sl_distance_pct')) and row.get('sl_distance_pct', 0) < 1.0:
            st.markdown("- ⚠️ Stop loss may have been too tight (< 1%). Consider wider stops for this market regime.")
            
        # Check if there were negative indicators
        try:
            if pd.notna(row["indicator_scores"]):
                scores = json.loads(row["indicator_scores"])
                neg_indicators = [(INDICATOR_MAP.get(k, k), v) for k, v in scores.items() 
                                 if str(v).replace('-','',1).replace('.','',1).isdigit() and float(v) < 0]
                if neg_indicators:
                    st.markdown("- 📉 Conflicting indicators detected:")
                    for ind, val in neg_indicators:
                        st.markdown(f"  * {ind}: {val}")
        except:
            pass
            
        # Check if market regime was unfavorable
        try:
            if "tf_scores" in row and pd.notna(row["tf_scores"]):
                tf_data = json.loads(row["tf_scores"])
                if "regime" in tf_data and tf_data["regime"] == "volatile":
                    st.markdown("- 🌪️ Trade was taken during volatile market conditions. Consider reducing position size or avoiding trades in this regime.")
        except:
            pass
            
    elif row['result'] in ['tp1', 'tp1-partial', 'breakeven']:
        st.markdown("**Partial Win/Breakeven - Potential Improvements:**")
        
        # Check for missed upside
        if pd.notna(row.get('missed_upside')) and row.get('missed_upside', 0) > 5.0:
            st.markdown(f"- 📈 Significant missed upside ({row.get('missed_upside')}%) after exit. Consider:")
            st.markdown("  * Using partial profit-taking (half at TP1, let remainder run with trailing stop)")
            st.markdown("  * Analyzing market momentum at TP1 to decide whether to exit fully")
            
        # Check if risk/reward was appropriate
        if pd.notna(row.get('risk_reward')) and row.get('risk_reward', 0) < 1.5:
            st.markdown("- ⚖️ Risk-to-reward ratio may have been too low. Aim for at least 1.5:1 for better long-term results.")
            
    elif row['result'] == 'win':
        st.markdown("**Winning Trade - What Worked Well:**")
        
        # Identify positive factors
        try:
            if pd.notna(row["indicator_scores"]):
                scores = json.loads(row["indicator_scores"])
                pos_indicators = [(INDICATOR_MAP.get(k, k), v) for k, v in scores.items() 
                                 if str(v).replace('-','',1).replace('.','',1).isdigit() and float(v) > 0]
                pos_indicators.sort(key=lambda x: float(x[1]), reverse=True)
                if pos_indicators:
                    st.markdown("- ✅ Strong confirmation from indicators:")
                    for ind, val in pos_indicators[:3]:  # Top 3 positive indicators
                        st.markdown(f"  * {ind}: {val}")
        except:
            pass
            
        # Comment on risk management
        if pd.notna(row.get('risk_reward')) and row.get('risk_reward', 0) >= 2.0:
            st.markdown("- ⚖️ Excellent risk-to-reward setup of {:.1f}:1".format(row.get('risk_reward')))
        
        # Comment on pullback
        if pd.notna(row.get('pullback_after')) and row.get('pullback_after', 0) > 3.0:
            st.markdown(f"- 🎯 Excellent timing on exit - market pulled back {row.get('pullback_after')}% afterward")

def filter_data(df):
    """Enhanced filter functionality with more options"""
    symbols = df.symbol.unique().tolist()
    trade_types = df.trade_type.unique().tolist() if 'trade_type' in df.columns else []
    directions = df.direction.unique().tolist() if 'direction' in df.columns else []
    results = df.result.unique().tolist() if 'result' in df.columns else []
    
    # Get strategy types if available
    strategy_types = df.strategy_type.unique().tolist() if 'strategy_type' in df.columns else []
    
    # Get signal tags if available
    signal_tags = df.signal_tag.unique().tolist() if 'signal_tag' in df.columns else []

    with st.sidebar:
        # Add options to clear/reset data
        st.write("## 🔄 Data Management")
        with st.expander("Reset Data Options"):
            reset_option = st.radio(
                "Reset Option",
                ["Keep all data", "Keep recent trades only", "Start fresh"],
                key="reset_option"
            )
            
            if reset_option == "Keep recent trades only":
                reset_days = st.number_input(
                    "Keep trades from the last N days:",
                    min_value=1,
                    value=30,
                    key="reset_days"
                )
                
                if st.button("Confirm Reset (Keep Recent)", key="confirm_reset_recent"):
                    try:
                        # Load the data
                        full_df = pd.read_csv(LOG_PATH)
                        full_df["timestamp"] = pd.to_datetime(full_df["timestamp"])
                        
                        # Filter to keep only recent trades
                        cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=reset_days)
                        df_recent = full_df[full_df["timestamp"] >= cutoff_date]
                        
                        # Save the filtered data back to the CSV
                        df_recent.to_csv(LOG_PATH, index=False)
                        st.success(f"Reset complete! Kept only trades from the last {reset_days} days.")
                        time.sleep(2)  # Give user time to see the message
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Error resetting data: {e}")
                        
            elif reset_option == "Start fresh":
                st.warning("⚠️ This will delete ALL trade data. This cannot be undone!")
                
                confirm_text = st.text_input(
                    "Type 'CONFIRM' to proceed with complete reset:",
                    key="confirm_text"
                )
                
                if st.button("Start Fresh (Delete All Data)", key="confirm_fresh_start"):
                    if confirm_text == "CONFIRM":
                        try:
                            # Create a backup just in case
                            import shutil
                            from datetime import datetime
                            
                            # Create backup
                            backup_path = f"{LOG_PATH}.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            if os.path.exists(LOG_PATH):
                                shutil.copy2(LOG_PATH, backup_path)
                            
                            # Get header from existing file or create default header
                            if os.path.exists(LOG_PATH):
                                with open(LOG_PATH, 'r') as f:
                                    header = f.readline().strip()
                            else:
                                header = "timestamp,symbol,direction,entry_price,sl,tp1,tp2,result,score,trade_type,confidence,tf_scores,indicator_scores,used_indicators,pattern_detected,whale_signal,volume_spike,sl_strategy,missed_upside,pullback_after"
                            
                            # Create new file with just the header
                            with open(LOG_PATH, 'w') as f:
                                f.write(header + '\n')
                                
                            st.success(f"Successfully reset all trade data! A backup was saved to {backup_path}")
                            time.sleep(2)  # Give user time to see the message
                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Error resetting data: {e}")
                    else:
                        st.error("Confirmation text doesn't match 'CONFIRM'. Reset aborted.")
        
        # Add option to download current log as backup
        if os.path.exists(LOG_PATH):
            try:
                with open(LOG_PATH, 'r') as f:
                    file_contents = f.read()
                    
                st.download_button(
                    label="Download Current Log Backup",
                    data=file_contents,
                    file_name=f"trade_log_backup_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="download_backup"
                )
            except Exception as e:
                st.error(f"Error creating backup: {e}")
        st.write("## 🔍 Filters")
        
        # Date range filter
        if 'timestamp' in df.columns:
            min_date = df['timestamp'].min().date()
            max_date = df['timestamp'].max().date()
            date_range = st.date_input(
                "Date range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                key="date_filter"
            )
            
            # Handle single date selection
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range
            else:
                start_date = end_date = date_range
        
        # Symbol filter with search
        symbol_search = st.text_input("Search symbols", key="symbol_search")
        filtered_symbols = [s for s in symbols if symbol_search.lower() in s.lower()] if symbol_search else symbols
        selected_symbols = st.multiselect("Symbols", filtered_symbols, default=filtered_symbols, key="symbol_select")
        
        # Other filters
        selected_types = st.multiselect("Trade Types", trade_types, default=trade_types, key="type_select")
        selected_directions = st.multiselect("Direction", directions, default=directions, key="direction_select")
        selected_results = st.multiselect("Results", results, default=results, key="result_select")
        
        # Strategy type filter if available
        if strategy_types:
            selected_strategies = st.multiselect("Strategy Types", strategy_types, default=strategy_types, key="strategy_select")
        else:
            selected_strategies = strategy_types
            
        # Signal tag filter if available
        if signal_tags:
            selected_tags = st.multiselect("Signal Tags", signal_tags, default=signal_tags, key="tag_select")
        else:
            selected_tags = signal_tags
            
        # Additional filters
        hide_open = st.checkbox("Hide Open Trades", value=False, key="hide_open")
        
        # Score range filter
        if 'score' in df.columns and not df['score'].empty:
            min_score = float(df['score'].min()) if not pd.isna(df['score'].min()) else 0
            max_score = float(df['score'].max()) if not pd.isna(df['score'].max()) else 10
            
            # Fix for min/max being the same
            if min_score == max_score:
                min_score = max(0, min_score - 1)  # Ensure it doesn't go below 0
                max_score = max_score + 1
                
            score_range = st.slider("Score Range", min_score, max_score, (min_score, max_score), key="score_range")
        else:
            score_range = (0, 10)
            
        # PnL range filter for completed trades
        if 'move_pct' in df.columns:
            completed_df = df[df.result != "open"]
            if not completed_df.empty:
                min_pnl = float(completed_df['move_pct'].min()) if not completed_df['move_pct'].empty else -100
                max_pnl = float(completed_df['move_pct'].max()) if not completed_df['move_pct'].empty else 100
                
                # Fix for min/max being the same
                if min_pnl == max_pnl:
                    min_pnl = min_pnl - 1
                    max_pnl = max_pnl + 1
                    
                pnl_range = st.slider("PnL Range (%)", min_pnl, max_pnl, (min_pnl, max_pnl), key="pnl_range")
            else:
                pnl_range = (-100, 100)
        else:
            pnl_range = (-100, 100)

    # Build up the filter conditions
    df_filtered = df.copy()
    
    # Apply date filter if available
    if 'timestamp' in df.columns:
        df_filtered = df_filtered[
            (df_filtered.timestamp.dt.date >= start_date) & 
            (df_filtered.timestamp.dt.date <= end_date)
        ]
    
    # Apply other filters    
    if selected_symbols:
        df_filtered = df_filtered[df_filtered.symbol.isin(selected_symbols)]
        
    if selected_types and 'trade_type' in df.columns:
        df_filtered = df_filtered[df_filtered.trade_type.isin(selected_types)]
        
    if selected_directions and 'direction' in df.columns:
        df_filtered = df_filtered[df_filtered.direction.isin(selected_directions)]
        
    if selected_results and 'result' in df.columns:
        df_filtered = df_filtered[df_filtered.result.isin(selected_results)]
        
    if selected_strategies and 'strategy_type' in df.columns:
        df_filtered = df_filtered[df_filtered.strategy_type.isin(selected_strategies)]
        
    if selected_tags and 'signal_tag' in df.columns:
        df_filtered = df_filtered[df_filtered.signal_tag.isin(selected_tags)]

    if hide_open and 'result' in df.columns:
        df_filtered = df_filtered[df_filtered.result != "open"]
        
    # Apply score filter
    if 'score' in df.columns:
        df_filtered = df_filtered[
            (df_filtered.score >= score_range[0]) | 
            (df_filtered.score.isna())
        ]
        df_filtered = df_filtered[
            (df_filtered.score <= score_range[1]) |
            (df_filtered.score.isna())
        ]
        
    # Apply PnL filter for completed trades
    if 'move_pct' in df.columns:
        df_filtered = df_filtered[
            (df_filtered.move_pct >= pnl_range[0]) | 
            (df_filtered.result == "open") |
            (df_filtered.move_pct.isna())
        ]
        df_filtered = df_filtered[
            (df_filtered.move_pct <= pnl_range[1]) | 
            (df_filtered.result == "open") |
            (df_filtered.move_pct.isna())
        ]
        
    # Display the filtered dataframe
    if df_filtered.empty:
        st.warning("No data available after applying filters.")
        return df_filtered

    # Process additional columns for display
    if "indicator_scores" in df_filtered.columns:
        df_filtered.loc[:, "indicators"] = df_filtered["indicator_scores"].apply(format_indicator_scores)
        df_filtered.loc[:, "top_indicator"] = df_filtered["indicator_scores"].apply(top_indicator)

    if "tf_scores" in df_filtered.columns:
        df_filtered.loc[:, "tf_scores_display"] = df_filtered["tf_scores"].apply(format_tf_scores)

    return df_filtered

def display_summary_stats(df):
    """Enhanced summary statistics with more metrics"""
    st.write("## 📊 Summary Statistics")
    
    # Create columns for better layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("### 📈 Overall Performance")
        
        total = len(df)
        completed = len(df[df.result != "open"])
        wins = len(df[df.result == "win"])
        losses = len(df[df.result == "loss"])
        breakeven = len(df[df.result.isin(["breakeven", "tp1", "tp1-partial"])])
        open_trades = len(df[df.result == "open"])

        # Calculate performance metrics
        win_rate = (wins + breakeven) / (wins + losses + breakeven) * 100 if (wins + losses + breakeven) else 0
        avg_score = df.score.mean() if total and 'score' in df.columns else 0
        avg_conf = df.confidence.mean() if total and 'confidence' in df.columns else 0
        
        # Create metrics in two rows
        metric1, metric2, metric3 = st.columns(3)
        metric1.metric("Total Trades", total)
        metric2.metric("Completed", completed)
        metric3.metric("Open", open_trades)
        
        metric1, metric2, metric3 = st.columns(3)
        metric1.metric("Win Rate", f"{win_rate:.1f}%")
        metric2.metric("Avg Score", f"{avg_score:.2f}")
        metric3.metric("Avg Confidence", f"{avg_conf:.2f}%")

        live_active = get_live_active_trades()
        st.write("### 🔴 Live Active Trades")
        st.metric("Currently Active (Live)", len(live_active))
        st.metric("CSV Open Trades", len(df[df.result == "open"]))
    
        if len(live_active) != len(df[df.result == "open"]):
            st.warning(f"⚠️ Mismatch detected! Live: {len(live_active)}, CSV: {len(df[df.result == 'open'])}")
        
        # Calculate PnL metrics if available
        if 'move_pct' in df.columns:
            completed_df = df[df.result != "open"]
            if not completed_df.empty:
                avg_win = completed_df[completed_df.move_pct > 0]['move_pct'].mean() if len(completed_df[completed_df.move_pct > 0]) > 0 else 0
                avg_loss = abs(completed_df[completed_df.move_pct < 0]['move_pct'].mean()) if len(completed_df[completed_df.move_pct < 0]) > 0 else 0
                
                metric1, metric2, metric3 = st.columns(3)
                metric1.metric("Avg Win", f"{avg_win:.2f}%")
                metric2.metric("Avg Loss", f"{avg_loss:.2f}%")
                
                # Calculate profit factor
                if avg_loss > 0:
                    profit_factor = avg_win / avg_loss
                    metric3.metric("Profit Factor", f"{profit_factor:.2f}")
    
    with col2:
        # Calculate statistics by direction
        if 'direction' in df.columns and not df.empty:
            st.write("### 🔀 Performance by Direction")
            
            direction_stats = df[df.result != "open"].groupby('direction')['result'].apply(
                lambda x: (x == 'win').sum() / len(x) * 100 if len(x) > 0 else 0
            ).reset_index()
            direction_stats.columns = ['Direction', 'Win Rate (%)']
            
            # Add count column
            direction_counts = df[df.result != "open"].groupby('direction').size().reset_index()
            direction_counts.columns = ['Direction', 'Count']
            
            # Merge stats
            direction_stats = direction_stats.merge(direction_counts, on='Direction')
            
            # Calculate average PnL by direction
            if 'move_pct' in df.columns:
                direction_pnl = df[df.result != "open"].groupby('direction')['move_pct'].mean().reset_index()
                direction_pnl.columns = ['Direction', 'Avg PnL (%)']
                direction_stats = direction_stats.merge(direction_pnl, on='Direction')
            
            # Display as table
            st.dataframe(direction_stats)
            
            # Create a bar chart to compare win rates
            fig = px.bar(
                direction_stats, 
                x='Direction', 
                y='Win Rate (%)',
                color='Direction',
                text='Count',
                title='Win Rate by Direction'
            )
            st.plotly_chart(fig, use_container_width=True)

def export_data(df):
    """New function to export filtered data"""
    st.write("## 📥 Export Data")
    
    if df.empty:
        st.warning("No data available to export.")
        return
    
    # Export options
    export_format = st.selectbox("Export format", ["CSV", "Excel", "JSON"], key="export_format_select")
    
    # Generate export data
    if export_format == "CSV":
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name="trade_analysis.csv",
            mime="text/csv"
        )
    elif export_format == "Excel":
        # For Excel, we need to use BytesIO
        import io
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Trades', index=False)
        
        st.download_button(
            label="Download Excel",
            data=buffer.getvalue(),
            file_name="trade_analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    elif export_format == "JSON":
        # Convert DataFrame to JSON
        json_data = df.to_json(orient="records", date_format="iso")
        st.download_button(
            label="Download JSON",
            data=json_data,
            file_name="trade_analysis.json",
            mime="application/json"
        )

def main():
    st.set_page_config(page_title="Crypto Trading Bot Dashboard", layout="wide")
    st.title("🚀 Advanced Crypto Trading Bot Dashboard")
    st.markdown("*Comprehensive analysis of trading performance and setups*")

    # Load data
    df = load_data()
    if df.empty:
        st.warning("No trade data found yet. Please ensure the trade log file exists at the specified path.")
        return

    # Preprocess dataframe for better display
    if "indicator_scores" in df.columns:
        df.loc[:, "indicators"] = df["indicator_scores"].apply(format_indicator_scores)
        df.loc[:, "top_indicator"] = df["indicator_scores"].apply(top_indicator)

    if "tf_scores" in df.columns:
        df.loc[:, "tf_scores_display"] = df["tf_scores"].apply(format_tf_scores)

    # Filter data
    df_filtered = filter_data(df)
    
    # Show count of filtered trades
    st.markdown(f"### 📋 Showing {len(df_filtered)} trades (filtered from {len(df)} total)")

    # Display summary statistics
    display_summary_stats(df_filtered)
    
    # Add tabs for better organization
    overview_tab, active_tab, closed_tab, analysis_tab, drilldown_tab, export_tab = st.tabs([
        "Performance Overview", "Active Trades", "Completed Trades", 
        "Indicator Analysis", "Trade Drilldown", "Export"
    ])
    
    with overview_tab:
        display_result_breakdown(df_filtered)
        display_performance_charts(df_filtered)
        
    with active_tab:
        df_open = df_filtered[df_filtered.result == "open"]
        if not df_open.empty:
            display_trade_table(df_open, "Active Trades")
        else:
            st.info("No active trades found with current filters.")
            
    with closed_tab:
        df_closed = df_filtered[df_filtered.result != "open"]
        if not df_closed.empty:
            display_trade_table(df_closed, "Completed Trades")
        else:
            st.info("No completed trades found with current filters.")
            
    with analysis_tab:
        display_indicator_details(df_filtered)
        
    with drilldown_tab:
        display_trade_drilldown(df_filtered)
        
    with export_tab:
        export_data(df_filtered)

if __name__ == "__main__":
    main()
