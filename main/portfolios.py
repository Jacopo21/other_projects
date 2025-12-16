import streamlit as st
import pandas as pd
from pathlib import Path
import altair as alt
import yfinance as yf
from datetime import datetime, timedelta
from translations import TRANSLATIONS 

st.set_page_config(layout="wide", page_title="Galambos Capital")

# --- Language Setup ---
if 'language' not in st.session_state:
    st.session_state['language'] = 'en' 

language_options = {
    "EN": "en",
    "HU": "hu",
    "IT": "it"
}

def set_language():
    st.session_state.language = language_options[st.session_state.lang_selector]

def _(key):
    return TRANSLATIONS.get(st.session_state.language, {}).get(key, key)

# --- Navigation State ---
if 'page' not in st.session_state:
    st.session_state.page = 'landing'

def go_to_landing():
    st.session_state.page = 'landing'

def go_to_alternative():
    st.session_state.page = 'alternative'

def go_to_portfolio():
    st.session_state.page = 'portfolio'

base = Path(__file__).parent

# --- Helper: Render Top Header ---
def render_header(show_home=True):
    """Renders the top navigation bar with optional Home button and Language selector."""
    
    col1, col2, col3 = st.columns([1, 4, 1], vertical_alignment="center")
    
    with col1:
        if show_home:
            if st.button("← Home", key="nav_home"):
                go_to_landing()
                st.rerun()
        else:
            logo_path = base / "logo2.png"
            if logo_path.exists(): 
                st.image(str(logo_path), width=150)
    
    with col3:
        current_label = [k for k, v in language_options.items() if v == st.session_state.language][0]
        st.selectbox(
            "Language", 
            options=list(language_options.keys()), 
            index=list(language_options.keys()).index(current_label),
            key='lang_selector', 
            on_change=set_language, 
            label_visibility="collapsed"
        )
    
    st.divider()

# --- Data Loading Functions ---
@st.cache_data
def load_static_data():
    """Loads static data for IBUST and USEquity500."""
    try:
        excel_path = base / "streamlit_performances.xlsx"
        if not excel_path.is_file():
            return None
        
        data = {
            "IBUST": pd.read_excel(excel_path, sheet_name="IBUST"),
            "USEquity500": pd.read_excel(excel_path, sheet_name="USEquity500"),
        }
        
        for name, df in data.items():
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            if 'win' in df.columns and df['win'].dtype == 'object':
                df['win'] = df['win'].map({'YES': 1, 'NO': 0}).fillna(0)
            
            numeric_cols = ['netprofit', 'equity used', 'returns on equity', 'leverage used', 'win', 'cumulative returns', 'cumulative return']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            if 'cumulative return' in df.columns:
                df.rename(columns={'cumulative return': 'cumulative returns'}, inplace=True)
                
        return data
    except Exception as e:
        st.error(f"Error loading static data: {e}")
        return None

