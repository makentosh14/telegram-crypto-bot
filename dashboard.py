import pandas as pd
import streamlit as st
import os
from datetime import datetime
import json

LOG_PATH = "/mnt/data/trade_logs/trade_setups.csv"

def load_data():
    if os.path.exists(LOG_PATH):
        df = pd.read_csv(LOG_PATH, engine="python", quotechar='"', skip_blank_lines=True, on_bad_lines='skip')
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
        df = df.sort_values(by="timestamp", ascending=False)
        return df
    else:
        return pd.DataFrame()

def display_summary_stats(df):
    total = len(df)
    wins = len(df[df.result == "win"])
    losses = len(df[df.result == "loss"])
    breakeven = len(df[df.result == "breakeven"])
    open_trades = len(df[df.result == "open"])

    win_rate = (wins / (wins + losses) * 100) if (wins + losses) else 0
    avg_score = df.score.mean() if total else 0
    avg_conf = df.confidence.mean() if total else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Trades", total)
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Avg Score", f"{avg_score:.2f}")
    col4.metric("Avg Confidence", f"{avg_conf:.2f}%")

def display_trade_table(df, title):
    st.write(f"### 📋 {title}")
    preferred_columns = ["timestamp", "symbol", "direction", "entry_price", "sl", "tp1", "tp2", "result", "score", "trade_type", "confidence"]
    existing_columns = [col for col in preferred_columns if col in df.columns]
    df_display = df[existing_columns].copy()

    def highlight_result(val):
        if val == "win":
            return "background-color: #b7f7b0"
        elif val == "loss":
            return "background-color: #f8b8b8"
        elif val == "breakeven":
            return "background-color: #f5f5a0"
        elif val == "open":
            return "background-color: #cce5ff"
        return ""

    if "result" in df_display.columns:
        styled_df = df_display.style.map(highlight_result, subset=["result"])
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.dataframe(df_display, use_container_width=True)

def display_result_breakdown(df):
    st.write("### 📊 Trade Result Breakdown")

    tp2_hits = len(df[(df.result == "win") & df.tp2.notna()])
    tp1_only = len(df[(df.result == "breakeven") & df.tp1.notna() & df.tp2.isna()])
    sl_hits = len(df[df.result == "loss"])
    open_trades = len(df[df.result == "open"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("TP2 Wins", tp2_hits)
    col2.metric("TP1 Only", tp1_only)
    col3.metric("SL Hits", sl_hits)
    col4.metric("Open Trades", open_trades)

def display_indicator_details(df):
    st.write("### 🧠 Indicator Breakdown — Most Recent Trade")
    if df.empty:
        st.warning("No data available to display indicator details.")
        return

    latest = df.iloc[0]

    if "indicator_scores" in latest and pd.notna(latest["indicator_scores"]):
        try:
            scores = json.loads(latest["indicator_scores"])
            st.subheader("📊 Indicator Scores")
            st.json(scores)
        except Exception as e:
            st.error(f"Error parsing indicator scores: {e}")

    if "used_indicators" in latest and pd.notna(latest["used_indicators"]):
        try:
            indicators = json.loads(latest["used_indicators"])
            st.subheader("✅ Used Indicators")
            st.markdown(", ".join(indicators))
        except Exception as e:
            st.error(f"Error parsing used indicators: {e}")

def filter_data(df):
    symbols = df.symbol.unique().tolist()
    trade_types = df.trade_type.unique().tolist()
    directions = df.direction.unique().tolist()

    with st.sidebar:
        st.write("## 🔍 Filters")
        selected_symbols = st.multiselect("Symbols", symbols, default=symbols)
        selected_types = st.multiselect("Trade Types", trade_types, default=trade_types)
        selected_directions = st.multiselect("Direction", directions, default=directions)
        hide_open = st.checkbox("Hide Open Trades", value=False)

    df_filtered = df[
        df.symbol.isin(selected_symbols) &
        df.trade_type.isin(selected_types) &
        df.direction.isin(selected_directions)
    ]

    if hide_open:
        df_filtered = df_filtered[df_filtered.result != "open"]

    return df_filtered

def main():
    st.set_page_config(page_title="Crypto Bot Dashboard", layout="wide")
    st.title("🚀 Crypto Trading Bot Dashboard")

    df = load_data()
    if df.empty:
        st.warning("No trade data found yet.")
        return

    df_filtered = filter_data(df)
    df_open = df_filtered[df_filtered.result == "open"]
    df_closed = df_filtered[df_filtered.result != "open"]

    display_summary_stats(df_filtered)
    display_result_breakdown(df_filtered)

    if not df_open.empty:
        display_trade_table(df_open, "Active Trades")

    if not df_closed.empty:
        display_trade_table(df_closed, "Completed Trades")

    display_indicator_details(df_filtered)

if __name__ == "__main__":
    main()
