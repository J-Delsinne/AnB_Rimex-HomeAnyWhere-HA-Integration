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

## Quick Start

### Step 1: Install via HACS

1. Open **HACS** in Home Assistant
2. Click the three dots menu (top right) → **Custom repositories**
3. Add: `https://github.com/J-Delsinne/AnB_Rimex-HomeAnyWhere-HA-Integration`
4. Select category: **Integration** → Click **Add**
5. Search for **"IPCom Home Anywhere Blue"** and click **Download**
6. **Restart Home Assistant**

### Step 2: Configure Your Devices

Create the device configuration file at `/config/ipcom/devices.yaml`:

**Option A: Using File Editor Add-on (recommended)**
1. Install the **File Editor** add-on from the Add-on Store if you haven't already
2. Open File Editor and navigate to the `/config/` folder
3. Create a new folder called `ipcom`
4. Open `/config/custom_components/ipcom/cli/devices.example.yaml` and copy its contents
5. Create a new file `/config/ipcom/devices.yaml` and paste the contents
6. Edit with your device configuration

**Option B: Using SSH**
```bash
mkdir -p /config/ipcom
cp /config/custom_components/ipcom/cli/devices.example.yaml /config/ipcom/devices.yaml
```

Edit `/config/ipcom/devices.yaml` with your actual device configuration.

> **Note:** The `devices.yaml` file is stored in `/config/ipcom/` (outside the integration folder) so it won't be overwritten when you update the integration via HACS.
>
> Find the mapping info in the official desktop Home Anywhere application (IPCOM/Installer credentials needed).

Example configuration:

```yaml
lights:
  kitchen_light:
    module: 1
    output: 1
    type: switch
    display_name: "Kitchen Light"

  living_room:
    module: 6
    output: 2
    type: dimmer
    display_name: "Living Room"

shutters:
  # Each shutter needs TWO relays (up and down)
  shutter_kitchen_d:
    module: 5
    output: 7
    type: switch
    display_name: "Kitchen Shutter"
    relay_role: down
    paired_device: shutter_kitchen_u

  shutter_kitchen_u:
    module: 5
    output: 8
    type: switch
    display_name: "Kitchen Shutter"
    relay_role: up
    paired_device: shutter_kitchen_d
```

### Step 3: Add the Integration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"IPCom Home Anywhere Blue"**
3. Enter your connection details:
   - **Host**: Your IPCom server hostname or IP
   - **Port**: `5000` (default)
   - **Username**: Your IPCom username
   - **Password**: Your IPCom password

Done! Your devices will appear in Home Assistant.

---

## Manual Installation

If you prefer not to use HACS:

1. Download the latest release from [GitHub Releases](https://github.com/J-Delsinne/AnB_Rimex-HomeAnyWhere-HA-Integration/releases)
2. Copy `custom_components/ipcom/` to your Home Assistant `/config/custom_components/` directory
3. Restart Home Assistant
4. Follow Steps 2 and 3 above

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

Each physical shutter requires **two entries** - one for each relay:

```yaml
shutters:
  my_shutter_down:
    module: 5
    output: 1
    type: switch
    relay_role: down
    paired_device: my_shutter_up
    display_name: "My Shutter"

  my_shutter_up:
    module: 5
    output: 2
    type: switch
    relay_role: up
    paired_device: my_shutter_down
    display_name: "My Shutter"
```

The integration automatically combines paired relays into a single cover entity.

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
| Devices not appearing | Verify `/config/ipcom/devices.yaml` exists and is correctly configured |

---

## Features

| Feature | Description |
|---------|-------------|
| One-click HACS install | No manual file copying required |
| Automatic reconnection | Exponential backoff with unlimited retries |
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

**v3.2.0 Beta**

---

## Support

For issues, open a ticket on [GitHub Issues](https://github.com/J-Delsinne/AnB_Rimex-HomeAnyWhere-HA-Integration/issues).

---

## License

This project is provided as-is for personal use. This is an unofficial integration and is not affiliated with or endorsed by And Solutions or the Home Anywhere Blue brand.