@st.cache_data(ttl=3600)
def get_portfolio_data():
    """Calculates live portfolio performance using Weighted Average Price logic with robust fallbacks."""
    try:
        portfolio_path = base / "portfolioGC.xlsx"
        if not portfolio_path.is_file():
            st.error("Portfolio file not found.")
            return None, None, None

        purchases = pd.read_excel(portfolio_path, sheet_name="purchases")
        purchases['bought_on'] = pd.to_datetime(purchases['bought_on'])
        
        if purchases.empty:
            return None, None, None
            
        purchases['ticker'] = purchases['ticker'].astype(str).str.strip()
        tickers = purchases['ticker'].unique().tolist()
        
        first_purchase = purchases['bought_on'].min()
        
        # --- Date Handling ---
        # Include today (15th) to show the "doubling" effect.
        today = datetime.now().date()
        end_date = today + timedelta(days=1) 
        start_date = first_purchase

        try:
            market_data = yf.download(
                tickers, 
                start=start_date, 
                end=end_date, 
                interval='1d', 
                auto_adjust=True, 
                progress=False
            )['Close']
        except Exception as e:
            st.warning(f"Warning: Issue fetching data from Yahoo Finance ({e}). Attempting fallback.")
            market_data = pd.DataFrame() # Fallback to empty to trigger logic below
        
        if market_data.empty:
             date_range = pd.date_range(start=start_date, end=today, freq='B')
             market_data = pd.DataFrame(index=date_range)
        
        if isinstance(market_data, pd.Series):
            market_data = market_data.to_frame(name=tickers[0])
            
        market_data.index = market_data.index.tz_localize(None)

        if 'GC=F' in market_data.columns:
            market_data.rename(columns={'GC=F': 'GOLD'}, inplace=True)
        purchases['ticker'] = purchases['ticker'].replace('GC=F', 'GOLD')
        
        tickers = purchases['ticker'].unique().tolist()

        for t in tickers:
            if t not in market_data.columns:
                match = purchases[purchases['ticker'] == t]
                if not match.empty:
                    fallback_price = match['price'].iloc[0]
                    market_data[t] = fallback_price
        
        market_data = market_data.ffill().bfill()        
        market_data = market_data[market_data.index.dayofweek < 5]

        nav_series = []
        
    
        for date, prices in market_data.iterrows():
            
            # Identify active holdings on this date
            active_holdings = purchases[purchases['bought_on'] <= date].copy()
            
            if active_holdings.empty:
                nav_series.append({'date': date, 'nav': 0.0, 'invested': 0.0})
                continue

            daily_nav = 0
            daily_invested = 0
            
            for _, row in active_holdings.iterrows():
                t = row['ticker']
                qty = row['amount']
                purchase_price = row['price']
                
                # NAV
                if t in prices and not pd.isna(prices[t]):
                    daily_nav += prices[t] * qty
                
                # Invested (Sums all purchases -> Weighted Average Logic)
                daily_invested += purchase_price * qty
            
            nav_series.append({'date': date, 'nav': daily_nav, 'invested': daily_invested})
        
        nav_df = pd.DataFrame(nav_series)
        
        if not nav_df.empty:
            real_activity_df = nav_df[nav_df['invested'] > 0]
            
            if not real_activity_df.empty:
                nav_df = real_activity_df.reset_index(drop=True)
                first_date = nav_df.iloc[0]['date']
                first_invested = nav_df.iloc[0]['invested']
                
                # Anchor for chart
                inception_row = pd.DataFrame([{
                    'date': first_date,
                    'nav': first_invested,
                    'invested': first_invested
                }])
                
                nav_df = pd.concat([inception_row, nav_df]).reset_index(drop=True)
                nav_df['cumulative returns'] = (nav_df['nav'] - nav_df['invested']) / nav_df['invested']
            else:
                nav_df['cumulative returns'] = 0.0

        # --- Holdings Snapshot (Latest) ---
        latest_prices = market_data.iloc[-1]
        
        holdings_snapshot = purchases.groupby('ticker').agg({
            'amount': 'sum',
            'bought_on': 'min'
        }).reset_index()

        holdings_snapshot['current_price'] = holdings_snapshot['ticker'].map(latest_prices)
        holdings_snapshot = holdings_snapshot.dropna(subset=['current_price'])
        
        holdings_snapshot['market_value'] = holdings_snapshot['amount'] * holdings_snapshot['current_price']
        
        def get_total_cost(ticker):
            rows = purchases[purchases['ticker'] == ticker]
            return (rows['amount'] * rows['price']).sum()

        holdings_snapshot['cost_basis_total'] = holdings_snapshot['ticker'].apply(get_total_cost)
        
        # Weighted Average Entry Price
        holdings_snapshot['avg_entry_price'] = holdings_snapshot['cost_basis_total'] / holdings_snapshot['amount']
        
        total_mv = holdings_snapshot['market_value'].sum()
        holdings_snapshot['weight'] = (holdings_snapshot['market_value'] / total_mv) * 100
        holdings_snapshot['unrealized_pnl'] = holdings_snapshot['market_value'] - holdings_snapshot['cost_basis_total']
        holdings_snapshot['return_pct'] = (holdings_snapshot['unrealized_pnl'] / holdings_snapshot['cost_basis_total'])*100
        holdings_snapshot['return_pct'] = holdings_snapshot['return_pct'].round(2)


        return nav_df, holdings_snapshot, market_data

    except Exception as e:
        st.error(f"Error calculating portfolio: {e}")
        return None, None, None

