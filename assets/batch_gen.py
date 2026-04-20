#!/usr/bin/env python3
"""Download FAL sources and convert to pixel art for D20 assets."""
import subprocess, os, json

SRC_DIR = "/home/rigario/Projects/rigario-d20/assets/sources"
OUT_DIR = "/home/rigario/Projects/rigario-d20/assets/pixel-art"
PIXEL = "/home/rigario/.hermes/skills/creative/pixel-art/scripts/pixel_art.py"

os.makedirs(SRC_DIR, exist_ok=True)

# Name -> (url, preset)
ASSETS = {
    "npc-aldric": ("https://v3b.fal.media/files/b/0a96fea5/bPlz2_cFer5NuaTAyUwHB_oQvU6rwC.png", "snes"),
    "npc-ser-maren": ("https://v3b.fal.media/files/b/0a96fea6/1q0R9MX0x8WTG-oqj3725_RTlNFELY.png", "snes"),
    "npc-marta": ("https://v3b.fal.media/files/b/0a96fea6/aTkQeIRAWorwVU-GnShZS_MA9QM0wB.png", "snes"),
    "npc-kira": ("https://v3b.fal.media/files/b/0a96fea7/k-8HxacrAObXam9tUhYVy_EFqU945m.png", "snes"),
    "npc-sister-drenna": ("https://v3b.fal.media/files/b/0a96fea7/Gt2Q7dP89DgmC96Ji9Y-3_1ETFShXc.png", "snes"),
    "npc-dels-spirit": ("https://v3b.fal.media/files/b/0a96fea8/b1b3vwXbYYUBIzsdkjwEP_dHGsFBra.png", "snes"),
    "npc-torren": ("https://v3b.fal.media/files/b/0a96fea9/tmgz6XF5ETt39M7Jm2BK__t12rsqjF.png", "snes"),
    "enc-hollow-eye-road": ("https://v3b.fal.media/files/b/0a96fea9/7SF0IyfFpjkVrck32-V-P_ip2yOqay.png", "snes"),
    "enc-starving-wolves": ("https://v3b.fal.media/files/b/0a96feaa/EQWaYug3lwq86ffKSrJGJ_HDMiNvmz.png", "snes"),
    "enc-goblin-scouts": ("https://v3b.fal.media/files/b/0a96feab/E8bPxxVppzt-ivpt25uxl_sOKYHll0.png", "snes"),
    "enc-stirring-dead": ("https://v3b.fal.media/files/b/0a96feab/AMTdpqkGnKSZCq03-0Ohw_z7y1Lr7j.png", "snes"),
    "enc-cave-zombies": ("https://v3b.fal.media/files/b/0a96feac/rBpF3L-OctZ27CgJO6tFc_9AaQMDyL.png", "snes"),
    "enc-corrupted-spider": ("https://v3b.fal.media/files/b/0a96feac/KkIxcquvhWgXIvcN_LPJd_dzCjywXC.png", "snes"),
    "enc-breaking-rite": ("https://v3b.fal.media/files/b/0a96fead/zgpwlM4s9aZjKvbeQPDHy_ZOOtmgQA.png", "snes"),
    "enc-toll-collector": ("https://v3b.fal.media/files/b/0a96fead/VWiJYgccBwKy-ZyDrGSNe_HheJUDAL.png", "snes"),
    "enc-withered-grove": ("https://v3b.fal.media/files/b/0a96feae/BE0vxTsKtlJQ1t_2KWLgp_xLW8Hnu2.png", "snes"),
    "enc-merchant-ghost": ("https://v3b.fal.media/files/b/0a96feaf/eRcJfxTTfbPt_KfqBaCZM_gXsJEbZ6.png", "snes"),
    "enc-old-root": ("https://v3b.fal.media/files/b/0a96feaf/fpAf1JUG6nIJtrcxIrDzB_yjfayksk.png", "arcade"),
    "enc-stonefist": ("https://v3b.fal.media/files/b/0a96feb1/XnRd8lrlP4VFWPqscNFsU_0OjRtm3u.png", "arcade"),
    "enc-eye-stalker": ("https://v3b.fal.media/files/b/0a96feb2/rrAzFaNNLA1CsdQMprRvd_jRZZo6cQ.png", "neon"),
    "enc-moonpetal-warden": ("https://v3b.fal.media/files/b/0a96feb2/xyOZ4EvDOzwfCEMss7at1_XAV3pzgZ.png", "snes"),
    "enc-orc-refugees": ("https://v3b.fal.media/files/b/0a96feb4/BQAJYm27pN5AflVJ4MzXH_fDbXdaIa.png", "snes"),
    "loc-rusty-tankard": ("https://v3b.fal.media/files/b/0a96feb5/YauwjIeEqw7TD9Vcp4yYW_RNyklKl2.png", "arcade"),
    "loc-south-road": ("https://v3b.fal.media/files/b/0a96feb5/CbOx7GRoPtkQxhtIMgk1Y_B2BNZrzO.png", "arcade"),
    "loc-crossroads": ("https://v3b.fal.media/files/b/0a96feb6/5uakBliJaK-ICVMIzSd0P_3k8hJw18.png", "arcade"),
    "loc-deep-whisperwood": ("https://v3b.fal.media/files/b/0a96feb7/Ke0tYvvYbSTqQ5MT2GGnU_M4hCu0sq.png", "arcade"),
    "loc-greypeak-pass": ("https://v3b.fal.media/files/b/0a96feb7/6tl9fve4eWLotP8AsbhxS_7Gpf4hhF.png", "arcade"),
    "loc-cave-entrance": ("https://v3b.fal.media/files/b/0a96feb8/chNyymSfErVwGnDE_eqpH_o4DQWHez.png", "arcade"),
    "loc-moonpetal-glade": ("https://v3b.fal.media/files/b/0a96feb9/5IvNtfeR3kA3O3yI-CoaF_nnXFYQRp.png", "arcade"),
    "item-mark-of-dreamer": ("https://v3b.fal.media/files/b/0a96feb9/hOHAFf61yBRTwOH-QOPvD_TfuQjbQC.png", "neon"),
    "item-dels-signet-ring": ("https://v3b.fal.media/files/b/0a96feba/KLg8IAnau87_znDW7wGhH_Wemcyttj.png", "snes"),
    "item-kols-ritual-dagger": ("https://v3b.fal.media/files/b/0a96feba/ACFlsJaWL_RYR4Cjuo-Y8_enYqIKgE.png", "snes"),
    "item-moonpetal-bundle": ("https://v3b.fal.media/files/b/0a96febb/kFgD0IpZrDBow6yeID20T_gEBKGvIu.png", "snes"),
    "item-hollow-eye-sigil": ("https://v3b.fal.media/files/b/0a96febc/OrIeHn6DicIX7vAVwRvWW_mTfS3ZSV.png", "snes"),
    "item-eye-stalker-core": ("https://v3b.fal.media/files/b/0a96febd/anZPjaDCPUUMW0VjqGOkX_QEnnhsSx.png", "neon"),
}

