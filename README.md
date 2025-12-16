# Gemscap Statistical Arbitrage System

A real-time cryptocurrency pairs trading analytics platform built for quantitative traders and researchers.

## 🎯 Overview

This system ingests live tick data from Binance WebSocket, performs sophisticated statistical analysis including hedge ratio calculation, spread analysis, z-score computation, and stationarity testing, then presents results through an interactive web dashboard.

## ✨ Features

### Core Analytics
- **Real-time Data Ingestion**: Live WebSocket connection to Binance for BTC, ETH, BNB, SOL pairs
- **Multi-Timeframe Analysis**: Simultaneous processing at 1s, 1min, and 5min intervals
- **Hedge Ratio Calculation**: OLS regression-based β estimation
- **Spread Analysis**: Computes Y - β·X for mean reversion trading
- **Z-Score Monitoring**: Rolling z-score calculation for entry/exit signals
- **Stationarity Testing**: ADF (Augmented Dickey-Fuller) test
- **Correlation Tracking**: Rolling correlation between asset pairs
- **Volatility Metrics**: Annualized volatility calculation
- **Volume Analysis**: Trading volume patterns

### Advanced Features
- **Mean Reversion Backtest**: Configurable entry/exit strategy with P&L tracking
- **Multi-Pair Comparison**: Visual comparison of z-scores across pairs
- **Custom Alerts**: Threshold-based notifications
- **Data Export**: CSV download for all analytics
- **RESTful API**: HTTP endpoints for programmatic access
- **Interactive Visualizations**: Zoom, pan, hover on all charts

## 🏗️ Architecture

```
┌─────────────────┐
│  Binance API    │  Live tick data
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ws_ingest.py   │  WebSocket → SQLite
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  market.db      │  Centralized storage
│  • ticks        │
│  • analytics    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  engine.py      │  Analytics processor
└────────┬────────┘
         │
         ▼
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌────────┐
│  API   │ │ Dash   │  Visualization layers
└────────┘ └────────┘
```

## 📁 Project Structure

```
statistical-arbitrage-system/
├── config.yaml              # Configuration file
├── requirements.txt         # Python dependencies
├── run_all.py              # One-command launcher
├── README.md               # This file
├── storage/
│   └── market.db           # SQLite database (auto-created)
├── logs/
│   └── app.log             # Application logs (auto-created)
├── ingestion/
│   ├── __init__.py
│   └── ws_ingest.py        # WebSocket data collector
├── analytics/
│   ├── __init__.py
│   ├── computations.py     # Statistical functions
│   └── engine.py           # Analytics processor
├── api/
│   ├── __init__.py
│   └── server.py           # FastAPI REST server
└── dashboard/
    ├── __init__.py
    └── app.py              # Streamlit dashboard
```

## 🚀 Quick Start

### Prerequisites
- Python 3.9 or higher
- pip package manager
- 2GB free disk space
- Internet connection for Binance WebSocket

### Installation

1. **Clone/Download the project**
   ```bash
   cd statistical-arbitrage-system
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Mac/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create required directories**
   ```bash
   mkdir storage logs
   ```

### Running the System

#### Option 1: One-Command Start (Recommended)
```bash
python run_all.py
```

**Note for Windows (PowerShell)**

```powershell
# Create and activate virtual environment (PowerShell)
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
venv\Scripts\Activate.ps1

