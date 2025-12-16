import sqlite3
import time
import os
import yaml
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from analytics.computations import (
    compute_hedge_ratio,
    compute_spread,
    compute_zscore,
    compute_adf_test,
    compute_rolling_correlation,
    compute_volatility,
    compute_returns_stats
)

# Load configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Setup logging
logging.basicConfig(
    level=getattr(logging, config['logging']['level']),
    format=config['logging']['format'],
    handlers=[
        logging.FileHandler(config['logging']['file']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = config['database']['path']
SYMBOL_PAIRS = config['symbols']['pairs']
TIMEFRAMES = config['analytics']['timeframes']
ROLLING_WINDOWS = config['analytics']['rolling_windows']
LOOKBACK_MINUTES = config['analytics']['lookback_minutes']
UPDATE_INTERVAL = config['analytics']['update_interval']
BATCH_SIZE = config['analytics']['batch_size']


def create_analytics_table():
    """Initialize analytics database schema"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
            ts TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            pair_y TEXT NOT NULL,
            pair_x TEXT NOT NULL,
            hedge_ratio REAL,
            alpha REAL,
            r_squared REAL,
            spread REAL,
            zscore REAL,
            correlation REAL,
            y_volatility REAL,
            x_volatility REAL,
            adf_statistic REAL,
            adf_pvalue REAL,
            is_stationary INTEGER,
            PRIMARY KEY (ts, timeframe, pair_y, pair_x)
        )
    """)
    
    # Create index for faster queries
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_analytics_tf_pair 
        ON analytics(timeframe, pair_y, pair_x, ts DESC)
    """)
    
    # Table for backtest results
    cur.execute("""
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair_y TEXT NOT NULL,
            pair_x TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            entry_price REAL,
            exit_price REAL,
            position TEXT,
            pnl REAL,
            return_pct REAL
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Analytics database schema initialized")


def load_recent_ticks(pair_y, pair_x, lookback_minutes):
    """Load recent tick data for a symbol pair"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    
    since = (datetime.utcnow() - timedelta(minutes=lookback_minutes)).isoformat()
    
    query = """
        SELECT ts, symbol, price, qty
        FROM ticks
        WHERE symbol IN (?, ?) AND ts >= ?
        ORDER BY ts ASC
    """
    
    df = pd.read_sql(query, conn, params=(pair_y, pair_x, since))
    conn.close()
    
    if df.empty:
        return df

    # Parse timestamps robustly: try mixed-format fast path, fallback to per-item parsing
    try:
        df["ts"] = pd.to_datetime(df["ts"], utc=True, format="mixed")
    except Exception:
        df["ts"] = pd.to_datetime(df["ts"].astype(str), utc=True, errors="coerce")
    return df

def resample_prices(df, timeframe="1s"):
    """
    Resample tick data to specified timeframe
    Returns DataFrame with columns: ts, symbol, price, volume
    """
    if df.empty:
        return pd.DataFrame(columns=["ts", "symbol", "price", "volume"])
    
    df = df.copy()
    df = df.set_index("ts")
    
    # Resample for each symbol
    resampled_list = []
    
    for symbol in df['symbol'].unique():
        symbol_df = df[df['symbol'] == symbol]
        
        # Price: last value in period
        price_bars = symbol_df['price'].resample(timeframe).last()
        
        # Volume: sum in period
        volume_bars = symbol_df['qty'].resample(timeframe).sum()
        
        # Combine
        bars = pd.DataFrame({
            'ts': price_bars.index,
            'symbol': symbol,
            'price': price_bars.values,
            'volume': volume_bars.values
        })
        
        resampled_list.append(bars)
    
    if not resampled_list:
        return pd.DataFrame(columns=["ts", "symbol", "price", "volume"])
    
    result = pd.concat(resampled_list, ignore_index=True)
    result = result.dropna()
    
    return result


def process_pair_analytics(pair_y, pair_x, timeframe, df_ticks):
    """
    Process all analytics for a single symbol pair and timeframe
    Returns dict of analytics or None if insufficient data
    """
    # Resample to timeframe
    bars = resample_prices(df_ticks, timeframe)
    
    if bars.empty:
        return None
    
    # Split into Y and X series
    y_bars = bars[bars["symbol"] == pair_y].set_index("ts").sort_index()
    x_bars = bars[bars["symbol"] == pair_x].set_index("ts").sort_index()
    
    # Require fewer bars for higher timeframes to allow quicker initial analytics
    min_bars_map = {
        '1s': 30,
        '1min': 10,
        '5min': 6
    }

    required_bars = min_bars_map.get(timeframe, 30)

    if len(y_bars) < required_bars or len(x_bars) < required_bars:
        return None
    
    # Align timestamps
    y_price = y_bars['price']
    x_price = x_bars['price']
    y_volume = y_bars['volume']
    x_volume = x_bars['volume']
    
    # Compute hedge ratio
    hedge_result = compute_hedge_ratio(y_price, x_price, method='ols')
    
    if hedge_result is None:
        return None
    
    beta = hedge_result['beta']
    alpha = hedge_result['alpha']
    r_squared = hedge_result['r_squared']
    
    # Align data for spread calculation
    aligned = pd.concat([y_price, x_price], axis=1).dropna()
    aligned.columns = ['y', 'x']
    
    if len(aligned) < 30:
        return None
    
    # Compute spread
    aligned['spread'] = compute_spread(aligned['y'], aligned['x'], beta)
    
    # Compute rolling windows but cap them to available data length so we can
    # produce analytics with fewer bars during startup (may be approximate)
    z_window = min(ROLLING_WINDOWS.get('zscore', 30), max(3, len(aligned)))
    aligned['zscore'] = compute_zscore(aligned['spread'], z_window)

    corr_window = min(ROLLING_WINDOWS.get('correlation', 60), max(3, len(aligned)))
    aligned['correlation'] = compute_rolling_correlation(
        aligned['y'], aligned['x'], corr_window
    )

    vol_window = min(ROLLING_WINDOWS.get('volatility', 20), max(3, len(aligned)))
    y_vol = compute_volatility(aligned['y'], vol_window)
    x_vol = compute_volatility(aligned['x'], vol_window)
    
    # ADF test on spread
    adf_result = compute_adf_test(aligned['spread'])
    
    # Get latest values
    aligned = aligned.dropna()
    
    if aligned.empty:
        return None
    
    latest = aligned.iloc[-1]
    latest_y_vol = y_vol.iloc[-1] if not y_vol.empty else None
    latest_x_vol = x_vol.iloc[-1] if not x_vol.empty else None
    
    result = {
        'ts': latest.name.isoformat(),
        'timeframe': timeframe,
        'pair_y': pair_y,
        'pair_x': pair_x,
        'hedge_ratio': float(beta),
        'alpha': float(alpha),
        'r_squared': float(r_squared) if r_squared else None,
        'spread': float(latest['spread']),
        'zscore': float(latest['zscore']),
        'correlation': float(latest['correlation']) if pd.notna(latest['correlation']) else None,
        'y_volatility': float(latest_y_vol) if pd.notna(latest_y_vol) else None,
        'x_volatility': float(latest_x_vol) if pd.notna(latest_x_vol) else None,
        'adf_statistic': float(adf_result['adf_statistic']) if adf_result else None,
        'adf_pvalue': float(adf_result['p_value']) if adf_result else None,
        'is_stationary': int(adf_result['is_stationary']) if adf_result else None
    }
    
    return result


def batch_write_analytics(analytics_list):
    """Write multiple analytics records to database in one transaction"""
    if not analytics_list:
        return
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cur = conn.cursor()
    
    for analytics in analytics_list:
        cur.execute("""
            INSERT OR REPLACE INTO analytics VALUES 
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            analytics['ts'],
            analytics['timeframe'],
            analytics['pair_y'],
            analytics['pair_x'],
            analytics['hedge_ratio'],
            analytics['alpha'],
            analytics['r_squared'],
            analytics['spread'],
            analytics['zscore'],
            analytics['correlation'],
            analytics['y_volatility'],
            analytics['x_volatility'],
            analytics['adf_statistic'],
            analytics['adf_pvalue'],
            analytics['is_stationary']
        ))
    
    conn.commit()
    conn.close()
    
    logger.info(f"Wrote {len(analytics_list)} analytics records")


