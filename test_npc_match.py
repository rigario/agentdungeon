import re

def find_npc(target, npcs):
    target_lower = target.lower().strip()
    target_tokens = {
        t for t in re.findall(r"[a-z0-9]+", target_lower)
        if t not in {"the", "a", "an", "to", "with", "about", "on", "of", "and", "ask", "tell", "say", "speak", "talk", "chat"}
    }
    for n in npcs:
        name_lower = n.get("name", "").lower()
        name_tokens = {
            t for t in re.findall(r"[a-z0-9]+", name_lower)
            if t not in {"the", "a", "an", "of"}
        }
        if (
            target_lower in name_lower
            or name_lower in target_lower
            or bool(target_tokens and name_tokens and (target_tokens & name_tokens))
        ):
            return n
    return None

npcs = [
    {"name": "Aldric", "id": "npc-aldric"},
    {"name": "Brother Kol", "id": "npc-brother-kol"},
    {"name": "Ser Maren", "id": "npc-maren"},
    {"name": "The Green Woman", "id": "npc-green-woman"},
]

tests = [
    ("ask Aldric about dreams", "Aldric"),
    ("talk to Brother Kol", "Brother Kol"),
    ("speak with the Green Woman", "The Green Woman"),
    ("ask maren about the seal", "Ser Maren"),
    ("aldric", "Aldric"),
    ("kol", "Brother Kol"),
    ("green woman", "The Green Woman"),
    ("random topic with no npc", None),
]

print("Token-matching tests:")
all_pass = True
for target, expected in tests:
    found = find_npc(target, npcs)
    found_name = found["name"] if found else None
    status = "PASS" if found_name == expected else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(f"  {status}: target='{target}' expected={expected} got={found_name}")

if all_pass:
    print("\nAll tests passed.")
else:
    print("\nSome tests FAILED.")
