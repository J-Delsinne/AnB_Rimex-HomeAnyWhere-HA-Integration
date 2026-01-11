# Home Anywhere Blue - IPCom Integration

Python client and Home Assistant integration for Home Anywhere Blue home automation systems via the proprietary IPCom TCP protocol.

## ✅ Status: Production Ready

- ✅ Complete protocol reverse engineered
- ✅ TCP connection with XOR encryption
- ✅ CLI interface with JSON output
- ✅ Full Home Assistant integration
- ✅ Support for lights, dimmers, and dual-relay shutters
- ✅ Module 6 (EXO DIM) dimmer support

---

## Repository Structure

```
/
├── README.md                      # This file
├── DEPLOYMENT_SUMMARY.md          # Deployment guide
├── MODULE_6_QUICK_REFERENCE.md    # EXO DIM reference
├── COVER_DEPLOYMENT.md            # Shutter deployment guide
│
├── ipcom/                         # CLI & Core Protocol
│   ├── ipcom_cli.py              # CLI interface (JSON contract v1.0)
│   ├── ipcom_tcp_client.py       # TCP client with encryption
│   ├── models.py                  # Data models
│   ├── frame_builder.py           # Command frame construction
│   └── devices.yaml               # Device configuration
│
└── custom_components/ipcom/       # Home Assistant Integration
    ├── __init__.py
    ├── manifest.json
    ├── const.py
    ├── config_flow.py
    ├── coordinator.py
    ├── light.py                   # Switches & dimmers
    ├── cover.py                   # Dual-relay shutters
    └── translations/en.json
```

---

## Quick Start

### 1. CLI Usage

```bash
# Navigate to ipcom directory
cd ipcom

# Check device status
python ipcom_cli.py status --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS

# Control devices
python ipcom_cli.py on keuken --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS
python ipcom_cli.py off keuken --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS
python ipcom_cli.py dim salon 50 --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS

# Watch live updates (JSON)
python ipcom_cli.py watch --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS --json
```

### 2. Home Assistant Installation

**Step 1: Copy CLI files**
```bash
# Copy the entire ipcom folder to your Home Assistant config directory
scp -r ipcom root@homeassistant:/config/
```

**Step 2: Copy Home Assistant integration**
```bash
# Copy custom component
scp -r custom_components/ipcom root@homeassistant:/config/custom_components/
```

**Step 3: Configure devices.yaml**
Edit `/config/ipcom/devices.yaml` with your device configuration.

**Step 4: Restart Home Assistant**
```
Settings → System → Restart
```

**Step 5: Add Integration**
1. Settings → Devices & Services → Add Integration
2. Search for "IPCom Home Anywhere Blue"
3. Configure:
   - CLI Path: `ipcom` (or full path `/config/ipcom`)
   - Host: Your IPCom hostname or IP address
   - Port: `5000`
   - Username: Your IPCom username
   - Password: Your IPCom password

---

## Features

### Supported Devices

**Lights**
- ✅ On/Off switches (15 devices)
- ✅ Dimmers (Module 6 - EXO DIM) - 2 devices

**Covers (Shutters)**
- ✅ Dual-relay shutter control (4 physical shutters = 8 relays)
- ✅ Safety: UP=1 & DOWN=1 never occurs
- ✅ Operations: Open, Close, Stop

### Module 6 (EXO DIM) Support

Module 6 dimmers use a **0-100 value range** (not 0-255 like regular modules).

```bash
# Turn on to 100%
python ipcom_cli.py on eetkamer --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS

# Dim to 50%
python ipcom_cli.py dim eetkamer 50 --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS

# Turn off
python ipcom_cli.py off eetkamer --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS
```

See [MODULE_6_QUICK_REFERENCE.md](MODULE_6_QUICK_REFERENCE.md) for details.

### Dual-Relay Shutter Control

Each physical shutter requires **two relays** (UP and DOWN):

```yaml
# devices.yaml example
shutters:
  rolluik_sal_links_d:
    module: 5
    output: 1
    relay_role: down
    paired_device: rolluik_sal_links_m

  rolluik_sal_links_m:
    module: 5
    output: 2
    relay_role: up
    paired_device: rolluik_sal_links_d
```

The cover platform automatically creates one cover entity per physical shutter, controlling both relays safely.

See [COVER_DEPLOYMENT.md](COVER_DEPLOYMENT.md) for details.

---

## CLI JSON Contract (v1.0)

The CLI provides a **stable JSON interface** for Home Assistant:

```bash
python ipcom_cli.py status --json --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS
```