# Run all services
python run_all.py
```

Note: `run_all.py` is cross-platform and replaces the previous `run.sh` launcher.

#### Option 2: Manual Start (4 separate terminals)

**Terminal 1 - Data Ingestion:**
```bash
python -m ingestion.ws_ingest
```

**Terminal 2 - Analytics Engine:**
```bash
# Wait 10 seconds after starting ingestion
python -m analytics.engine
```

**Terminal 3 - API Server (Optional):**
```bash
python -m api.server
```

**Terminal 4 - Dashboard:**
```bash
streamlit run dashboard/app.py
```

The dashboard will automatically open at **http://localhost:8501**

## 📊 Usage Guide

### Dashboard Overview

**Main Metrics Bar:**
- **Hedge Ratio (β)**: Current OLS regression coefficient
- **Spread**: Current Y - β·X value with trend
- **Z-Score**: Standardized spread with trend indicator
- **Correlation**: Rolling correlation coefficient
- **Stationarity**: ADF test result (Yes/No)

**Tabs:**
1. **Price & Spread**: Price charts for both assets and spread visualization
2. **Analytics**: Z-score, correlation, volatility, and hedge ratio evolution
3. **Backtest**: Mean reversion strategy simulation with P&L tracking
4. **Data**: Raw analytics table with export functionality

**Sidebar Controls:**
- Symbol pair selection (ETH/BTC, BNB/BTC, SOL/ETH)
- Timeframe selection (1s, 1min, 5min)
- Z-score alert threshold slider
- Display options toggles
- Auto-refresh control
- CSV export buttons

### API Endpoints

Base URL: `http://localhost:8000`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API information |
| `/health` | GET | System health check |
| `/pairs` | GET | List available pairs |
| `/analytics/{y}/{x}` | GET | Get analytics data |
| `/latest/{y}/{x}` | GET | Latest metrics all timeframes |
| `/spread/{y}/{x}` | GET | Spread time series |
| `/export/{y}/{x}` | GET | Export data (CSV/JSON) |
| `/stats/{y}/{x}` | GET | 24h statistical summary |

**Example:**
```bash
curl http://localhost:8000/latest/ETHUSDT/BTCUSDT
```

## ⚙️ Configuration

Edit `config.yaml` to customize:

```yaml
symbols:
  pairs:
    - [ETHUSDT, BTCUSDT]  # Add more pairs here

analytics:
  timeframes: ["1s", "1min", "5min"]
  rolling_windows:
    zscore: 30        # Z-score window size
    correlation: 60   # Correlation window
    volatility: 20    # Volatility window
  lookback_minutes: 60
  update_interval: 1.0

alerts:
  default_zscore_threshold: 2.0

dashboard:
  refresh_interval: 1
  max_display_points: 500
```

## 📈 Analytics Methodology

### Hedge Ratio (β)
Uses Ordinary Least Squares (OLS) regression:
```
Y = α + β·X + ε
```
Where β represents how many units of X to hold per unit of Y.

### Spread Calculation
```
Spread = Y - β·X
```
Creates a synthetic instrument that should be mean-reverting.

### Z-Score
```
Z = (Spread - μ) / σ
```
Standardized spread over a rolling window.
- |Z| > 2.0: Strong mean reversion signal
- |Z| → 0: Return to mean (exit signal)

### ADF Stationarity Test
Tests if the spread is stationary (suitable for mean reversion):
- **p-value < 0.05**: Spread is stationary ✓
- **p-value > 0.05**: Non-stationary (risky for pairs trading)

### Mean Reversion Strategy
```
Entry: |Z-score| > 2.0
Exit: |Z-score| < 0.5

Direction:
- Short spread when Z > 2 (expect reversion down)
- Long spread when Z < -2 (expect reversion up)

P&L = Position × (Exit_Spread - Entry_Spread)
```

## 🔍 Troubleshooting

### No data appearing in dashboard?
1. Check ingestion is running: Look for "Ingested X ticks" messages
2. Wait 60 seconds for initial data accumulation
3. Verify WebSocket connection in logs
4. Check database: `sqlite3 storage/market.db "SELECT COUNT(*) FROM ticks"`

### Analytics not updating?
1. Ensure analytics engine is running
2. Need 30+ data points for z-score calculation
3. Check `logs/app.log` for errors
4. Verify sufficient tick data exists

### Dashboard showing "Waiting for data"?
1. Analytics engine must run for at least 30 seconds
2. Select different timeframe (try '1s' first)
3. Check if analytics table has data:
   ```sql
   sqlite3 storage/market.db "SELECT COUNT(*) FROM analytics"
   ```

### Database locked errors?
All files already have `timeout=30.0` - this shouldn't occur. If it does, restart all components.

## 📊 Performance Notes

### Current Capacity (SQLite)
- **Tick throughput**: 100-500 ticks/second
- **Analytics latency**: 1-2 seconds
- **Dashboard refresh**: 1 second
- **Storage**: ~1MB per hour

### Scaling to Production

**For higher throughput (1000+ ticks/second):**