dl_ok = 0
dl_fail = 0
cv_ok = 0
cv_fail = 0

print(f"=== DOWNLOADING {len(ASSETS)} SOURCES ===")
for name, (url, preset) in sorted(ASSETS.items()):
    src = f"{SRC_DIR}/{name}.jpg"
    if os.path.exists(src) and os.path.getsize(src) > 1000:
        print(f"  CACHED: {name}")
        dl_ok += 1
        continue
    r = subprocess.run(["curl", "-sL", "--max-time", "30", "-o", src, url], capture_output=True)
    if r.returncode == 0 and os.path.exists(src) and os.path.getsize(src) > 1000:
        print(f"  OK: {name}")
        dl_ok += 1
    else:
        print(f"  FAIL: {name}")
        dl_fail += 1

print(f"\n=== CONVERTING TO PIXEL ART (block=2) ===")
for name, (url, preset) in sorted(ASSETS.items()):
    src = f"{SRC_DIR}/{name}.jpg"
    out = f"{OUT_DIR}/{name}.png"
    if not os.path.exists(src):
        print(f"  SKIP (no source): {name}")
        cv_fail += 1
        continue
    r = subprocess.run(["python3", PIXEL, src, out, "--preset", preset, "--block", "2"], capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  OK: {name} ({preset})")
        cv_ok += 1
    else:
        print(f"  FAIL: {name} - {r.stderr.strip()[:80]}")
        cv_fail += 1

print(f"\n=== COMPLETE ===")
print(f"Downloaded: {dl_ok}, Failed: {dl_fail}")
print(f"Converted: {cv_ok}, Failed: {cv_fail}")