**Output Structure**:
```json
{
  "timestamp": "2025-12-28T14:00:00+00:00",
  "host": "your-ipcom-host.example.com",
  "devices": [
    {
      "device_key": "salon",
      "display_name": "SALON",
      "category": "lights",
      "type": "dimmer",
      "module": 6,
      "output": 2,
      "value": 50,
      "state": "on",
      "brightness": 50
    },
    {
      "device_key": "rolluik_sal_links_m",
      "display_name": "ROLLUIK SAL LINKS M",
      "category": "shutters",
      "type": "switch",
      "module": 5,
      "output": 2,
      "value": 0,
      "state": "off",
      "relay_role": "up",
      "paired_device": "rolluik_sal_links_d"
    }
  ]
}
```

---

## Architecture

```
┌─────────────────────────────────────┐
│     Home Assistant Frontend         │
└──────────────┬──────────────────────┘
               │
    ┌──────────▼──────────┐
    │  Light Platform     │
    │  Cover Platform     │
    └──────────┬──────────┘
               │
       ┌───────▼────────┐
       │  Coordinator   │
       └───────┬────────┘
               │
         ┌─────▼─────┐
         │ CLI JSON  │  ← Stable Contract v1.0
         └─────┬─────┘
               │
    ┌──────────▼──────────┐
    │  ipcom_cli.py       │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │ ipcom_tcp_client.py │
    │ frame_builder.py    │
    │ models.py           │
    └──────────┬──────────┘
               │
         ┌─────▼─────┐
         │ TCP/IP    │
         │ XOR Enc   │
         └─────┬─────┘
               │
    ┌──────────▼──────────┐
    │ Home Anywhere Blue  │
    │ IPCom Controller    │
    └─────────────────────┘
```

**Key Design Principles**:
- Home Assistant ↔ CLI JSON (stable, versioned interface)
- No protocol parsing in Home Assistant code
- CLI encapsulates all TCP/protocol complexity

---

## Python API Usage

```python
from ipcom.ipcom_tcp_client import IPComClient

# Connect
client = IPComClient(
    host="your-ipcom-host.example.com",
    port=5000,
    username="your_username",
    password="your_password"
)
client.connect()
client.authenticate()
client.start_snapshot_polling()

# Control devices
client.turn_on(module=3, output=4)
client.turn_off(module=3, output=4)
client.set_dimmer(module=6, output=1, percentage=75)

# Get state
snapshot = client.get_latest_snapshot()
value = snapshot.get_value(module=3, output=4)

# Cleanup
client.disconnect()
```

---

## Configuration

### devices.yaml

Define your devices in `ipcom/devices.yaml`:

```yaml
lights:
  keuken:
    module: 3
    output: 4
    type: switch
    display_name: "KEUKEN"

  salon:
    module: 6
    output: 2
    type: dimmer
    display_name: "SALON"

shutters:
  rolluik_keuken_d:
    module: 5
    output: 7
    type: switch
    relay_role: down
    paired_device: rolluik_keuken_m

  rolluik_keuken_m:
    module: 5
    output: 8
    type: switch
    relay_role: up
    paired_device: rolluik_keuken_d
```

---

## Testing

```bash
# Test CLI
cd ipcom
python ipcom_cli.py status --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS

# Test control
python ipcom_cli.py on keuken --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS

# Test dimming (Module 6)
python ipcom_cli.py dim salon 50 --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS
```

---

## Troubleshooting

### CLI not working
```bash
# Check Python version (requires Python 3.7+)
python3 --version

# Test connection
python ipcom/ipcom_cli.py status --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS

# Check devices.yaml exists
ls -la ipcom/devices.yaml
```

### Home Assistant integration issues
```bash
# Check logs
tail -f /config/home-assistant.log | grep ipcom

# Verify CLI path
cat /config/custom_components/ipcom/const.py | grep CLI_SCRIPT

# Test CLI manually
python3 /config/ipcom/ipcom_cli.py status --json --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS
```

### Covers not appearing
```bash
# Verify relay metadata
python ipcom/ipcom_cli.py status --json | grep relay_role

# Check devices.yaml has relay_role and paired_device
cat ipcom/devices.yaml | grep -A 5 "shutters:"
```

---

## Documentation

- **[DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md)** - Complete deployment guide
- **[MODULE_6_QUICK_REFERENCE.md](MODULE_6_QUICK_REFERENCE.md)** - EXO DIM dimmer reference
- **[COVER_DEPLOYMENT.md](COVER_DEPLOYMENT.md)** - Shutter deployment guide
- **[CODEBASE_SANITATION_REPORT.md](CODEBASE_SANITATION_REPORT.md)** - Cleanup report

---

## License

This project reverse engineers the proprietary Home Anywhere Blue IPCom protocol for personal use and home automation integration.

---

## Credits

Reverse engineered from the official Home Anywhere Blue Android app.

**Protocol Details**:
- XOR-based encryption with dual keys
- Custom frame structure (ExoSetValuesFrame, etc.)
- Module 6 (EXO DIM) uses 0-100 value range
- Dual-relay shutter control system

---

## Support

For issues, questions, or contributions, please open an issue on GitHub.

**Status**: Production ready - All features working ✅
