#!/usr/bin/env python3
"""
Test device control - turn a device ON and OFF.
"""

import sys
import time
from ipcom.ipcom_tcp_client import IPComClient

sys.stdout.reconfigure(line_buffering=True)

def main():
    """Test controlling KEUKEN (Module 3, Output 4)."""

    print("=" * 80)
    print("DEVICE CONTROL TEST")
    print("=" * 80)
    print()
    print("Target: KEUKEN (Module 3, Output 4)")
    print()

    client = IPComClient("megane-david.dyndns.info", 5000, debug=False)

    # Track snapshots
    snapshot_count = [0]

    def on_snapshot(snapshot):
        snapshot_count[0] += 1
        keuken_value = snapshot.get_value(3, 4)

        if snapshot_count[0] % 5 == 1:  # Print every 5th snapshot
            print(f"[Snapshot #{snapshot_count[0]}] KEUKEN = {keuken_value} ({'ON' if keuken_value == 255 else 'OFF' if keuken_value == 0 else f'{keuken_value}/255'})")

    client.on_state_snapshot(on_snapshot)

    try:
        print("Connecting...")
        if not client.connect():
            print("[FAIL] Connection failed")
            return
        print("[OK] Connected")
        print()

        print("Authenticating...")
        if not client.authenticate():
            print("[FAIL] Authentication failed")
            return
        print("[OK] Authenticated")
        print()

        print("Starting polling...")
        client.start_snapshot_polling()
        print("[OK] Polling started")
        print()

        # Wait for initial state
        print("Waiting for initial state...")
        start = time.time()
        while snapshot_count[0] < 2 and time.time() - start < 3:
            client._receive_loop()
            time.sleep(0.01)

        if snapshot_count[0] == 0:
            print("[WARN] No snapshots received")
            return

        initial_value = client.get_value(3, 4)
        print(f"[OK] Initial state: KEUKEN = {initial_value} ({'ON' if initial_value == 255 else 'OFF'})")
        print()

        # Test 1: Turn OFF
        print("=" * 80)
        print("TEST 1: Turn KEUKEN OFF")
        print("=" * 80)
        client.turn_off(3, 4)
        print("[OK] Command sent: turn_off(module=3, output=4)")
        print()

        # Wait for state change
        print("Waiting for state update...")
        time.sleep(1)
        for _ in range(10):
            client._receive_loop()
            time.sleep(0.1)

        off_value = client.get_value(3, 4)
        print(f"Result: KEUKEN = {off_value}")
        if off_value == 0:
            print("[SUCCESS] Device turned OFF!")
        else:
            print(f"[WARN] Expected 0, got {off_value}")
        print()

        # Test 2: Turn ON
        print("=" * 80)
        print("TEST 2: Turn KEUKEN ON")
        print("=" * 80)
        client.turn_on(3, 4)
        print("[OK] Command sent: turn_on(module=3, output=4)")
        print()

        # Wait for state change
        print("Waiting for state update...")
        time.sleep(1)
        for _ in range(10):
            client._receive_loop()
            time.sleep(0.1)

        on_value = client.get_value(3, 4)
        print(f"Result: KEUKEN = {on_value}")
        if on_value == 255:
            print("[SUCCESS] Device turned ON!")
        else:
            print(f"[WARN] Expected 255, got {on_value}")
        print()

        # Restore initial state
        print("=" * 80)
        print("Restoring initial state...")
        print("=" * 80)
        if initial_value == 255:
            client.turn_on(3, 4)
            print("Turned back ON")
        else:
            client.turn_off(3, 4)
            print("Turned back OFF")

        time.sleep(1)
        for _ in range(5):
            client._receive_loop()
            time.sleep(0.1)

        print()
        print("=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)
        print(f"Total snapshots received: {snapshot_count[0]}")

    except KeyboardInterrupt:
        print()
        print("Interrupted by user")
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.disconnect()
        print()
        print("Disconnected")

if __name__ == "__main__":
    main()
