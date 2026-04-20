#!/bin/bash
# D20 VPS Backup — SQLite backup with retention
set -e

BACKUP_DIR="/app/data/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="d20_${DATE}.db"

echo "=== D20 Backup ==="
echo "Backing up SQLite database..."

docker exec d20-rules-server sh -c "mkdir -p $BACKUP_DIR && sqlite3 /app/data/d20.db ".backup $BACKUP_DIR/$BACKUP_FILE""

# Copy backup out of container
docker cp "d20-rules-server:$BACKUP_DIR/$BACKUP_FILE" "./backups/$BACKUP_FILE" 2>/dev/null || echo "Backup created in container at $BACKUP_DIR/$BACKUP_FILE"

# Retain last 7 backups
docker exec d20-rules-server sh -c "ls -t $BACKUP_DIR/d20_*.db 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null || true"

echo "Backup complete: $BACKUP_FILE"
