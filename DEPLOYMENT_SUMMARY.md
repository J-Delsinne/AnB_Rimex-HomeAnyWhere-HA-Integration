## Production Files

### Core Protocol & CLI (5 files)
```
ipcom_tcp_client.py     # TCP client with XOR encryption
models.py               # Data models (StateSnapshot, etc.)
frame_builder.py        # Command frame construction
ipcom_cli.py            # CLI with JSON contract v1.0
devices.yaml            # Device configuration
```

### Home Assistant Integration (8 files)
```
custom_components/ipcom/
  ├── __init__.py
  ├── manifest.json
  ├── const.py
  ├── config_flow.py
  ├── coordinator.py
  ├── light.py          # On/off switches + dimmers
  ├── cover.py          # Dual-relay shutters
  └── translations/en.json
```

### Documentation (3 files)
```
README.md                      # Main documentation
MODULE_6_QUICK_REFERENCE.md    # EXO DIM (Module 6) reference
COVER_DEPLOYMENT.md            # Cover deployment guide
```

### Tools & Reference (3 files)
```
copy_to_ha.sh           # Linux deployment script
copy_to_ha.bat          # Windows deployment script
official_handshake.pcap # Reference capture
```

---

## Deploy to Home Assistant

### Option 1: Using Deployment Script

**Linux/macOS**:
```bash
chmod +x copy_to_ha.sh
./copy_to_ha.sh
```

**Windows**:
```cmd
copy_to_ha.bat
```

### Option 2: Manual Copy

```bash
# Copy CLI and config
scp ipcom_cli.py root@homeassistant:/config/
scp devices.yaml root@homeassistant:/config/

# Copy core protocol files
scp ipcom_tcp_client.py root@homeassistant:/config/
scp models.py root@homeassistant:/config/
scp frame_builder.py root@homeassistant:/config/

# Copy HA integration
scp -r custom_components/ipcom root@homeassistant:/config/custom_components/
```

### Restart Home Assistant
```
Settings → System → Restart
```

---

## Expected Entities

### Lights (17 entities)
**Switches** (15):
- WASBAK, BADKAMER, DOUCHE, KEUKEN, KELDER
- BUITEN, SLAAPKAMER 2, TRAP, VERDIEP
- BADKAMER BOVEN, SLAAPKAMER 1, BUREAU, NACHTHAL
- LIVING, GARAGE

**Dimmers** (2):
- EETKAMER (Module 6, Output 1)
- SALON (Module 6, Output 2)

### Covers (4 entities)
- ROLLUIK SAL LINKS (Module 5, Outputs 1+2)
- ROLLUIK SAL RECHTS (Module 5, Outputs 3+4)
- ROLLUIK EETKAMER (Module 5, Outputs 5+6)
- ROLLUIK KEUKEN (Module 5, Outputs 7+8)

**Total**: 21 entities

---

## Verification Tests

### 1. CLI Status Test
```bash
python ipcom_cli.py status --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS --json
```
**Expected**: Valid JSON with all 25 devices (17 lights, 8 shutter relays)

### 2. Dimmer Control Test
```bash
python ipcom_cli.py dim salon 50 --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS
```
**Expected**: `✔ SALON dimmed to 50% (Module 6, Output 2)`

### 3. Shutter Relay Metadata Test
```bash
python ipcom_cli.py status --json | grep -A 3 "relay_role"
```
**Expected**: All shutter devices have `relay_role: up/down` and `paired_device`

### 4. Home Assistant Integration Test
After deployment:
1. Open Home Assistant
2. Settings → Devices & Services → Add Integration
3. Search for "IPCom Home Anywhere Blue"
4. Configure with:
   - CLI Path: `ipcom` (or `/config/ipcom`)
   - Host: Your IPCom hostname or IP address
   - Port: `5000`
   - Username: Your IPCom username
   - Password: Your IPCom password
5. Verify:
   - ✅ 17 light entities appear
   - ✅ 4 cover entities appear
   - ✅ Dimmer sliders work (EETKAMER, SALON)
   - ✅ Cover controls work (open/close/stop)

---

## Key Features

### Dual-Relay Shutter Control
Each cover entity controls TWO relays safely:
- **UP relay**: Opens shutter
- **DOWN relay**: Closes shutter
- **Safety**: UP=1 & DOWN=1 NEVER occurs
- **STOP**: Both relays OFF

### Module 6 (EXO DIM) Support
- Uses 0-100 value range (not 0-255)
- Proper brightness scaling in HA (0-255 display)
- Full dimming control via `dim` command

### CLI JSON Contract v1.0
Stable, documented interface:
- Home Assistant reads device state via `status --json`
- Commands executed via `on`, `off`, `dim` subcommands
- No direct protocol/socket manipulation in HA

---

## Troubleshooting

### CLI not working
```bash
# Test connection
python ipcom_cli.py status --host YOUR_HOST --port 5000 --username YOUR_USER --password YOUR_PASS

# Check devices.yaml exists
ls -la devices.yaml

# Verify Python 3
python3 --version
```

### Home Assistant integration not loading
```bash
# Check logs
tail -f /config/home-assistant.log | grep ipcom

# Verify files copied
ls -la /config/ipcom_cli.py
ls -la /config/custom_components/ipcom/

# Check Python command in const.py
cat /config/custom_components/ipcom/const.py | grep CLI_PYTHON
```

### Covers not appearing
```bash
# Verify relay metadata in JSON
python ipcom_cli.py status --json | grep relay_role

# Check cover.py loaded
grep "Creating dual-relay cover" /config/home-assistant.log
```

---

## Architecture Summary

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

**Separation of Concerns**:
- HA integration ↔ CLI JSON contract (stable, versioned)
- CLI ↔ Protocol layer (encapsulated)
- No protocol parsing in Home Assistant code

---