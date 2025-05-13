import pandas as pd
import streamlit as st
import os
from datetime import datetime
import json

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

def load_data():
    if os.path.exists(LOG_PATH):
        df = pd.read_csv(LOG_PATH, engine="python", quotechar='"', skip_blank_lines=True, on_bad_lines='skip')
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
        df = df.sort_values(by="timestamp", ascending=False)

        df["exit_price"] = df.apply(lambda row: row["tp2"] if row["result"] == "win" else (row["tp1"] if "tp1" in str(row["result"]) else row["sl"]), axis=1)
        df["move_pct"] = ((df["exit_price"] - df["entry_price"]) / df["entry_price"] * 100).round(2)
        df["score_delta"] = df["score"] - df["confidence"]
        df["signal_tag"] = df.apply(classify_signal, axis=1)
        return df
    else:
        return pd.DataFrame()

def classify_signal(row):
    try:
        if row.get("whale_signal"):
            return "🐳 Whale Entry"
        if row.get("confidence", 0) >= 85:
            return "🔥 Prime Setup"
        if row.get("volume_spike") == False:
            return "💤 Low Volume"
        if row.get("score", 0) < 6.5:
            return "⚠️ Weak Setup"
        return "✅ Confirmed"
    except:
        return "🧪 Unknown"

def format_indicator_scores(raw):
    try:
        scores = json.loads(raw)
        readable = [f"{INDICATOR_MAP.get(str(k), k)}: {v}" for k, v in scores.items() if float(v) > 0]
        return "\n".join(readable) if readable else "—"
    except:
        return "—"

def top_indicator(raw):
    try:
        scores = json.loads(raw)
        sorted_items = sorted(scores.items(), key=lambda x: float(x[1]), reverse=True)
        return INDICATOR_MAP.get(sorted_items[0][0], sorted_items[0][0]) if sorted_items else ""
    except:
        return ""

def format_tf_scores(raw):
    try:
        scores = json.loads(raw)
        return ", ".join(f"{TF_LABELS.get(tf, tf)}: {val}" for tf, val in scores.items())
    except:
        return "—"

def display_trade_table(df, title):
    st.write(f"### 📋 {title}")
    preferred_columns = [
        "timestamp", "symbol", "direction", "entry_price", "exit_price", "move_pct",
        "score", "confidence", "score_delta", "signal_tag",
        "result", "trade_type", "tf_scores", "indicators", "top_indicator",
        "missed_upside", "pullback_after"
    ]
    existing_columns = [col for col in preferred_columns if col in df.columns]
    df_display = df[existing_columns].copy()

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
    st.write("### 📊 Trade Result Breakdown")

    tp2_hits = len(df[(df.result == "win") & df.tp2.notna()])
    tp1_only = len(df[df.result.isin(["tp1", "tp1-partial", "breakeven"])])
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
            readable = {INDICATOR_MAP.get(k, k): v for k, v in scores.items()}
            st.json(readable)
        except Exception as e:
            st.error(f"Error parsing indicator scores: {e}")

    if "used_indicators" in latest and pd.notna(latest["used_indicators"]):
        try:
            indicators = json.loads(latest["used_indicators"])
            st.subheader("✅ Used Indicators")
            st.markdown(", ".join([INDICATOR_MAP.get(i, i) for i in indicators]))
        except Exception as e:
            st.error(f"Error parsing used indicators: {e}")

def display_trade_drilldown(df):
    st.write("### 🧬 Per-Trade Deep Analysis")
    df = df.sort_values("timestamp", ascending=False)
    trade_options = df["symbol"] + " | " + df["timestamp"].astype(str)
    selected_row = st.selectbox("Select a trade to analyze", trade_options)

    if selected_row:
        try:
            symbol = selected_row.split(" | ")[0]
            row = df[df.symbol == symbol].iloc[0]
            st.markdown(f"#### 🧾 Trade: {row['symbol']} — {row['direction']} ({row['result']})")
            st.markdown(f"- **Entry**: {row['entry_price']}, **Exit**: {row['exit_price']}, **SL**: {row['sl']}, **TP1**: {row['tp1']}, **TP2**: {row['tp2']}")
            st.markdown(f"- **Score**: {row['score']}, **Confidence**: {row['confidence']}%, **Type**: {row['trade_type']}, **Move %**: {row['move_pct']}%")
            st.markdown(f"- **Signal Tag**: {row['signal_tag']}, **Top Indicator**: {row.get('top_indicator', '')}")
            st.markdown(f"- **Missed Upside**: {row.get('missed_upside', '–')}%, **Pullback After Exit**: {row.get('pullback_after', '–')}%")
            if pd.notna(row.get("tf_scores")):
                st.markdown("**📈 TF Scores:**")
                st.markdown(format_tf_scores(row["tf_scores"]))
            if pd.notna(row["indicator_scores"]):
                scores = json.loads(row["indicator_scores"])
                readable = {INDICATOR_MAP.get(k, k): v for k, v in scores.items()}
                st.markdown("**📊 Indicator Scores:**")
                st.json(readable)
            if pd.notna(row["used_indicators"]):
                st.markdown("**✅ Used Indicators:**")
                indicators = json.loads(row["used_indicators"])
                st.json([INDICATOR_MAP.get(i, i) for i in indicators])
        except Exception as e:
            st.error(f"Failed to display trade drilldown: {e}")

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

def display_summary_stats(df):
    total = len(df)
    wins = len(df[df.result == "win"])
    losses = len(df[df.result == "loss"])
    breakeven = len(df[df.result.isin(["breakeven", "tp1", "tp1-partial"])])
    open_trades = len(df[df.result == "open"])

    win_rate = (wins / (wins + losses) * 100) if (wins + losses) else 0
    avg_score = df.score.mean() if total else 0
    avg_conf = df.confidence.mean() if total else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Trades", total)
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Avg Score", f"{avg_score:.2f}")
    col4.metric("Avg Confidence", f"{avg_conf:.2f}%")

def main():
    st.set_page_config(page_title="Crypto Bot Dashboard", layout="wide")
    st.title("🚀 Crypto Trading Bot Dashboard")

    df = load_data()
    if df.empty:
        st.warning("No trade data found yet.")
        return

    df_filtered = filter_data(df)

    if "indicator_scores" in df_filtered.columns:
        df_filtered["indicators"] = df_filtered["indicator_scores"].apply(format_indicator_scores)
        df_filtered["top_indicator"] = df_filtered["indicator_scores"].apply(top_indicator)

    if "tf_scores" in df_filtered.columns:
        df_filtered["tf_scores"] = df_filtered["tf_scores"].apply(format_tf_scores)

    df_open = df_filtered[df_filtered.result == "open"]
    df_closed = df_filtered[df_filtered.result != "open"]

    display_summary_stats(df_filtered)
    display_result_breakdown(df_filtered)

    if not df_open.empty:
        display_trade_table(df_open, "Active Trades")

    if not df_closed.empty:
        display_trade_table(df_closed, "Completed Trades")

    display_indicator_details(df_filtered)
    display_trade_drilldown(df_filtered)

if __name__ == "__main__":
    main()
