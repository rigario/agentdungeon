#!/bin/bash
# Download all FAL sources and convert to pixel art
set -e

SRC_DIR="/home/rigario/Projects/rigario-d20/assets/sources"
OUT_DIR="/home/rigario/Projects/rigario-d20/assets/pixel-art"
PIXEL="/home/rigario/.hermes/skills/creative/pixel-art/scripts/pixel_art.py"

mkdir -p "$SRC_DIR" "$OUT_DIR"

# URL mapping: name=url
declare -A URLS
URLS[npc-aldric]="https://v3b.fal.media/files/b/0a96fea5/bPlz2_cFer5NuaTAyUwHB_oQvU6rwC.png"
URLS[npc-ser-maren]="https://v3b.fal.media/files/b/0a96fea6/1q0R9MX0x8WTG-oqj3725_RTlNFELY.png"
URLS[npc-marta]="https://v3b.fal.media/files/b/0a96fea6/aTkQeIRAWorwVU-GnShZS_MA9QM0wB.png"
URLS[npc-kira]="https://v3b.fal.media/files/b/0a96fea7/k-8HxacrAObXam9tUhYVy_EFqU945m.png"
URLS[npc-sister-drenna]="https://v3b.fal.media/files/b/0a96fea7/Gt2Q7dP89DgmC96Ji9Y-3_1ETFShXc.png"
URLS[npc-dels-spirit]="https://v3b.fal.media/files/b/0a96fea8/b1b3vwXbYYUBIzsdkjwEP_dHGsFBra.png"
URLS[npc-torren]="https://v3b.fal.media/files/b/0a96fea9/tmgz6XF5ETt39M7Jm2BK__t12rsqjF.png"
URLS[enc-hollow-eye-road]="https://v3b.fal.media/files/b/0a96fea9/7SF0IyfFpjkVrck32-V-P_ip2yOqay.png"
URLS[enc-starving-wolves]="https://v3b.fal.media/files/b/0a96feaa/EQWaYug3lwq86ffKSrJGJ_HDMiNvmz.png"
URLS[enc-goblin-scouts]="https://v3b.fal.media/files/b/0a96feab/E8bPxxVppzt-ivpt25uxl_sOKYHll0.png"
URLS[enc-stirring-dead]="https://v3b.fal.media/files/b/0a96feab/AMTdpqkGnKSZCq03-0Ohw_z7y1Lr7j.png"
URLS[enc-cave-zombies]="https://v3b.fal.media/files/b/0a96feac/rBpF3L-OctZ27CgJO6tFc_9AaQMDyL.png"
URLS[enc-corrupted-spider]="https://v3b.fal.media/files/b/0a96feac/KkIxcquvhWgXIvcN_LPJd_dzCjywXC.png"
URLS[enc-breaking-rite]="https://v3b.fal.media/files/b/0a96fead/zgpwlM4s9aZjKvbeQPDHy_ZOOtmgQA.png"
URLS[enc-toll-collector]="https://v3b.fal.media/files/b/0a96fead/VWiJYgccBwKy-ZyDrGSNe_HheJUDAL.png"
URLS[enc-withered-grove]="https://v3b.fal.media/files/b/0a96feae/BE0vxTsKtlJQ1t_2KWLgp_xLW8Hnu2.png"
URLS[enc-merchant-ghost]="https://v3b.fal.media/files/b/0a96feaf/eRcJfxTTfbPt_KfqBaCZM_gXsJEbZ6.png"
URLS[enc-old-root]="https://v3b.fal.media/files/b/0a96feaf/fpAf1JUG6nIJtrcxIrDzB_yjfayksk.png"
URLS[enc-stonefist]="https://v3b.fal.media/files/b/0a96feb1/XnRd8lrlP4VFWPqscNFsU_0OjRtm3u.png"
URLS[enc-eye-stalker]="https://v3b.fal.media/files/b/0a96feb2/rrAzFaNNLA1CsdQMprRvd_jRZZo6cQ.png"
URLS[enc-moonpetal-warden]="https://v3b.fal.media/files/b/0a96feb2/xyOZ4EvDOzwfCEMss7at1_XAV3pzgZ.png"
URLS[enc-orc-refugees]="https://v3b.fal.media/files/b/0a96feb4/BQAJYm27pN5AflVJ4MzXH_fDbXdaIa.png"
URLS[loc-rusty-tankard]="https://v3b.fal.media/files/b/0a96feb5/YauwjIeEqw7TD9Vcp4yYW_RNyklKl2.png"
URLS[loc-south-road]="https://v3b.fal.media/files/b/0a96feb5/CbOx7GRoPtkQxhtIMgk1Y_B2BNZrzO.png"
URLS[loc-crossroads]="https://v3b.fal.media/files/b/0a96feb6/5uakBliJaK-ICVMIzSd0P_3k8hJw18.png"
URLS[loc-deep-whisperwood]="https://v3b.fal.media/files/b/0a96feb7/Ke0tYvvYbSTqQ5MT2GGnU_M4hCu0sq.png"
URLS[loc-greypeak-pass]="https://v3b.fal.media/files/b/0a96feb7/6tl9fve4eWLotP8AsbhxS_7Gpf4hhF.png"
URLS[loc-cave-entrance]="https://v3b.fal.media/files/b/0a96feb8/chNyymSfErVwGnDE_eqpH_o4DQWHez.png"
URLS[loc-moonpetal-glade]="https://v3b.fal.media/files/b/0a96feb9/5IvNtfe3kA3O3yI-CoaF_nnXFYQRp.png"
URLS[item-mark-of-dreamer]="https://v3b.fal.media/files/b/0a96feb9/hOHAFf61yBRTwOH-QOPvD_TfuQjbQC.png"
URLS[item-dels-signet-ring]="https://v3b.fal.media/files/b/0a96feba/KLg8IAnau87_znDW7wGhH_Wemcyttj.png"
URLS[item-kols-ritual-dagger]="https://v3b.fal.media/files/b/0a96feba/ACFlsJaWL_RYR4Cjuo-Y8_enYqIKgE.png"
URLS[item-moonpetal-bundle]="https://v3b.fal.media/files/b/0a96febb/kFgD0IpZrDBow6yeID20T_gEBKGvIu.png"
URLS[item-hollow-eye-sigil]="https://v3b.fal.media/files/b/0a96febc/OrIeHn6DicIX7vAVwRvWW_mTfS3ZSV.png"
URLS[item-eye-stalker-core]="https://v3b.fal.media/files/b/0a96febd/anZPjaDCPUUMW0VjqGOkX_QEnnhsSx.png"

