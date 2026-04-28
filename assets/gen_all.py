#!/usr/bin/env python3
"""Generate all D20 pixel art assets from manifest."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

MANIFEST = str(Path(__file__).resolve().parent / "manifest.json")
SRC_DIR = str(Path(__file__).resolve().parent / "sources")
OUT_DIR = str(Path(__file__).resolve().parent / "pixel-art")
PIXEL_SCRIPT = str(Path(os.environ.get("PIXEL_ART_SKILL_DIR", "~/.hermes/skills/creative/pixel-art/scripts")).expanduser() / "pixel_art.py")

os.makedirs(SRC_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

with open(MANIFEST) as f:
    assets = json.load(f)

print(f"Generating {len(assets)} assets...")

# Read existing sources to skip re-downloads
existing_sources = set(os.listdir(SRC_DIR)) if os.path.exists(SRC_DIR) else set()
existing_outputs = set(os.listdir(OUT_DIR))

# PHASE 1: Generate source images via FAL API (curl to image.pollinations.ai)
# Since we cant call image_generate from here, we write a shell script of curl commands
# Actually, let's source the FAL URLs via the Pollinations API sequentially with delays

failed = []
converted = 0

for i, asset in enumerate(assets):
    name = asset["name"]
    prompt = asset["prompt"]
    preset = asset["preset"]
    block = asset["block"]
    
    src_path = f"{SRC_DIR}/{name}.jpg"
    out_path = f"{OUT_DIR}/{name}.png"
    
    # Skip if output already exists
    if name + ".png" in existing_outputs:
        print(f"[{i+1}/{len(assets)}] SKIP (output exists): {name}")
        converted += 1
        continue
    
    # Step 1: Generate source image via Pollinations
    if name + ".jpg" not in existing_sources:
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=768&nologo=true&seed=42"
        print(f"[{i+1}/{len(assets)}] FETCH: {name}...", end=" ", flush=True)
        try:
            urllib.request.urlretrieve(url, src_path)
            # Verify it's an image
            with open(src_path, "rb") as f:
                header = f.read(4)
            if header[:2] == b"\xff\xd8" or header[:4] == b"\x89PNG":
                print("OK")
            else:
                print("BAD RESPONSE (not image)")
                os.remove(src_path)
                failed.append(name)
                time.sleep(3)
                continue
        except Exception as e:
            print(f"FAILED: {e}")
            failed.append(name)
            time.sleep(3)
            continue
        time.sleep(3)  # Rate limit: 1 req per IP
    else:
        print(f"[{i+1}/{len(assets)}] CACHED: {name} (source exists)")
    
    # Step 2: Convert to pixel art  
    print(f"  CONVERT: {name} ({preset}, block={block})...", end=" ", flush=True)
    result = subprocess.run(
        ["python3", PIXEL_SCRIPT, src_path, out_path, "--preset", preset, "--block", str(block)],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode == 0:
        print("OK")
        converted += 1
    else:
        print(f"FAILED: {result.stderr.strip()}")
        failed.append(name)

print(f"\n=== COMPLETE ===")
print(f"Converted: {converted}/{len(assets)}")
if failed:
    print(f"Failed: {failed}")
