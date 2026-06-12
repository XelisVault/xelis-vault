#!/bin/bash
# Price Bot Launcher — runs in background, logs to price_bot.log
# Stop with: kill $(cat /tmp/xelis_price_bot.pid)

ORACLE_HASH="083f50b2eab5958ddacbb3c8e4e8943987d3bd337d7a56ae0763f6020734f8d6"
UPDATE_INTERVAL=100  # blocks (~8 min on testnet)

cd "$(dirname "$0")"
nohup python3 price_bot.py "$ORACLE_HASH" > price_bot.log 2>&1 &
echo $! > /tmp/xelis_price_bot.pid
echo "Price bot started (PID: $(cat /tmp/xelis_price_bot.pid))"
echo "Logs: price_bot.log"
echo "Stop: kill $(cat /tmp/xelis_price_bot.pid)"
