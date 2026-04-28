#!/bin/bash
# D20 Pixel Art Asset Generator - Higher Resolution (block=2)
# Fetches source images from Pollinations + FAL, then converts with smaller pixel blocks

set -e
ASSET_DIR="$(cd "$(dirname "$0")" && pwd)/pixel-art"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)/sources"
mkdir -p "$SRC_DIR"

# Character prompts (Pollinations)
declare -A CHAR_PROMPTS
CHAR_PROMPTS[del-possessed]="A D&D fantasy tavern scene: a possessed man with glowing amber eyes lunging forward with a knife in a dimly lit rustic inn, wooden tables, warm hearth fire, the mans body language showing inner struggle against dark possession, D&D 5e art style"
CHAR_PROMPTS[brother-kol]="A D&D fantasy villain: Brother Kol, a calm hollow-eyed cult leader in dark hooded robes standing before a cracked glowing amber seal stone in a cave, ritual dagger in hand, serene expression, eerie amber light, underground cavern with phosphorescent moss"
CHAR_PROMPTS[green-woman]="A D&D forest fey: the Green Woman, a mystical fey woman with green skin and long flowing hair made of leaves and vines, standing in a moonlit glade surrounded by pale blue-white moonpetal flowers, standing stones, ethereal forest atmosphere"
CHAR_PROMPTS[gromm-bugbear]="A D&D bugbear: Gromm, a massive hairy humanoid standing protectively in dark forest shelter of branches and bones, holding a morningstar, fierce but defensive, deep dark forest, dark fantasy art"
CHAR_PROMPTS[whisperwood-edge]="A D&D dark forest edge: tall oaks with thick undergrowth, scratched circles on tree bark, broken branches, eerie silence, path leading toward a cave, moody dark fantasy atmosphere"
CHAR_PROMPTS[cave-depths-seal]="An underground dungeon cavern with phosphorescent moss on dark stone walls, thick cobwebs, ancient carved sigils on the floor, amber glow in the distance, ominous dark fantasy D&D setting"

echo "=== Fetching character sources from Pollinations ==="
for name in del-possessed brother-kol green-woman gromm-bugbear whisperwood-edge cave-depths-seal; do
    encoded=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${CHAR_PROMPTS[$name]}'))")
    out="$SRC_DIR/${name}.jpg"
    if [ ! -f "$out" ]; then
        echo "Fetching $name..."
        curl -sL --max-time 120 -o "$out" "https://image.pollinations.ai/prompt/${encoded}?width=768&height=768&nologo=true&seed=42" || echo "FAILED: $name"
        sleep 2
    else
        echo "Already have $name"
    fi
done

echo ""
echo "=== Converting to pixel art (block=2, SNES-quality detail) ==="
cd ${PIXEL_ART_SKILL_DIR:-$HOME/.hermes/skills/creative/pixel-art/scripts}

# Characters: SNES preset but block=2 for more detail
for name in del-possessed brother-kol green-woman gromm-bugbear; do
    echo "Converting $name (snes, block=2)..."
    python3 pixel_art.py "$SRC_DIR/${name}.jpg" "$ASSET_DIR/${name}.png" --preset snes --block 2
done

# Locations: arcade preset but block=2
for name in whisperwood-edge cave-depths-seal; do
    echo "Converting $name (arcade, block=2)..."
    python3 pixel_art.py "$SRC_DIR/${name}.jpg" "$ASSET_DIR/${name}.png" --preset arcade --block 2
done

echo ""
echo "=== Done. Checking results ==="
for f in "$ASSET_DIR"/*.png; do
    if [[ "$f" != *"_source"* ]] && [[ "$f" != *"_v"* ]]; then
        python3 -c "
from PIL import Image
img = Image.open('$f')
colors = len(img.getcolors(maxcolors=10000) or [])
print(f'  $(basename $f): {img.size[0]}x{img.size[1]}, {colors} colors')
"
    fi
done