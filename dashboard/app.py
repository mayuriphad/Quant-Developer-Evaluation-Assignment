import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import yaml
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.computations import simple_backtest

# Load configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

DB_PATH = config['database']['path']
SYMBOL_PAIRS = config['symbols']['pairs']
TIMEFRAMES = config['analytics']['timeframes']
REFRESH_INTERVAL = config['dashboard']['refresh_interval']
MAX_POINTS = config['dashboard']['max_display_points']

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title=config['dashboard']['title'],
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
    }
    .stAlert {
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 " + config['dashboard']['title'])
st.caption("Real-time cryptocurrency pairs trading analytics powered by Binance WebSocket")

# =====================================================
# SIDEBAR CONTROLS
# =====================================================
st.sidebar.header("⚙️ Controls")

# Symbol pair selection
pair_options = [f"{y}/{x}" for y, x in SYMBOL_PAIRS]
selected_pair_str = st.sidebar.selectbox(
    "Symbol Pair",
    options=pair_options,
    index=0
)
pair_y, pair_x = selected_pair_str.split('/')

# Timeframe selection
selected_timeframe = st.sidebar.selectbox(
    "Timeframe",
    options=TIMEFRAMES,
    index=1
)

# Alert threshold
z_alert = st.sidebar.slider(
    "Z-Score Alert Threshold",
    min_value=1.0,
    max_value=3.5,
    value=2.0,
    step=0.1
)

# Display options
show_volume = st.sidebar.checkbox("Show Volume", value=True)
show_backtest = st.sidebar.checkbox("Show Backtest", value=True)
show_stats_table = st.sidebar.checkbox("Show Statistics Table", value=True)

# Auto refresh
auto_refresh = st.sidebar.checkbox("Auto Refresh", value=True)

st.sidebar.divider()

# Download section
st.sidebar.header("📥 Export Data")

# =====================================================
# DATA LOADING FUNCTIONS
# =====================================================
@st.cache_data(ttl=REFRESH_INTERVAL)
def load_analytics(pair_y, pair_x, timeframe, limit=MAX_POINTS):
    """Load analytics data for a specific pair and timeframe"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    
    query = """
        SELECT *
        FROM analytics
        WHERE pair_y = ? AND pair_x = ? AND timeframe = ?
        ORDER BY ts DESC
        LIMIT ?
    """
    
    df = pd.read_sql(query, conn, params=(pair_y, pair_x, timeframe, limit))
    conn.close()
    
    if df.empty:
        return df

    # Parse timestamps robustly: try mixed-format fast path, fallback to per-item parsing
    try:
        df["ts"] = pd.to_datetime(df["ts"], utc=True, format="mixed")
    except Exception:
        df["ts"] = pd.to_datetime(df["ts"].astype(str), utc=True, errors="coerce")
    return df.sort_values("ts")


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_price_data(pair_y, pair_x, limit=MAX_POINTS):
    """Load raw price tick data"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    
    query = """
        SELECT ts, symbol, price, qty
        FROM ticks
        WHERE symbol IN (?, ?)
        ORDER BY ts DESC
        LIMIT ?
    """
    
    df = pd.read_sql(query, conn, params=(pair_y, pair_x, limit))
    conn.close()
    
    if df.empty:
        return df

    # Parse timestamps robustly: try mixed-format fast path, fallback to per-item parsing
    try:
        df["ts"] = pd.to_datetime(df["ts"], utc=True, format="mixed")
    except Exception:
        df["ts"] = pd.to_datetime(df["ts"].astype(str), utc=True, errors="coerce")

    return df.sort_values("ts")


@st.cache_data(ttl=60)
def get_all_pairs_latest(timeframe='1min'):
    """Get latest analytics for all pairs for a given timeframe"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)

    query = """
        SELECT pair_y, pair_x, timeframe, MAX(ts) as ts, 
               hedge_ratio, spread, zscore, correlation, is_stationary
        FROM analytics
        WHERE timeframe = ?
        GROUP BY pair_y, pair_x, timeframe
    """

    df = pd.read_sql(query, conn, params=(timeframe,))
    conn.close()

    return df


# =====================================================
# LOAD DATA
# =====================================================
df_analytics = load_analytics(pair_y, pair_x, selected_timeframe)

if df_analytics.empty:
    st.warning(f"⏳ Waiting for analytics data for {pair_y}/{pair_x} ({selected_timeframe})...")
    st.info("Make sure the ingestion and analytics engines are running. Data will appear within 60 seconds.")
    st.stop()

latest = df_analytics.iloc[-1]

# =====================================================
# KEY METRICS ROW
# =====================================================
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        "Hedge Ratio (β)",
        f"{latest['hedge_ratio']:.4f}",
        help="OLS regression coefficient: Y = α + β·X"
    )

with col2:
    spread_delta = df_analytics['spread'].diff().iloc[-1] if len(df_analytics) > 1 else 0
    st.metric(
        "Spread",
        f"{latest['spread']:.2f}",
        f"{spread_delta:+.2f}",
        help="Y - β·X"
    )

with col3:
    z_delta = df_analytics['zscore'].diff().iloc[-1] if len(df_analytics) > 1 else 0
    st.metric(
        "Z-Score",
        f"{latest['zscore']:.2f}",
        f"{z_delta:+.2f}",
        delta_color="inverse",
        help="(Spread - μ) / σ"
    )

with col4:
    if pd.notna(latest['correlation']):
        st.metric(
            "Correlation",
            f"{latest['correlation']:.3f}",
            help="Rolling correlation between Y and X"
        )
    else:
        st.metric("Correlation", "N/A")

with col5:
    if pd.notna(latest['is_stationary']):
        stationary_text = "✅ Yes" if latest['is_stationary'] == 1 else "❌ No"
        st.metric(
            "Stationary",
            stationary_text,
            help=f"ADF p-value: {latest['adf_pvalue']:.4f}" if pd.notna(latest['adf_pvalue']) else "ADF test"
        )
    else:
        st.metric("Stationary", "Testing...")

# =====================================================
# ALERT BANNER
# =====================================================
if abs(latest["zscore"]) >= z_alert:
    st.error(f"🚨 ALERT: |Z-score| = {abs(latest['zscore']):.2f} ≥ {z_alert} - Mean reversion opportunity detected!")
else:
    st.success(f"✅ Z-score within normal range (|z| < {z_alert})")

# =====================================================
# MAIN CHARTS
# =====================================================
st.divider()

# Create tabs for different views
tab1, tab2, tab3, tab4 = st.tabs(["📈 Price & Spread", "📊 Analytics", "🎯 Backtest", "📋 Data"])

with tab1:
    st.subheader(f"Price Charts - {pair_y} vs {pair_x}")
    
    # Load price data
    df_prices = load_price_data(pair_y, pair_x)
    
    if not df_prices.empty:
        # Create subplots
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=(f'{pair_y} and {pair_x} Prices', 'Spread'),
            row_heights=[0.5, 0.5]
        )
        
        # Y prices
        y_prices = df_prices[df_prices['symbol'] == pair_y]
        fig.add_trace(
            go.Scatter(
                x=y_prices['ts'],
                y=y_prices['price'],
                name=pair_y,
                line=dict(color='#667eea', width=2),
                hovertemplate='%{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # X prices
        x_prices = df_prices[df_prices['symbol'] == pair_x]
        fig.add_trace(
            go.Scatter(
                x=x_prices['ts'],
                y=x_prices['price'],
                name=pair_x,
                line=dict(color='#f093fb', width=2),
                yaxis='y2',
                hovertemplate='%{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Spread
        fig.add_trace(
            go.Scatter(
                x=df_analytics['ts'],
                y=df_analytics['spread'],
                name='Spread',
                line=dict(color='#4facfe', width=2),
                fill='tozeroy',
                hovertemplate='%{y:.2f}<extra></extra>'
            ),
            row=2, col=1
        )
        
        # Add zero line for spread
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=2, col=1)
        
        # Update layout
        fig.update_layout(
            height=700,
            hovermode='x unified',
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            template='plotly_dark'
        )
        
        fig.update_xaxes(title_text="Time", row=2, col=1)
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(title_text="Spread", row=2, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
    
    # Volume chart
    if show_volume and not df_prices.empty:
        st.subheader("Volume Analysis")
        
        fig_vol = go.Figure()
        
        for symbol in [pair_y, pair_x]:
            symbol_data = df_prices[df_prices['symbol'] == symbol]
            fig_vol.add_trace(go.Bar(
                x=symbol_data['ts'],
                y=symbol_data['qty'],
                name=f'{symbol} Volume',
                opacity=0.7
            ))
        
        fig_vol.update_layout(
            height=300,
            barmode='group',
            template='plotly_dark',
            xaxis_title="Time",
            yaxis_title="Volume"
        )
        
        st.plotly_chart(fig_vol, use_container_width=True)

with tab2:
    st.subheader("Statistical Analytics")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        # Z-Score over time
        fig_z = go.Figure()
        
        fig_z.add_trace(go.Scatter(
            x=df_analytics['ts'],
            y=df_analytics['zscore'],
            name='Z-Score',
            line=dict(color='#00f2fe', width=2),
            fill='tozeroy'
        ))
        
        # Add threshold lines
        fig_z.add_hline(y=z_alert, line_dash="dash", line_color="red", opacity=0.5)
        fig_z.add_hline(y=-z_alert, line_dash="dash", line_color="red", opacity=0.5)
        fig_z.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.3)
        
        fig_z.update_layout(
            title="Z-Score Over Time",
            height=400,
            template='plotly_dark',
            xaxis_title="Time",
            yaxis_title="Z-Score"
        )
        
        st.plotly_chart(fig_z, use_container_width=True)
    
    with col_b:
        # Correlation over time
        fig_corr = go.Figure()
        
        fig_corr.add_trace(go.Scatter(
            x=df_analytics['ts'],
            y=df_analytics['correlation'],
            name='Correlation',
            line=dict(color='#ffd89b', width=2),
            fill='tozeroy'
        ))
        
        fig_corr.update_layout(
            title="Rolling Correlation",
            height=400,
            template='plotly_dark',
            xaxis_title="Time",
            yaxis_title="Correlation"
        )
        
        st.plotly_chart(fig_corr, use_container_width=True)
    
    # Volatility comparison
    st.subheader("Volatility Analysis")
    
    fig_vol = go.Figure()
    
    fig_vol.add_trace(go.Scatter(
        x=df_analytics['ts'],
        y=df_analytics['y_volatility'],
        name=f'{pair_y} Volatility',
        line=dict(color='#667eea', width=2)
    ))
    
    fig_vol.add_trace(go.Scatter(
        x=df_analytics['ts'],
        y=df_analytics['x_volatility'],
        name=f'{pair_x} Volatility',
        line=dict(color='#f093fb', width=2)
    ))
    
    fig_vol.update_layout(
        height=350,
        template='plotly_dark',
        xaxis_title="Time",
        yaxis_title="Annualized Volatility"
    )
    
    st.plotly_chart(fig_vol, use_container_width=True)
    
    # Hedge ratio over time
    st.subheader("Hedge Ratio Evolution")
    
    fig_beta = go.Figure()
    
    fig_beta.add_trace(go.Scatter(
        x=df_analytics['ts'],
        y=df_analytics['hedge_ratio'],
        name='Hedge Ratio (β)',
        line=dict(color='#4facfe', width=2),
        mode='lines+markers',
        marker=dict(size=4)
    ))
    
    fig_beta.update_layout(
        height=300,
        template='plotly_dark',
        xaxis_title="Time",
        yaxis_title="Beta"
    )
    
    st.plotly_chart(fig_beta, use_container_width=True)

with tab3:
    if show_backtest:
        st.subheader("Mean Reversion Strategy Backtest")
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            entry_z = st.number_input("Entry Z-Score", value=2.0, min_value=1.0, max_value=4.0, step=0.1)
            exit_z = st.number_input("Exit Z-Score", value=0.5, min_value=0.0, max_value=2.0, step=0.1)
        
        # Run backtest
        backtest_result = simple_backtest(
            df_analytics['spread'],
            df_analytics['zscore'],
            entry_threshold=entry_z,
            exit_threshold=exit_z
        )
        
        if backtest_result and backtest_result['total_trades'] > 0:
            with col2:
                st.write("#### Backtest Results")
                
                metric_cols = st.columns(4)
                
                with metric_cols[0]:
                    st.metric("Total Trades", backtest_result['total_trades'])
                
                with metric_cols[1]:
                    st.metric("Total P&L", f"{backtest_result['total_pnl']:.2f}")
                
                with metric_cols[2]:
                    st.metric("Win Rate", f"{backtest_result['win_rate']:.1f}%")
                
                with metric_cols[3]:
                    st.metric("Avg P&L", f"{backtest_result['avg_pnl']:.2f}")
            
            # Trades table
            st.write("#### Trade History")
            trades_df = backtest_result['trades']
            trades_df['entry_time'] = pd.to_datetime(trades_df['entry_time'])
            trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
            
            # Pandas Styler may require matplotlib for background_gradient.
            styled = trades_df.style.format({
                'entry_price': '{:.2f}',
                'exit_price': '{:.2f}',
                'pnl': '{:.2f}',
                'return_pct': '{:.2f}%'
            })

            try:
                # Only apply gradient if matplotlib is available
                import matplotlib  # noqa: F401
                styled = styled.background_gradient(subset=['pnl'], cmap='RdYlGn')
            except Exception:
                # Fallback: skip gradient if matplotlib not installed
                pass

            st.dataframe(
                styled,
                use_container_width=True
            )
            
            # P&L chart
            fig_pnl = go.Figure()
            
            cumulative_pnl = trades_df['pnl'].cumsum()
            
            fig_pnl.add_trace(go.Scatter(
                x=trades_df['exit_time'],
                y=cumulative_pnl,
                name='Cumulative P&L',
                line=dict(color='#00f2fe', width=3),
                fill='tozeroy'
            ))
            
            fig_pnl.update_layout(
                title="Cumulative P&L",
                height=350,
                template='plotly_dark',
                xaxis_title="Time",
                yaxis_title="Cumulative P&L"
            )
            
            st.plotly_chart(fig_pnl, use_container_width=True)
        else:
            st.info("No trades generated with current parameters. Try adjusting entry/exit thresholds.")
    else:
        st.info("Enable 'Show Backtest' in sidebar to view strategy performance")

with tab4:
    st.subheader("Raw Analytics Data")
    
    # Display options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        n_rows = st.selectbox("Rows to display", [50, 100, 200, 500], index=1)
    
    with col2:
        sort_col = st.selectbox("Sort by", df_analytics.columns.tolist(), index=0)
    
    with col3:
        sort_order = st.radio("Order", ["Descending", "Ascending"], horizontal=True)
    
    # Prepare display dataframe
    display_df = df_analytics.tail(n_rows).sort_values(
        sort_col,
        ascending=(sort_order == "Ascending")
    )
    
    # Format numeric columns
    numeric_cols = display_df.select_dtypes(include=['float64', 'float32']).columns
    format_dict = {col: '{:.4f}' for col in numeric_cols}
    
    st.dataframe(
        display_df.style.format(format_dict),
        use_container_width=True,
        height=400
    )
    
    if show_stats_table:
        st.subheader("Summary Statistics")
        
        stats = df_analytics[['spread', 'zscore', 'hedge_ratio', 'correlation']].describe()
        st.dataframe(stats.T, use_container_width=True)

# =====================================================
# MULTI-PAIR COMPARISON
# =====================================================
st.divider()
st.subheader("📊 Multi-Pair Comparison")

df_all_pairs = get_all_pairs_latest(selected_timeframe)

if not df_all_pairs.empty:
    df_all_pairs['pair'] = df_all_pairs['pair_y'] + '/' + df_all_pairs['pair_x']
    
    # Create comparison chart
    fig_compare = go.Figure()
    
    fig_compare.add_trace(go.Bar(
        x=df_all_pairs['pair'],
        y=df_all_pairs['zscore'],
        name='Z-Score',
        marker_color=df_all_pairs['zscore'].apply(
            lambda x: '#ef4444' if abs(x) > z_alert else '#22c55e'
        ),
        text=df_all_pairs['zscore'].round(2),
        textposition='outside'
    ))
    
    fig_compare.add_hline(y=z_alert, line_dash="dash", line_color="red", opacity=0.5)
    fig_compare.add_hline(y=-z_alert, line_dash="dash", line_color="red", opacity=0.5)
    
    fig_compare.update_layout(
        height=300,
        template='plotly_dark',
        xaxis_title="Symbol Pair",
        yaxis_title="Z-Score",
        showlegend=False
    )
    
    st.plotly_chart(fig_compare, use_container_width=True)
else:
    st.info("No comparison data available yet for the selected timeframe.")
    st.caption(f"Try switching to '1s' or wait for the analytics engine to produce {selected_timeframe} bars.")

# =====================================================
# EXPORT SECTION
# =====================================================
st.sidebar.divider()

# Export analytics
csv_analytics = df_analytics.to_csv(index=False).encode("utf-8")
st.sidebar.download_button(
    label="⬇️ Download Analytics CSV",
    data=csv_analytics,
    file_name=f"analytics_{pair_y}_{pair_x}_{selected_timeframe}.csv",
    mime="text/csv"
)

# Export price data
df_prices = load_price_data(pair_y, pair_x)
if not df_prices.empty:
    csv_prices = df_prices.to_csv(index=False).encode("utf-8")
    st.sidebar.download_button(
        label="⬇️ Download Price Data CSV",
        data=csv_prices,
        file_name=f"prices_{pair_y}_{pair_x}.csv",
        mime="text/csv"
    )

# =====================================================
# FOOTER & AUTO REFRESH
# =====================================================
st.divider()
col1, col2, col3 = st.columns(3)

with col1:
    st.caption(f"Last Update: {latest['ts']}")

with col2:
    st.caption(f"Data Points: {len(df_analytics)}")

with col3:
    st.caption(f"Timeframe: {selected_timeframe}")

if auto_refresh:
    import time
    time.sleep(REFRESH_INTERVAL)
    st.rerun()