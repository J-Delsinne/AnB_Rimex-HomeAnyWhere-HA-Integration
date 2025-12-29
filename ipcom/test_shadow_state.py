#!/usr/bin/env python3
"""
Test shadow state fix for race condition in dual-relay shutter control.

This test verifies that rapid commands don't overwrite each other when using
the shadow state pattern (_pending_writes).
"""

import sys
import time
from ipcom_tcp_client import IPComClient

HOST = "megane-david.dyndns.info"
PORT = 5000

# Keuken shutter relays
KEUKEN_UP_MODULE = 5
KEUKEN_UP_OUTPUT = 8
KEUKEN_DOWN_MODULE = 5
KEUKEN_DOWN_OUTPUT = 7

def test_rapid_commands():
    """Test that rapid commands work correctly with shadow state."""
    print("=" * 70)
    print("Shadow State Race Condition Test")
    print("=" * 70)
    print()

    client = IPComClient(HOST, PORT, debug=False)

    print(f"Connecting to {HOST}:{PORT}...")
    if not client.connect():
        print("ERROR: Connection failed")
        return 1
    print("OK: Connected")

    if not client.authenticate():
        print("ERROR: Authentication failed")
        return 1
    print("OK: Authenticated")

    # Start polling to get initial snapshot
    client.start_snapshot_polling()
    print("OK: Polling started")
    print()

    # Wait for initial snapshot
    print("Waiting for initial state...")
    start = time.time()
    while not client.get_latest_snapshot() and time.time() - start < 3:
        client._receive_loop()
        time.sleep(0.05)

    if not client.get_latest_snapshot():
        print("ERROR: No snapshot received")
        return 1
    print()

    # Test: Rapid sequential commands (the race condition scenario)
    print("=" * 70)
    print("TEST: Rapid Commands (OPEN = turn_off DOWN, then turn_on UP)")
    print("=" * 70)
    print()

    print("Sending rapid sequence:")
    print("  1. turn_off(DOWN) - Module 5, Output 7")
    print("  2. turn_on(UP)    - Module 5, Output 8")
    print()

    # These commands happen rapidly, which used to cause race condition
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)
    client.turn_on(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)

    # Wait for server confirmation
    print("Waiting 2 seconds for server confirmation...")
    time.sleep(2)
    for _ in range(10):
        client._receive_loop()
        time.sleep(0.1)

    # Check result
    snapshot = client.get_latest_snapshot()
    if snapshot:
        up_value = snapshot.get_value(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
        down_value = snapshot.get_value(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)

        print()
        print("Result:")
        print(f"  UP relay (M{KEUKEN_UP_MODULE}O{KEUKEN_UP_OUTPUT}):   {up_value} (expected: >0)")
        print(f"  DOWN relay (M{KEUKEN_DOWN_MODULE}O{KEUKEN_DOWN_OUTPUT}): {down_value} (expected: 0)")
        print()

        # Verify expected state
        if up_value > 0 and down_value == 0:
            print("PASS: Shadow state prevented race condition!")
            print("   Both commands were applied correctly:")
            print("   - DOWN relay is OFF (0)")
            print("   - UP relay is ON (>0)")
            success = True
        else:
            print("FAIL: Race condition occurred!")
            print(f"   Expected: UP>0, DOWN=0")
            print(f"   Got:      UP={up_value}, DOWN={down_value}")
            if down_value > 0:
                print("   The turn_off(DOWN) command was lost (race condition bug)")
            success = False
    else:
        print("ERROR: No snapshot after command")
        success = False

    # Cleanup: Stop the shutter
    print()
    print("Cleanup: Stopping shutter (both relays OFF)...")
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)
    time.sleep(1)

    client.disconnect()
    print()
    print("OK: Disconnected")
    print()

    if success:
        print("=" * 70)
        print("TEST RESULT: PASSED - Shadow state fix is working!")
        print("=" * 70)
        return 0
    else:
        print("=" * 70)
        print("TEST RESULT: FAILED - Race condition still exists")
        print("=" * 70)
        return 1

if __name__ == "__main__":
    sys.exit(test_rapid_commands())
