# IPCom Home Anywhere Blue - Home Assistant Integration (UnOfficial)

Control your Home Anywhere Blue home automation system from Home Assistant.

## What This Does

- Controls **lights** (on/off switches and dimmers)
- Controls **shutters/covers** (open, close, stop)
- Real-time status updates via persistent TCP connection
- Automatic reconnection if connection drops

---

## Installation

### Step 1: Copy Files to Home Assistant

Copy both folders to your Home Assistant config directory:

```
/config/
├── ipcom/                         # CLI tool
│   ├── ipcom_cli.py
│   ├── ipcom_tcp_client.py
│   ├── devices.yaml               # Your device configuration
│   └── ...
│
└── custom_components/ipcom/       # Home Assistant integration
    ├── __init__.py
    ├── manifest.json
    ├── light.py
    ├── cover.py
    └── ...
```

**Using SSH/SCP:**
```bash
scp -r ipcom user@homeassistant:/config/
scp -r custom_components/ipcom user@homeassistant:/config/custom_components/
```

### Step 2: Configure Your Devices

Edit `/config/ipcom/devices.yaml` with your devices:

```yaml
lights:
  kitchen:
    module: 3
    output: 4
    type: switch
    display_name: "Kitchen"

  living_room:
    module: 6
    output: 2
    type: dimmer
    display_name: "Living Room"

shutters:
  # Each shutter needs TWO relays (up and down)
  shutter_kitchen_down:
    module: 5
    output: 7
    relay_role: down
    paired_device: shutter_kitchen_up

  shutter_kitchen_up:
    module: 5
    output: 8
    relay_role: up
    paired_device: shutter_kitchen_down
```

### Step 3: Add the Integration

1. Restart Home Assistant
2. Go to **Settings** > **Devices & Services** > **Add Integration**
3. Search for **"IPCom Home Anywhere Blue"**
4. Enter your connection details:
   - **CLI Path**: `ipcom` (or `/config/ipcom`)
   - **Host**: Your IPCom server hostname or IP
   - **Port**: `5000` (default)
   - **Username**: Your IPCom username
   - **Password**: Your IPCom password

Done! Your devices will appear in Home Assistant.

---

## Troubleshooting

### Enable Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.ipcom: debug
```

### Common Errors

| Error | Solution |
|-------|----------|
| "Authentication failed" | Check username and password |
| "Connection failed" | Check host and port, ensure IPCom server is reachable |
| "CLI not found" | Check CLI path points to the `ipcom` folder |
| Devices not appearing | Check `devices.yaml` configuration |

### Test CLI Manually

```bash
# SSH into Home Assistant and test the CLI
cd /config/ipcom
python3 ipcom_cli.py status --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS
```

---

## CLI Commands (Optional)

The CLI can also be used standalone for testing or scripting:

```bash
# Check status
python3 ipcom_cli.py status --host HOST --port 5000 --username USER --password PASS

# Control lights
python3 ipcom_cli.py on kitchen --host HOST ...
python3 ipcom_cli.py off kitchen --host HOST ...
python3 ipcom_cli.py dim living_room 50 --host HOST ...

# Watch live updates (JSON output)
python3 ipcom_cli.py watch --json --host HOST ...
```

---

## Device Configuration Reference

### Lights

```yaml
lights:
  device_name:
    module: 3          # Module number (1-16)
    output: 4          # Output channel (1-8)
    type: switch       # "switch" or "dimmer"
    display_name: "Kitchen Light"
```

### Shutters (Dual-Relay)

Each physical shutter needs **two entries** (up relay + down relay):

```yaml
shutters:
  my_shutter_down:
    module: 5
    output: 1
    relay_role: down
    paired_device: my_shutter_up

  my_shutter_up:
    module: 5
    output: 2
    relay_role: up
    paired_device: my_shutter_down
```

The integration automatically combines paired relays into a single cover entity.

---

## Features

| Feature | Description |
|---------|-------------|
| Automatic reconnection | Exponential backoff, unlimited retries |
| Health monitoring | Detects stale connections |
| Real-time updates | Persistent TCP connection |
| Secure credentials | Configured via UI, not stored in files |

### Supported Device Types

| Type | Module | Description |
|------|--------|-------------|
| Switch | Any | On/off lights |
| Dimmer | Module 6 (EXO DIM) | Dimmable lights (0-100%) |
| Cover | Any | Dual-relay shutters |

---

## Version

**v3.0.0 Beta**

---

## Support

For issues, open a ticket on GitHub.
