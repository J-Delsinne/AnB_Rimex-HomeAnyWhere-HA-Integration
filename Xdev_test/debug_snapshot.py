#!/usr/bin/env python3
"""
Debug script to show raw snapshot data
"""

import sys
import time
from ipcom.ipcom_tcp_client import IPComClient

# Configure stdout for UTF-8 on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

def main():
    print("Connecting to IPCom server...")
    client = IPComClient("megane-david.dyndns.info", 5000, debug=False)

    try:
        # Connect and authenticate
        if not client.connect():
            print("❌ Connection failed")
            return

        print("✔ Connected")

        if not client.authenticate():
            print("❌ Authentication failed")
            return

        print("✔ Authenticated")

        # Start polling
        client.start_snapshot_polling()
        print("✔ Polling started")

        # Wait for snapshots
        print("\nWaiting for snapshots (5 seconds)...\n")

        for i in range(5):
            time.sleep(1)

            # Manually process incoming data
            client._receive_loop()

            snapshot = client.get_latest_snapshot()
            if snapshot:
                print(f"[{i+1}/5] Snapshot received:")
                print(f"  Raw data (first 20 bytes): {snapshot.raw[:20].hex()}")

                # Count non-zero outputs
                non_zero = 0
                for module in range(1, 17):
                    for output in range(1, 9):
                        value = snapshot.get_value(module, output)
                        if value > 0:
                            non_zero += 1
                            print(f"  Module {module}, Output {output} = {value}")

                print(f"  Total active outputs: {non_zero}\n")
            else:
                print(f"[{i+1}/5] No snapshot yet\n")

    finally:
        client.disconnect()
        print("✔ Disconnected")

if __name__ == "__main__":
    main()
