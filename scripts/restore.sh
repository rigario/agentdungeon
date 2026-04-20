#!/bin/bash
# D20 VPS Restore — restore SQLite from backup
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_filename>"
    echo "Example: $0 d20_20260420_143000.db"
    exit 1
fi

BACKUP_FILE="$1"
BACKUP_DIR="/app/data/backups"

echo "=== D20 Restore ==="
echo "Restoring from: $BACKUP_FILE"

# Stop rules server
echo "Stopping rules server..."
docker compose stop d20-rules-server

# Restore
docker exec d20-rules-server sh -c "cp $BACKUP_DIR/$BACKUP_FILE /app/data/d20.db"

# Restart
echo "Starting rules server..."
docker compose start d20-rules-server

echo "Restore complete"