# Preset mapping
declare -A PRESETS
PRESETS[npc-aldric]="snes"
PRESETS[npc-ser-maren]="snes"
PRESETS[npc-marta]="snes"
PRESETS[npc-kira]="snes"
PRESETS[npc-sister-drenna]="snes"
PRESETS[npc-dels-spirit]="snes"
PRESETS[npc-torren]="snes"
PRESETS[enc-hollow-eye-road]="snes"
PRESETS[enc-starving-wolves]="snes"
PRESETS[enc-goblin-scouts]="snes"
PRESETS[enc-stirring-dead]="snes"
PRESETS[enc-cave-zombies]="snes"
PRESETS[enc-corrupted-spider]="snes"
PRESETS[enc-breaking-rite]="snes"
PRESETS[enc-toll-collector]="snes"
PRESETS[enc-withered-grove]="snes"
PRESETS[enc-merchant-ghost]="snes"
PRESETS[enc-old-root]="arcade"
PRESETS[enc-stonefist]="arcade"
PRESETS[enc-eye-stalker]="neon"
PRESETS[enc-moonpetal-warden]="snes"
PRESETS[enc-orc-refugees]="snes"
PRESETS[loc-rusty-tankard]="arcade"
PRESETS[loc-south-road]="arcade"
PRESETS[loc-crossroads]="arcade"
PRESETS[loc-deep-whisperwood]="arcade"
PRESETS[loc-greypeak-pass]="arcade"
PRESETS[loc-cave-entrance]="arcade"
PRESETS[loc-moonpetal-glade]="arcade"
PRESETS[item-mark-of-dreamer]="neon"
PRESETS[item-dels-signet-ring]="snes"
PRESETS[item-kols-ritual-dagger]="snes"
PRESETS[item-moonpetal-bundle]="snes"
PRESETS[item-hollow-eye-sigil]="snes"
PRESETS[item-eye-stalker-core]="neon"

DOWNLOADED=0
CONVERTED=0
FAILED=0

echo "=== DOWNLOADING SOURCES ==="
for name in "${!URLS[@]}"; do
    src="$SRC_DIR/${name}.jpg"
    if [ -f "$src" ]; then
        echo "  CACHED: $name"
        ((DOWNLOADED++))
        continue
    fi
    curl -sL --max-time 30 -o "$src" "${URLS[$name]}" && \
    file "$src" | grep -q "image data" && \
    echo "  OK: $name" && ((DOWNLOADED++)) || \
    echo "  FAIL: $name" && ((FAILED++))
done

echo ""
echo "=== CONVERTING TO PIXEL ART (block=2) ==="
for name in "${!URLS[@]}"; do
    src="$SRC_DIR/${name}.jpg"
    out="$OUT_DIR/${name}.png"
    preset="${PRESETS[$name]}"
    
    if [ ! -f "$src" ]; then
        echo "  SKIP (no source): $name"
        ((FAILED++))
        continue
    fi
    
    python3 "$PIXEL" "$src" "$out" --preset "$preset" --block 2 2>&1 && \
    echo "  OK: $name ($preset)" && ((CONVERTED++)) || \
    echo "  FAIL: $name" && ((FAILED++))
done

echo ""
echo "=== COMPLETE ==="
echo "Downloaded: $DOWNLOADED"
echo "Converted: $CONVERTED"
echo "Failed: $FAILED"