#!/usr/bin/env python
"""
Quick validation script for cadence_scheduler module.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Test 1: imports
try:
    from app.services.cadence_scheduler import tick_all_active_characters, start_scheduler, stop_scheduler, get_scheduler, set_enabled
    print("OK: imports")
except Exception as e:
    print(f"FAIL import: {e}")
    sys.exit(1)

# Test 2: tick no-op in normal mode
try:
    tick_all_active_characters()
    print("OK: tick normal mode no-op")
except Exception as e:
    print(f"FAIL tick normal: {e}")
    sys.exit(1)

# Test 3: tick with playtest mode but no doom clocks
try:
    from app.services.playtest_cadence import set_cadence_mode
    set_cadence_mode("playtest", tick_interval=60)
    tick_all_active_characters()
    set_cadence_mode("normal")
    print("OK: tick playtest no-characters (or existing chars ticked)")
except Exception as e:
    print(f"FAIL tick playtest: {e}")
    sys.exit(1)

# Test 4: scheduler start/stop lifecycle
try:
    stop_scheduler(None)
    start_scheduler(None)
    sched = get_scheduler()
    assert sched is not None, "Scheduler is None after start"
    assert sched.running, "Scheduler not running"
    jobs = sched.get_jobs()
    assert len(jobs) == 1, f"Expected 1 job, got {len(jobs)}"
    assert jobs[0].id == "cadence_tick_job", f"Wrong job id: {jobs[0].id}"
    stop_scheduler(None)
    assert get_scheduler() is None, "Scheduler not cleared after stop"
    print("OK: scheduler lifecycle")
except Exception as e:
    print(f"FAIL scheduler lifecycle: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

print("\nALL CHECKS PASSED")
