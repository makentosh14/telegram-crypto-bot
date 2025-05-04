import pandas as pd
import streamlit as st
import os
from datetime import datetime

LOG_PATH = "/mnt/data/trade_logs/trade_setups.csv"

# Load trade data
def load_data():
    if os.path.exists(LOG_PATH):
        df = pd.read_csv(LOG_PATH)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
        df = df.sort_values(by="timestamp", ascending=False)
        return df
    else:
        return pd.DataFrame()

def display_trade_table(df):
    st.write("### Trade Log Table")
    st.dataframe(df, use_container_width=True)

def display_summary_stats(df):
    total = len(df)
    wins = len(df[df.result == "win"])
    losses = len(df[df.result == "loss"])
    breakeven = len(df[df.result == "breakeven"])
    win_rate = (wins / total * 100) if total else 0
    avg_score = df.score.mean() if total else 0
    avg_conf = df.confidence.mean() if total else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Trades", total)
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Avg Score", f"{avg_score:.2f}")
    col4.metric("Avg Confidence", f"{avg_conf:.2f}%")

def filter_data(df):
    symbols = df.symbol.unique().tolist()
    trade_types = df.trade_type.unique().tolist()
    directions = df.direction.unique().tolist()

    with st.sidebar:
        st.write("## Filters")
        selected_symbols = st.multiselect("Symbols", symbols, default=symbols)
        selected_types = st.multiselect("Trade Types", trade_types, default=trade_types)
        selected_directions = st.multiselect("Direction", directions, default=directions)

    df_filtered = df[
        df.symbol.isin(selected_symbols) &
        df.trade_type.isin(selected_types) &
        df.direction.isin(selected_directions)
    ]
    return df_filtered

def main():
    st.set_page_config(page_title="Crypto Bot Dashboard", layout="wide")
    st.title("📈 Crypto Trading Bot Dashboard")

    df = load_data()
    if df.empty:
        st.warning("No trade data found yet.")
        return

    df = filter_data(df)
    display_summary_stats(df)
    display_trade_table(df)

if __name__ == "__main__":
    main()
