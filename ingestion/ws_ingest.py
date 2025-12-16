import asyncio
import json
import os
import yaml
import aiosqlite
import websockets
from datetime import datetime
import logging

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
BINANCE_WS = config['websocket']['url']
PING_INTERVAL = config['websocket']['ping_interval']
RECONNECT_DELAY = config['websocket']['reconnect_delay']

# Build stream string from config
SYMBOLS = config['symbols']['pairs']
streams = "/".join([f"{pair[0].lower()}@trade/{pair[1].lower()}@trade" for pair in SYMBOLS])


async def create_db():
    """Initialize database schema"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                qty REAL NOT NULL,
                is_buyer_maker INTEGER
            )
        """)
        
        # Create index for faster queries
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticks_ts_symbol 
            ON ticks(ts, symbol)
        """)
        
        await db.commit()
        logger.info("Database schema initialized")


async def ingest_once():
    """Single WebSocket connection lifecycle"""
    uri = f"{BINANCE_WS}/{streams}"
    logger.info(f"Connecting to {uri}")

    async with websockets.connect(
        uri,
        ping_interval=PING_INTERVAL,
        ping_timeout=PING_INTERVAL
    ) as ws:
        async with aiosqlite.connect(DB_PATH) as db:
            msg_count = 0
            
            while True:
                msg = await ws.recv()
                data = json.loads(msg)

                ts = datetime.utcfromtimestamp(data["T"] / 1000).isoformat()
                symbol = data["s"]
                price = float(data["p"])
                qty = float(data["q"])
                is_buyer_maker = int(data["m"])

                await db.execute(
                    "INSERT INTO ticks VALUES (?, ?, ?, ?, ?)",
                    (ts, symbol, price, qty, is_buyer_maker)
                )
                
                msg_count += 1
                
                # Commit in batches
                if msg_count % 100 == 0:
                    await db.commit()
                    logger.debug(f"Committed {msg_count} ticks")

                if msg_count % 1000 == 0:
                    logger.info(f"Ingested {msg_count} ticks - Latest: {symbol} @ {price}")


async def ingest_forever():
    """Main ingestion loop with auto-reconnection"""
    await create_db()
    
    attempt = 0
    while True:
        try:
            attempt += 1
            logger.info(f"Ingestion attempt #{attempt}")
            await ingest_once()

        except websockets.ConnectionClosed as e:
            logger.warning(f"WebSocket closed (code: {e.code}). Reconnecting in {RECONNECT_DELAY}s...")
            await asyncio.sleep(RECONNECT_DELAY)

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    try:
        asyncio.run(ingest_forever())
    except KeyboardInterrupt:
        logger.info("Ingestion stopped by user")