def plot_chart(df, y_col, title, color='red', format_type='percent', area=False):
    if df is None or df.empty:
        return
    
    scale_config = alt.Scale(zero=False)

    if format_type == 'percent':
        y_axis = alt.Y(f"{y_col}:Q", title=title, axis=alt.Axis(format='%'), scale=scale_config)
        tooltip_format = ".2%"
    elif format_type == 'dollar':
        y_axis = alt.Y(f"{y_col}:Q", title=title, axis=alt.Axis(format='$,.0f'), scale=scale_config)
        tooltip_format = "$,.2f"
    else: 
        y_axis = alt.Y(f"{y_col}:Q", title=title, scale=scale_config)
        tooltip_format = ".2f"

    base_c = alt.Chart(df).encode(
        x=alt.X("date:T", title=_("chart_date")),
        y=y_axis,
        tooltip=[
            alt.Tooltip("date:T", format="%Y-%m-%d"),
            alt.Tooltip(f"{y_col}:Q", title=title, format=tooltip_format)
        ]
    )

    if area:
        chart = base_c.mark_area(
            color=alt.Gradient(
                gradient='linear',
                stops=[alt.GradientStop(color=color, offset=0),
                       alt.GradientStop(color='white', offset=1)],
                x1=1, x2=1, y1=1, y2=0
            ),
            line={'color': color},
            opacity=0.5
        )
    else:
        chart = base_c.mark_line(color=color, strokeWidth=2)

    st.altair_chart(chart.properties(title=title, height=350).interactive(), use_container_width=True)

# --- PAGE: LANDING ---
if st.session_state.page == 'landing':
    render_header(show_home=False)

    st.title("Galambos Capital Dashboard")
    st.markdown("### Welcome to the Galambos Capital Investment Dashboard")
    st.markdown("Please select an investment category to view performance.")
    
    spacer, btn_col1, btn_col2, spacer2 = st.columns([1, 3, 3, 1])
    
    with btn_col1:
        st.info("### Alternative Solutions")
        st.write("Quantitative strategies including USEquity 500")
        if st.button("Enter Alternative Section", use_container_width=True):
            go_to_alternative()
            st.rerun()

    with btn_col2:
        st.success("### GC I - US Equity Portfolio")
        st.write("Medium risk equity fund")
        if st.button("Enter Portfolio Section", use_container_width=True):
            go_to_portfolio()
            st.rerun()

# --- PAGE: ALTERNATIVE ---
elif st.session_state.page == 'alternative':
    render_header(show_home=True)
    
    col_sel1, col_sel2 = st.columns([1, 3])
    with col_sel1:
        st.write(f"**{_('fund_selection')}**")
    with col_sel2:
        fund_list = ["USEquity500", "IBUST (Inactive)"]
        selected_fund = st.selectbox(_("select_fund"), fund_list, label_visibility="collapsed")

    st.title(f"Alternative Investing: {selected_fund}")
    
    static_data = load_static_data()
    
    if selected_fund == "USEquity500" and static_data:
        df = static_data["USEquity500"]
        
        plot_chart(df, "cumulative returns", "Cumulative Performance", format_type='raw')
        
        df['Month'] = df['date'].dt.to_period('M').astype(str)
        monthly_options = sorted(df['Month'].unique(), reverse=True)

        st.subheader(_("overall_performance"))
        overall_pnl = df['netprofit'].sum()
        overall_win_rate = df['win'].mean() * 100
        overall_avg_leverage = df['leverage used'].mean()
        
        c1, c2, c3 = st.columns(3)
        c1.metric(_("total_profit_loss"), f"${overall_pnl:,.2f}")
        c2.metric(_("overall_win_rate"), f"{overall_win_rate:.2f}%")
        c3.metric(_("average_leverage"), f"{overall_avg_leverage:.2f}x")
        
        st.divider()
        st.subheader(_("monthly_performance"))
        selected_month = st.selectbox(_("select_month"), options=monthly_options)
        
        if selected_month:
            month_df = df[df['Month'] == selected_month]
            if not month_df.empty:
                monthly_pnl = month_df['netprofit'].sum()
                avg_leverage = month_df['leverage used'].mean()
                total_monthly_return = month_df['returns on equity'].sum()
                win_rate = month_df['win'].mean() * 100
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric(_("total_return"), f"{total_monthly_return:.2%}")
                col2.metric(_("monthly_pnl"), f"${monthly_pnl:,.2f}")
                col3.metric(_("avg_leverage"), f"{avg_leverage:.2f}x")
                col4.metric(_("win_rate"), f"{win_rate:.2f}%")

    elif selected_fund == "IBUST (Inactive)" and static_data:
        df = static_data["IBUST"]
        plot_chart(df, "cumulative returns", "Historical Performance", color='grey', format_type='percent')
        st.warning("This strategy is currently inactive.")
        st.dataframe(df.head())