def analytics_loop():
    """Main analytics processing loop"""
    create_analytics_table()
    logger.info("Analytics engine started")
    
    iteration = 0
    
    while True:
        try:
            iteration += 1
            analytics_batch = []
            
            # Process each symbol pair
            for pair_y, pair_x in SYMBOL_PAIRS:
                # Load recent ticks
                df_ticks = load_recent_ticks(pair_y, pair_x, LOOKBACK_MINUTES)
                
                if df_ticks.empty:
                    logger.debug(f"No ticks for {pair_y}/{pair_x}")
                    continue
                
                # Process each timeframe
                for timeframe in TIMEFRAMES:
                    analytics = process_pair_analytics(
                        pair_y, pair_x, timeframe, df_ticks
                    )
                    
                    if analytics:
                        analytics_batch.append(analytics)
                        
                        # Safely format correlation (avoid invalid format specifier in f-string)
                        corr_val = analytics.get('correlation')
                        try:
                            corr_str = f"{corr_val:.3f}" if pd.notna(corr_val) else "N/A"
                        except Exception:
                            corr_str = "N/A"

                        logger.info(
                            f"{pair_y}/{pair_x} [{timeframe}] | "
                            f"beta={analytics['hedge_ratio']:.4f} | "
                            f"spread={analytics['spread']:.2f} | "
                            f"z={analytics['zscore']:.2f} | "
                            f"corr={corr_str}"
                        )
            
            # Batch write to database
            if analytics_batch:
                batch_write_analytics(analytics_batch)
            
            # Log status every 10 iterations
            if iteration % 10 == 0:
                logger.info(f"Completed iteration #{iteration}, processed {len(analytics_batch)} analytics")
            
            time.sleep(UPDATE_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("Analytics engine stopped by user")
            break
        
        except Exception as e:
            logger.error(f"Analytics error: {e}", exc_info=True)
            time.sleep(2)


if __name__ == "__main__":
    analytics_loop()