1. **Database**: Migrate to PostgreSQL or TimescaleDB
2. **Message Queue**: Add Redis or RabbitMQ between ingestion and analytics
3. **Distributed Processing**: Use Celery for parallel analytics
4. **Caching**: Add Redis for API responses
5. **Load Balancing**: Deploy multiple dashboard instances

## 🛠️ Technology Stack

- **Language**: Python 3.9+
- **Database**: SQLite (development), PostgreSQL-ready
- **Data Processing**: Pandas, NumPy
- **Analytics**: Statsmodels, SciPy
- **Visualization**: Streamlit, Plotly
- **API**: FastAPI, Uvicorn
- **WebSocket**: websockets, aiosqlite
- **Configuration**: PyYAML

## 🔐 Security Considerations

**Current Implementation:**
- Local development environment
- No authentication required
- Database on local filesystem

**Production Recommendations:**
1. Add JWT authentication to API
2. Use HTTPS/TLS for all connections
3. Implement rate limiting
4. Store sensitive config in environment variables
5. Add firewall rules to restrict access

## 📝 Component Details

### 1. WebSocket Ingestion (`ws_ingest.py`)
- **Purpose**: Collect live market data
- **Function**: Connects to Binance, saves ticks to database
- **Features**: Auto-reconnection, batch commits, error handling
- **Dependencies**: Independent (only needs config)

### 2. Analytics Engine (`engine.py`)
- **Purpose**: Process tick data into trading signals
- **Function**: Loads ticks, resamples, computes analytics, saves results
- **Features**: Multi-timeframe, multi-pair, batch processing
- **Dependencies**: Requires tick data from ingestion

### 3. Computations Library (`computations.py`)
- **Purpose**: Reusable statistical functions
- **Function**: Pure math calculations (no I/O)
- **Features**: OLS, ADF, z-score, correlation, backtest
- **Dependencies**: Only pandas, numpy, statsmodels

### 4. REST API (`server.py`)
- **Purpose**: Programmatic access to data
- **Function**: HTTP endpoints for analytics retrieval
- **Features**: 9 endpoints, CORS enabled, JSON/CSV export
- **Dependencies**: Reads from database

### 5. Dashboard (`app.py`)
- **Purpose**: Visual interface for traders
- **Function**: Interactive charts and analytics display
- **Features**: 4 tabs, auto-refresh, CSV export, backtesting
- **Dependencies**: Reads from database, imports computations

## 🎓 Use Cases

### For Traders
- Monitor real-time z-scores for entry signals
- Backtest mean reversion strategies
- Track correlation breakdowns
- Export data for custom analysis

### For Researchers
- Study cryptocurrency pair relationships
- Test statistical arbitrage hypotheses
- Analyze market microstructure
- Generate datasets for ML models

### For Developers
- API access for algorithmic trading
- Integrate with existing trading systems
- Extend with custom analytics
- Build on modular architecture

## 📚 References

**Statistical Arbitrage:**
- "Algorithmic Trading" by Ernest Chan
- "Pairs Trading: Quantitative Methods and Analysis" by Vidyamurthy

**Technical Documentation:**
- Statsmodels: https://www.statsmodels.org
- Streamlit: https://docs.streamlit.io
- FastAPI: https://fastapi.tiangolo.com
- Binance API: https://binance-docs.github.io/apidocs/

## 👩‍💻 Author

- **Name:** Mayuri Phad
- **Email:** mayuri.22320110@viit.ac.in
- **GitHub:** https://github.com/mayuriphad
- **LinkedIn:** https://www.linkedin.com/in/mayuriphad/


## 🤝 Contributing

This is an assignment project, but feedback is welcome:
1. Open an issue for bugs or feature requests
2. Fork and submit pull requests
3. Share your enhancements

## 📄 License

MIT License - Free to use, modify, and distribute

## 👥 Author

Created for Gemscap Quant Developer Evaluation Assignment

## 🙏 Acknowledgments

- Binance for WebSocket API access
- Anthropic Claude for development assistance
- Open source community for excellent libraries
- Gemscap for the challenging assignment opportunity

---

**Version**: 1.0.0  
**Last Updated**: December 2025  
**Status**: Production-ready prototype

**Questions?** Check the troubleshooting section or open an issue.