# --- PAGE: PORTFOLIO ---
elif st.session_state.page == 'portfolio':
    render_header(show_home=True)

    st.title("Equity Portfolio: Medium Risk Fund")
    
    with st.spinner("Fetching live market data..."):
        nav_df, holdings, market_data = get_portfolio_data()

    if nav_df is not None and holdings is not None:
        latest_nav = nav_df.iloc[-1]['nav']
        latest_invested = nav_df.iloc[-1]['invested']
        total_ret_pct = nav_df.iloc[-1]['cumulative returns']
        total_pnl = latest_nav - latest_invested
        initial_date = nav_df.iloc[0]['date'].strftime('%Y-%m-%d')
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Current NAV", f"${latest_nav:,.2f}")
        m2.metric("Total Invested", f"${latest_invested:,.2f}")
        m3.metric("Total PnL", f"${total_pnl:,.2f}", delta=f"{total_ret_pct:.2%}")
        m4.metric("Inception Date", initial_date)
        
        st.divider()

        st.subheader("Performance Trends")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("**Cumulative Return (%)**")
            plot_chart(nav_df, "cumulative returns", "Return Since Inception", color='#2ECC71', format_type='percent')
        with col_c2:
            st.markdown("**Net Asset Value (NAV)**")
            plot_chart(nav_df, "nav", "NAV ($) Since Inception", color='#3498DB', format_type='dollar', area=True)

        st.divider()
    
        st.subheader("Portfolio Allocation & Holdings")
        
        selection = alt.selection_point(fields=['ticker'], on='click', bind='legend')
        
        base_chart = alt.Chart(holdings).encode(
            theta=alt.Theta("market_value", stack=True)
        )
        
        pie = base_chart.mark_arc(outerRadius=120).encode(
            color=alt.Color("ticker"),
            order=alt.Order("market_value", sort="descending"),
            opacity=alt.condition(selection, alt.value(1), alt.value(0.3)),
            tooltip=["ticker", "amount", alt.Tooltip("weight", format=".2f", title="Allocation (%)"), alt.Tooltip("market_value", format="$,.2f")]
        ).add_params(selection)
        
        text = base_chart.mark_text(radius=140).encode(
            text=alt.Text("weight", format=".1f"),
            order=alt.Order("market_value", sort="descending"),
            color=alt.value("black")  
        )
        
        st.altair_chart(pie + text, use_container_width=True)
        
        # DataFrame Display with Avg Entry Price
        display_df = holdings[['ticker', 'amount', 'avg_entry_price', 'current_price', 'market_value', 'unrealized_pnl', 'weight', 'return_pct']].copy()
        
        st.dataframe(
            display_df,
            column_config={
                "ticker": "Ticker",
                "amount": "Qty",
                "avg_entry_price": st.column_config.NumberColumn("Avg Entry Price", format="$%.2f"),
                "current_price": st.column_config.NumberColumn("Current Price", format="$%.2f"),
                "market_value": st.column_config.NumberColumn("Market Value", format="$%.2f"),
                "unrealized_pnl": st.column_config.NumberColumn("Unrealized PnL", format="$%.2f"),
                "weight": st.column_config.ProgressColumn("Allocation", format="%.2f%%", min_value=0, max_value=100),
                "return_pct": st.column_config.NumberColumn("Return %", format="%.2%") 
            },
            hide_index=True,
            use_container_width=True
        )

        st.divider()
        st.subheader("Individual Asset Analysis")
        
        asset_options = holdings['ticker'].unique().tolist()
        selected_asset = st.selectbox("Select Asset to View Price History", options=asset_options)
        
        if selected_asset and selected_asset in market_data.columns:
            current_year = datetime.now().year
            ytd_start = datetime(current_year, 1, 1)
            
            asset_df = market_data[[selected_asset]].copy()
            
            asset_df = asset_df.reset_index()
            asset_df.columns = ['date', 'close'] 
            
            asset_df = asset_df[asset_df['date'] >= ytd_start]
            asset_df = asset_df.dropna()
            
            chart = alt.Chart(asset_df).mark_area(
                line={'color':'#2980B9'},
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='#2980B9', offset=0),
                           alt.GradientStop(color='white', offset=1)],
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(
                x=alt.X("date:T", title=_("chart_date")),
                y=alt.Y("close:Q", scale=alt.Scale(zero=False), title="Close Price ($)"),
                tooltip=["date:T", alt.Tooltip("close:Q", format="$,.2f")]
            ).properties(
                title=f"{selected_asset} Price History (YTD)",
                height=350
            ).interactive()
            
            st.altair_chart(chart, use_container_width=True)
        elif selected_asset:
            st.warning(f"Price data not available for {selected_asset}")

    else:
        st.info("Please verify the 'portfolioGC.xlsx' file is in the directory and contains valid data.")