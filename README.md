# IPCom Home Anywhere Blue - Home Assistant Integration (Unofficial)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/J-Delsinne/AnB_Rimex-HomeAnyWhere-HA-Integration.svg)](https://github.com/J-Delsinne/AnB_Rimex-HomeAnyWhere-HA-Integration/releases)

Control your Home Anywhere Blue home automation system from Home Assistant.

## What This Does

- Controls **lights** (on/off switches and dimmers)
- Controls **shutters/covers** (open, close, stop)
- Real-time status updates via persistent TCP connection
- Automatic reconnection if connection drops

---

## Installation

### Option 1: HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select **"Custom repositories"**
4. Add this repository URL: `https://github.com/J-Delsinne/AnB_Rimex-HomeAnyWhere-HA-Integration`
5. Select category: **"Integration"**
6. Click **"Add"**
7. Search for **"IPCom Home Anywhere Blue"** and install it
8. Restart Home Assistant
9. Configure your devices (see Step 2 below)

### Option 2: Manual Installation

Copy the `custom_components/ipcom` folder to your Home Assistant config directory:

```
/config/
└── custom_components/ipcom/       # Home Assistant integration
    ├── cli/                       # Bundled CLI (auto-installed)
    └── ...
```

**Using SSH/SCP:**
```bash
scp -r custom_components/ipcom user@homeassistant:/config/custom_components/
```

### Step 2: Configure Your Devices

Create `/config/ipcom/devices.yaml` with your devices:

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
| Devices not appearing | Check `devices.yaml` configuration |

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

For issues, open a ticket on [GitHub Issues](https://github.com/J-Delsinne/AnB_Rimex-HomeAnyWhere-HA-Integration/issues).

---

## License

This project is provided as-is for personal use. This is an unofficial integration and is not affiliated with or endorsed by And Solutions or the Home Anywhere Blue brand.
