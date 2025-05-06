import pandas as pd
import streamlit as st
import os
import json

LOG_PATH = "/mnt/data/trade_logs/trade_setups.csv"

def load_data():
    if not os.path.exists(LOG_PATH):
        st.error("❌ trade_setups.csv not found.")
        return pd.DataFrame()

    df = pd.read_csv(
        LOG_PATH,
        engine="python",
        quotechar='"',
        skip_blank_lines=True,
        on_bad_lines='skip'
    )

    required_cols = [
        "timestamp", "symbol", "direction", "entry", "sl", "tp1", "tp2",
        "result", "score", "trade_type", "confidence",
        "indicator_scores", "used_indicators",
        "pattern_detected", "whale_signal", "volume_spike", "sl_strategy"
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df[df["symbol"].notna() & df["entry"].notna()]
    df = df.sort_values(by="timestamp", ascending=False)

    st.write("✅ Loaded trade setups:", df.shape)
    return df

def display_summary_stats(df):
    total = len(df)
    wins = len(df[df.result == "win"])
    losses = len(df[df.result == "loss"])
    breakeven = len(df[df.result == "breakeven"])
    open_trades = len(df[df.result == "open"])
    win_rate = (wins / total * 100) if total else 0
    avg_score = df.score.astype(float).mean() if total else 0
    avg_conf = df.confidence.astype(float).mean() if total else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Trades", total)
    col2.metric("Open", open_trades)
    col3.metric("Win Rate", f"{win_rate:.1f}%")
    col4.metric("Avg Score", f"{avg_score:.2f}")
    col5.metric("Avg Confidence", f"{avg_conf:.2f}%")

def display_trade_table(df):
    st.write("### 📋 Trade Log")
    st.dataframe(df[[
        "timestamp", "symbol", "direction", "score", "confidence", "trade_type", "result", "entry", "sl", "tp1", "tp2"
    ]], use_container_width=True)

def display_indicator_details(df):
    st.write("### 🧠 Most Recent Trade Indicators")

    if df.empty:
        st.warning("No data available.")
        return

    latest = df.iloc[0]
    st.write(f"**Symbol:** {latest['symbol']} | **Result:** {latest['result']}")

    try:
        indicators = json.loads(latest["used_indicators"]) if pd.notna(latest["used_indicators"]) and latest["used_indicators"] != "{}" else []
        st.subheader("✅ Used Indicators")
        st.markdown(", ".join(indicators))
    except Exception as e:
        st.error(f"Indicator parse error: {e}")

    try:
        scores = json.loads(latest["indicator_scores"]) if pd.notna(latest["indicator_scores"]) and latest["indicator_scores"] != "{}" else {}
        st.subheader("📊 Indicator Scores")
        st.json(scores)
    except Exception as e:
        st.error(f"Score parse error: {e}")

def main():
    st.set_page_config(page_title="📈 Crypto Bot Dashboard", layout="wide")
    st.title("🚀 Crypto Trading Bot Dashboard")

    df = load_data()
    if df.empty:
        st.warning("No trade data found.")
        return

    display_summary_stats(df)
    display_trade_table(df)
    display_indicator_details(df)

if __name__ == "__main__":
    main()
