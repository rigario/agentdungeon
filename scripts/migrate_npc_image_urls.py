"""
Migration: Populate image_url for all NPCs
Fixes task b2f04ba2 — NPC cards show emoji instead of portraits
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'd20.db')

NPC_IMAGE_MAP = {
    "npc-aldric": "/static/pixel-art/npc-aldric.png",
    "npc-ser-maren": "/static/pixel-art/npc-ser-maren.png",
    "npc-marta": "/static/pixel-art/npc-marta.png",
    "npc-kira": "/static/pixel-art/npc-kira.png",
    "npc-green-woman": "/static/pixel-art/npc-green-woman.png",
    "npc-del-ghost": "/static/pixel-art/npc-dels-spirit.png",
    "npc-torren": "/static/pixel-art/npc-torren.png",
    "npc-brother-kol": "/static/pixel-art/npc-brother-kol.png",
    "npc-sister-drenna": "/static/pixel-art/npc-sister-drenna.png",
}

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

for npc_id, image_url in NPC_IMAGE_MAP.items():
    cursor.execute(
        "UPDATE npcs SET image_url = ? WHERE id = ? AND (image_url IS NULL OR image_url = '')",
        (image_url, npc_id)
    )

conn.commit()

# Verify
cursor.execute("SELECT id, COALESCE(image_url, 'NULL') FROM npcs")
rows = cursor.fetchall()
print("NPC image_url AFTER:")
for row in rows:
    print(f"  {row[0]}: {row[1]}")

conn.close()
