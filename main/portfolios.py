# run using: streamlit run portfolios.py
import streamlit as st
import pandas as pd
from pathlib import Path
import altair as alt

st.set_page_config(layout="wide")
st.title("Galambos Capital Dashboard")

st.markdown(
    """
    Welcome to our interactive portfolio dashboard. Use the sidebar to select a fund and explore its performance over time.
    """
)

@st.cache_data
def load_data():
    try:
        excel_path = Path("streamlit_performances.xlsx")

        if not excel_path.is_file():
            st.error(f"FATAL: The Excel file '{excel_path}' was not found.")
            st.error("SOLUTION: Please make sure your Python script and the Excel file are in the same folder.")
            return None
        
        data = {
            "IBUST": pd.read_excel(excel_path, sheet_name="IBUST"),
            "USEquity500": pd.read_excel(excel_path, sheet_name="USEquity500")
        }
        
        for name, df in data.items():
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            else:
                st.error(f"The '{name}' sheet is missing the required 'date' column.")
                continue

            if 'win' in df.columns:
                if df['win'].dtype == 'object':
                    df['win'] = df['win'].map({'YES': 1, 'NO': 0}).fillna(0)

            numeric_cols = [
                'netprofit', 'equity used', 'returns on equity', 'position size', 
                'leverage used', 'win', 'cumulative return', 'cumulative returns'
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            if 'cumulative return' in df.columns:
                df.rename(columns={'cumulative return': 'cumulative returns'}, inplace=True)
        
        return data
    except Exception as e:
        st.error(f"An error occurred while loading the data: {e}")
        return None

# --- PLOTTING FUNCTION ---
def plot_performance(df, fund_name):
    if df is None or 'cumulative returns' not in df.columns:
        st.warning(f"Cannot plot performance for {fund_name} as 'cumulative returns' data is missing.")
        return
    
    chart = alt.Chart(df).mark_line(color='black', strokeWidth=2).encode(
        x=alt.X("date:T", title="Date"),
        y=alt.Y("cumulative returns:Q", title="Cumulative Returns", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip("cumulative returns:Q", title="Returns", format=",.2f")]
    ).properties(
        title={"text": f"{fund_name} Cumulative Returns", "fontSize": 20, "anchor": "start"}
    ).configure_view(strokeWidth=0).configure_axis(grid=True).interactive()
    
    st.altair_chart(chart, use_container_width=True)

# --- MAIN APPLICATION LOGIC ---
data_frames = load_data()

if data_frames:
    st.sidebar.title("Fund Selection")
    selected_fund = st.sidebar.selectbox("Select a fund to analyze:", options=list(data_frames.keys()))

    st.header(f"Performance Analysis for: {selected_fund}")
    df_selected = data_frames[selected_fund].copy()

    plot_performance(df_selected, selected_fund)
    st.divider()

    df_selected['Month'] = df_selected['date'].dt.to_period('M').astype(str)
    monthly_options = sorted(df_selected['Month'].unique(), reverse=True)

    if selected_fund == "IBUST":
        def get_ibust_stats(df):
            if df.empty: return {key: 0 for key in ["pnl", "avg_equity", "win_rate", "avg_win", "long_count", "short_count", "long_win_rate", "short_win_rate"]}
            df['win'] = (df['netprofit'] > 0).astype(int)
            stats = {'pnl': df['netprofit'].sum(), 'avg_equity': df['equity used'].mean(), 'win_rate': df['win'].mean() * 100, 'avg_win': df[df['win'] == 1]['netprofit'].mean() if not df[df['win'] == 1].empty else 0}
            long_trades = df[df['direction'] == 'LONG']; short_trades = df[df['direction'] == 'SHORT']
            stats.update({'long_count': len(long_trades), 'short_count': len(short_trades), 'long_win_rate': (long_trades['win'].mean() * 100) if not long_trades.empty else 0, 'short_win_rate': (short_trades['win'].mean() * 100) if not short_trades.empty else 0})
            return stats

        st.subheader("Overall Performance")
        overall_stats = get_ibust_stats(df_selected)
        c1, c2, c3, c4 = st.columns(4); c1.metric("Total PnL", f"${overall_stats['pnl']:,.2f}"); c2.metric("Avg Equity Used", f"${overall_stats['avg_equity']:,.2f}"); c3.metric("Overall Win Rate", f"{overall_stats['win_rate']:.2f}%"); c4.metric("Avg Win PnL", f"${overall_stats['avg_win']:,.2f}")
        c1, c2, c3, c4 = st.columns(4); c1.metric("Long Trades", overall_stats['long_count']); c2.metric("Long Win Rate", f"{overall_stats['long_win_rate']:.2f}%"); c3.metric("Short Trades", overall_stats['short_count']); c4.metric("Short Win Rate", f"{overall_stats['short_win_rate']:.2f}%")
        st.divider()

        st.subheader("Monthly Performance Breakdown")
        selected_month = st.selectbox("Select a Month", options=monthly_options, key="ibust_month")
        if selected_month:
            month_df = df_selected[df_selected['Month'] == selected_month]
            monthly_stats = get_ibust_stats(month_df)
            c1, c2, c3, c4 = st.columns(4); c1.metric("Monthly PnL", f"${monthly_stats['pnl']:,.2f}"); c2.metric("Avg Equity", f"${monthly_stats['avg_equity']:,.2f}"); c3.metric("Win Rate", f"{monthly_stats['win_rate']:.2f}%"); c4.metric("Avg Win PnL", f"${monthly_stats['avg_win']:,.2f}")
            c1, c2, c3, c4 = st.columns(4); c1.metric("Long Trades", monthly_stats['long_count']); c2.metric("Long Win Rate", f"{monthly_stats['long_win_rate']:.2f}%"); c3.metric("Short Trades", monthly_stats['short_count']); c4.metric("Short Win Rate", f"{monthly_stats['short_win_rate']:.2f}%")

    elif selected_fund == "USEquity500":
        st.subheader("Overall Performance")
        overall_pnl = df_selected['netprofit'].sum()
        overall_win_rate = df_selected['win'].mean() * 100
        overall_avg_leverage = df_selected['leverage used'].mean()
        c1, c2, c3 = st.columns(3); c1.metric("Total Profit & Loss", f"${overall_pnl:,.2f}"); c2.metric("Overall Win Rate", f"{overall_win_rate:.2f}%"); c3.metric("Average Leverage", f"{overall_avg_leverage:.2f}x")
        st.divider()

        st.subheader("Monthly Performance Breakdown")
        selected_month = st.selectbox("Select a Month", options=monthly_options, key="usequity_month")
        if selected_month:
            month_df = df_selected[df_selected['Month'] == selected_month]
            if not month_df.empty:
                monthly_pnl = month_df['netprofit'].sum()
                avg_leverage = month_df['leverage used'].mean()
                total_monthly_return = month_df['returns on equity'].sum()
                avg_monthly_return = month_df['returns on equity'].mean()
                win_rate = month_df['win'].mean() * 100
                
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Total Return", f"{total_monthly_return:.2%}"); col2.metric("Avg Leverage", f"{avg_leverage:.2f}x"); col3.metric("Monthly PnL", f"${monthly_pnl:,.2f}"); col4.metric("Avg Return", f"{avg_monthly_return:.2%}"); col5.metric("Win Rate", f"{win_rate:.2f}%")

    with st.expander("View Raw Data for " + selected_fund):
        st.dataframe(df_selected)
else:
    st.warning("Dashboard could not be loaded. Please check the file path and format.")
