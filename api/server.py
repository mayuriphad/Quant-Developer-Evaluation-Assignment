from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import pandas as pd
import yaml
import uvicorn
from datetime import datetime, timedelta
from typing import Optional, List
import logging

# Load configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Setup logging
logging.basicConfig(
    level=getattr(logging, config['logging']['level']),
    format=config['logging']['format']
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Gemscap Statistical Arbitrage API",
    description="REST API for cryptocurrency pairs trading analytics",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = config['database']['path']
SYMBOL_PAIRS = config['symbols']['pairs']
TIMEFRAMES = config['analytics']['timeframes']


def get_db_connection():
    """Create database connection"""
    return sqlite3.connect(DB_PATH, timeout=30.0)  # ← ADD timeout=30.0


@app.get("/")
def read_root():
    """API root endpoint"""
    return {
        "message": "Gemscap Statistical Arbitrage API",
        "version": "1.0.0",
        "endpoints": {
            "/health": "System health check",
            "/pairs": "List available symbol pairs",
            "/analytics/{pair_y}/{pair_x}": "Get analytics for a pair",
            "/latest/{pair_y}/{pair_x}": "Get latest analytics",
            "/spread/{pair_y}/{pair_x}": "Get spread data",
            "/export/{pair_y}/{pair_x}": "Export analytics as CSV"
        }
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if tables exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        
        # Check recent data
        cur.execute("SELECT COUNT(*) FROM ticks WHERE ts > datetime('now', '-5 minutes')")
        recent_ticks = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM analytics WHERE ts > datetime('now', '-5 minutes')")
        recent_analytics = cur.fetchone()[0]
        
        conn.close()
        
        status = "healthy" if recent_ticks > 0 and recent_analytics > 0 else "degraded"
        
        return {
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "database": {
                "connected": True,
                "tables": tables,
                "recent_ticks": recent_ticks,
                "recent_analytics": recent_analytics
            }
        }
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@app.get("/pairs")
def list_pairs():
    """List all available symbol pairs"""
    pairs = [{"pair_y": y, "pair_x": x, "display": f"{y}/{x}"} for y, x in SYMBOL_PAIRS]
    
    return {
        "pairs": pairs,
        "total": len(pairs),
        "timeframes": TIMEFRAMES
    }


@app.get("/analytics/{pair_y}/{pair_x}")
def get_analytics(
    pair_y: str,
    pair_x: str,
    timeframe: Optional[str] = Query("1min", description="Timeframe (1s, 1min, 5min)"),
    limit: Optional[int] = Query(500, description="Number of records to return"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)")
):
    """Get analytics data for a symbol pair"""
    
    if (pair_y, pair_x) not in SYMBOL_PAIRS:
        raise HTTPException(status_code=404, detail="Symbol pair not found")
    
    if timeframe not in TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe. Choose from: {TIMEFRAMES}")
    
    conn = get_db_connection()
    
    # Build query
    query = """
        SELECT *
        FROM analytics
        WHERE pair_y = ? AND pair_x = ? AND timeframe = ?
    """
    params = [pair_y, pair_x, timeframe]
    
    if start_time:
        query += " AND ts >= ?"
        params.append(start_time)
    
    if end_time:
        query += " AND ts <= ?"
        params.append(end_time)
    
    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    
    if df.empty:
        return {
            "pair_y": pair_y,
            "pair_x": pair_x,
            "timeframe": timeframe,
            "data": [],
            "count": 0
        }
    
    # Convert to records
    records = df.to_dict('records')
    
    return {
        "pair_y": pair_y,
        "pair_x": pair_x,
        "timeframe": timeframe,
        "data": records,
        "count": len(records),
        "latest": records[0] if records else None
    }


@app.get("/latest/{pair_y}/{pair_x}")
def get_latest(pair_y: str, pair_x: str):
    """Get latest analytics for all timeframes"""
    
    if (pair_y, pair_x) not in SYMBOL_PAIRS:
        raise HTTPException(status_code=404, detail="Symbol pair not found")
    
    conn = get_db_connection()
    
    query = """
        SELECT *
        FROM analytics
        WHERE pair_y = ? AND pair_x = ?
        AND ts IN (
            SELECT MAX(ts)
            FROM analytics
            WHERE pair_y = ? AND pair_x = ?
            GROUP BY timeframe
        )
    """
    
    df = pd.read_sql(query, conn, params=(pair_y, pair_x, pair_y, pair_x))
    conn.close()
    
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found")
    
    # Group by timeframe
    result = {}
    for _, row in df.iterrows():
        result[row['timeframe']] = row.to_dict()
    
    return {
        "pair_y": pair_y,
        "pair_x": pair_x,
        "latest_by_timeframe": result
    }


@app.get("/spread/{pair_y}/{pair_x}")
def get_spread(
    pair_y: str,
    pair_x: str,
    timeframe: Optional[str] = Query("1min", description="Timeframe"),
    limit: Optional[int] = Query(500, description="Number of points")
):
    """Get spread and z-score data"""
    
    if (pair_y, pair_x) not in SYMBOL_PAIRS:
        raise HTTPException(status_code=404, detail="Symbol pair not found")
    
    conn = get_db_connection()
    
    query = """
        SELECT ts, spread, zscore, hedge_ratio
        FROM analytics
        WHERE pair_y = ? AND pair_x = ? AND timeframe = ?
        ORDER BY ts DESC
        LIMIT ?
    """
    
    df = pd.read_sql(query, conn, params=(pair_y, pair_x, timeframe, limit))
    conn.close()
    
    if df.empty:
        return {"data": [], "count": 0}
    
    df = df.sort_values('ts')
    
    return {
        "pair_y": pair_y,
        "pair_x": pair_x,
        "timeframe": timeframe,
        "data": df.to_dict('records'),
        "count": len(df),
        "stats": {
            "spread_mean": float(df['spread'].mean()),
            "spread_std": float(df['spread'].std()),
            "zscore_mean": float(df['zscore'].mean()),
            "zscore_std": float(df['zscore'].std()),
            "latest_hedge_ratio": float(df['hedge_ratio'].iloc[-1])
        }
    }


@app.get("/correlation")
def get_all_correlations():
    """Get latest correlation for all pairs"""
    
    conn = get_db_connection()
    
    query = """
        SELECT pair_y, pair_x, timeframe, ts, correlation, zscore, is_stationary
        FROM analytics
        WHERE timeframe = '1min'
        AND ts IN (
            SELECT MAX(ts)
            FROM analytics
            WHERE timeframe = '1min'
            GROUP BY pair_y, pair_x
        )
    """
    
    df = pd.read_sql(query, conn)
    conn.close()
    
    if df.empty:
        return {"pairs": [], "count": 0}
    
    return {
        "pairs": df.to_dict('records'),
        "count": len(df),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/export/{pair_y}/{pair_x}")
def export_data(
    pair_y: str,
    pair_x: str,
    timeframe: Optional[str] = Query("1min", description="Timeframe"),
    format: Optional[str] = Query("csv", description="Export format (csv or json)")
):
    """Export analytics data"""
    
    if (pair_y, pair_x) not in SYMBOL_PAIRS:
        raise HTTPException(status_code=404, detail="Symbol pair not found")
    
    conn = get_db_connection()
    
    query = """
        SELECT *
        FROM analytics
        WHERE pair_y = ? AND pair_x = ? AND timeframe = ?
        ORDER BY ts ASC
    """
    
    df = pd.read_sql(query, conn, params=(pair_y, pair_x, timeframe))
    conn.close()
    
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found")
    
    if format == "csv":
        filename = f"analytics_{pair_y}_{pair_x}_{timeframe}.csv"
        df.to_csv(filename, index=False)
        return FileResponse(filename, media_type="text/csv", filename=filename)
    
    elif format == "json":
        return {
            "pair_y": pair_y,
            "pair_x": pair_x,
            "timeframe": timeframe,
            "data": df.to_dict('records'),
            "count": len(df)
        }
    
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Use 'csv' or 'json'")


@app.get("/stats/{pair_y}/{pair_x}")
def get_statistics(pair_y: str, pair_x: str):
    """Get statistical summary for a pair"""
    
    if (pair_y, pair_x) not in SYMBOL_PAIRS:
        raise HTTPException(status_code=404, detail="Symbol pair not found")
    
    conn = get_db_connection()
    
    # Get data for last 24 hours
    since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    
    query = """
        SELECT *
        FROM analytics
        WHERE pair_y = ? AND pair_x = ? AND timeframe = '1min' AND ts >= ?
    """
    
    df = pd.read_sql(query, conn, params=(pair_y, pair_x, since))
    conn.close()
    
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found")
    
    stats = {
        "pair": f"{pair_y}/{pair_x}",
        "period": "24 hours",
        "spread": {
            "mean": float(df['spread'].mean()),
            "std": float(df['spread'].std()),
            "min": float(df['spread'].min()),
            "max": float(df['spread'].max()),
            "current": float(df['spread'].iloc[-1])
        },
        "zscore": {
            "mean": float(df['zscore'].mean()),
            "std": float(df['zscore'].std()),
            "min": float(df['zscore'].min()),
            "max": float(df['zscore'].max()),
            "current": float(df['zscore'].iloc[-1])
        },
        "hedge_ratio": {
            "mean": float(df['hedge_ratio'].mean()),
            "std": float(df['hedge_ratio'].std()),
            "current": float(df['hedge_ratio'].iloc[-1])
        },
        "correlation": {
            "mean": float(df['correlation'].mean()),
            "current": float(df['correlation'].iloc[-1])
        },
        "data_points": len(df)
    }
    
    return stats


if __name__ == "__main__":
    host = config['api']['host']
    port = config['api']['port']
    
    logger.info(f"Starting API server on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )