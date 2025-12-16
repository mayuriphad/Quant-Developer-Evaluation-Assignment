#!/bin/bash
# Gemscap Statistical Arbitrage System Startup Script

echo "🚀 Starting Gemscap Statistical Arbitrage System..."
echo ""

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p storage logs
echo "✓ Directories created"
echo ""

# Start WebSocket ingestion in background
echo "📡 Starting WebSocket ingestion..."
python -m ingestion.ws_ingest > logs/ingestion.log 2>&1 &
INGEST_PID=$!
echo "✓ Ingestion started (PID: $INGEST_PID)"
echo ""

# Wait for initial data collection
echo "⏳ Waiting 5 seconds for initial data..."
sleep 5
echo ""

# Start analytics engine in background
echo "📊 Starting analytics engine..."
python -m analytics.engine > logs/analytics.log 2>&1 &
ANALYTICS_PID=$!
echo "✓ Analytics started (PID: $ANALYTICS_PID)"
echo ""

# Wait for analytics to initialize
echo "⏳ Waiting 3 seconds for analytics..."
sleep 3
echo ""

# Start API server in background
echo "🌐 Starting API server..."
python -m api.server > logs/api.log 2>&1 &
API_PID=$!
echo "✓ API server started (PID: $API_PID)"
echo ""

# Wait for API to start
echo "⏳ Waiting 2 seconds for API..."
sleep 2
echo ""

# Display information
echo "================================"
echo "✅ All services started!"
echo "================================"
echo ""
echo "📊 Dashboard: http://localhost:8501"
echo "🌐 API: http://localhost:8000"
echo "📝 Logs: ./logs/"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Start Streamlit dashboard (this runs in foreground)
echo "📈 Starting dashboard..."
streamlit run dashboard/app.py

# Cleanup function when script exits
cleanup() {
    echo ""
    echo "🛑 Stopping all services..."
    kill $INGEST_PID 2>/dev/null
    kill $ANALYTICS_PID 2>/dev/null
    kill $API_PID 2>/dev/null
    echo "✓ All services stopped"
    exit 0
}

# Set trap to run cleanup on exit
trap cleanup EXIT INT TERM