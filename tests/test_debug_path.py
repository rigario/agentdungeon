"""Debug test path resolution"""
import sys, os
print("\n=== DEBUG: test module top of file ===")
print("__file__ =", __file__ if '__file__' in dir() else "NOT SET")
print("sys.path[0] =", sys.path[0])
print("First 5 entries:")
for p in sys.path[:5]:
    print(" ", p)

_PROJECT_PARENT = "/home/rigario/Projects/rigario-d20"
if _PROJECT_PARENT not in sys.path:
    sys.path.insert(0, _PROJECT_PARENT)
    print(f"Inserted {_PROJECT_PARENT} at position 0")
else:
    print(f"{_PROJECT_PARENT} already in sys.path at index {sys.path.index(_PROJECT_PARENT)}")

print("\nAfter path hack, sys.path[0] =", sys.path[0])
print("Searching for app.services.srd_reference...")
import importlib
spec = importlib.util.find_spec('app.services.srd_reference')
print("find_spec result:", spec)
