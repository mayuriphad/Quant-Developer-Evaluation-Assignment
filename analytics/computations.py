import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from scipy import stats


def compute_hedge_ratio(y, x, method='ols'):
    """
    Compute hedge ratio using specified regression method
    
    Args:
        y: Dependent variable (pandas Series)
        x: Independent variable (pandas Series)
        method: 'ols', 'huber', or 'theilsen'
    
    Returns:
        dict with beta, alpha, r_squared, residuals
    """
    if len(y) < 10 or len(x) < 10:
        return None
    
    df = pd.concat([y, x], axis=1).dropna()
    if len(df) < 10:
        return None
    
    df.columns = ['y', 'x']
    
    X = sm.add_constant(df['x'])
    
    if method == 'ols':
        model = sm.OLS(df['y'], X).fit()
    elif method == 'huber':
        model = sm.RLM(df['y'], X, M=sm.robust.norms.HuberT()).fit()
    elif method == 'theilsen':
        slope, intercept, _, _, _ = stats.theilslopes(df['y'], df['x'])
        return {
            'beta': slope,
            'alpha': intercept,
            'r_squared': None,
            'residuals': df['y'] - (slope * df['x'] + intercept)
        }
    else:
        raise ValueError(f"Unknown method: {method}")
    
    return {
        'beta': model.params['x'],
        'alpha': model.params['const'],
        'r_squared': model.rsquared if hasattr(model, 'rsquared') else None,
        'residuals': model.resid
    }


def compute_spread(y, x, beta):
    """Compute spread: Y - β*X"""
    return y - beta * x


def compute_zscore(series, window):
    """Compute rolling z-score"""
    if len(series) < window:
        return pd.Series(index=series.index, dtype=float)
    
    mean = series.rolling(window).mean()
    std = series.rolling(window).std()
    
    # Avoid division by zero
    std = std.replace(0, np.nan)
    
    return (series - mean) / std


def compute_adf_test(series, maxlag=None):
    """
    Augmented Dickey-Fuller test for stationarity
    
    Returns:
        dict with test results
    """
    if len(series.dropna()) < 50:
        return None
    
    try:
        result = adfuller(series.dropna(), maxlag=maxlag, autolag='AIC')
        
        return {
            'adf_statistic': result[0],
            'p_value': result[1],
            'used_lag': result[2],
            'n_obs': result[3],
            'critical_values': result[4],
            'is_stationary': result[1] < 0.05
        }
    except Exception as e:
        return None


def compute_rolling_correlation(y, x, window):
    """Compute rolling correlation between two series"""
    if len(y) < window or len(x) < window:
        return pd.Series(index=y.index, dtype=float)
    
    return y.rolling(window).corr(x)


def compute_volatility(prices, window=20):
    """Compute rolling volatility (annualized)"""
    if len(prices) < window:
        return pd.Series(index=prices.index, dtype=float)
    
    returns = prices.pct_change()
    volatility = returns.rolling(window).std() * np.sqrt(252 * 24 * 60)
    
    return volatility


def compute_returns_stats(prices):
    """Compute basic return statistics"""
    returns = prices.pct_change().dropna()
    
    if len(returns) == 0:
        return None
    
    return {
        'mean_return': returns.mean(),
        'std_return': returns.std(),
        'sharpe_ratio': returns.mean() / returns.std() if returns.std() > 0 else 0,
        'skewness': returns.skew(),
        'kurtosis': returns.kurtosis(),
        'min_return': returns.min(),
        'max_return': returns.max()
    }


def simple_backtest(spread, zscore, entry_threshold=2.0, exit_threshold=0.5):
    """
    Simple mean reversion backtest
    
    Strategy:
    - Enter when |z| > entry_threshold
    - Exit when |z| < exit_threshold
    - Short spread when z > entry_threshold
    - Long spread when z < -entry_threshold
    """
    df = pd.DataFrame({
        'spread': spread,
        'zscore': zscore
    }).dropna()
    
    if len(df) < 10:
        return None
    
    position = 0
    trades = []
    entry_price = 0
    entry_time = None
    
    for idx, row in df.iterrows():
        z = row['zscore']
        s = row['spread']
        
        # Entry logic
        if position == 0:
            if z > entry_threshold:
                position = -1
                entry_price = s
                entry_time = idx
            elif z < -entry_threshold:
                position = 1
                entry_price = s
                entry_time = idx
        
        # Exit logic
        elif position != 0 and abs(z) < exit_threshold:
            pnl = position * (s - entry_price)
            
            trades.append({
                'entry_time': entry_time,
                'exit_time': idx,
                'entry_price': entry_price,
                'exit_price': s,
                'position': 'SHORT' if position == -1 else 'LONG',
                'pnl': pnl,
                'return_pct': (pnl / abs(entry_price)) * 100
            })
            
            position = 0
    
    if not trades:
        return {
            'total_trades': 0,
            'total_pnl': 0,
            'win_rate': 0,
            'avg_pnl': 0,
            'trades': []
        }
    
    trades_df = pd.DataFrame(trades)
    
    return {
        'total_trades': len(trades_df),
        'total_pnl': trades_df['pnl'].sum(),
        'win_rate': (trades_df['pnl'] > 0).mean() * 100,
        'avg_pnl': trades_df['pnl'].mean(),
        'avg_return_pct': trades_df['return_pct'].mean(),
        'max_pnl': trades_df['pnl'].max(),
        'min_pnl': trades_df['pnl'].min(),
        'trades': trades_df
    }