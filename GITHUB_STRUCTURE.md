# GitHub Repository Structure

This document shows the exact structure to push to your private GitHub repository.

---

## Files to Include in Git Repository

```
home-anywhere-ipcom/                    # Your repo name
│
├── .gitignore                          # Git ignore rules
├── README.md                            # Main documentation
├── DEPLOYMENT_SUMMARY.md                # Deployment guide
├── MODULE_6_QUICK_REFERENCE.md          # EXO DIM reference
├── COVER_DEPLOYMENT.md                  # Shutter guide
├── CODEBASE_SANITATION_REPORT.md        # Cleanup report (optional)
│
├── ipcom/                               # CLI & Core Protocol
│   ├── ipcom_cli.py                    # CLI interface (JSON contract)
│   ├── ipcom_tcp_client.py             # TCP client with encryption
│   ├── models.py                        # Data models (StateSnapshot, etc.)
│   ├── frame_builder.py                 # Command frame construction
│   └── devices.yaml                     # Device configuration
│
└── custom_components/ipcom/             # Home Assistant Integration
    ├── __init__.py                      # Component initialization
    ├── manifest.json                    # HA component manifest
    ├── const.py                         # Constants
    ├── config_flow.py                   # Configuration UI
    ├── coordinator.py                   # Data coordinator
    ├── light.py                         # Light platform (switches + dimmers)
    ├── cover.py                         # Cover platform (dual-relay shutters)
    └── translations/
        └── en.json                      # English translations
```

---

## Files Excluded (via .gitignore)

These files are NOT pushed to GitHub:

```
# Development/Testing (local only)
test_control.py
debug_snapshot.py
copy_to_ha.sh
copy_to_ha.bat
official_handshake.pcap

# Archive/Reference (local only)
ha_reverse/

# Generated artifacts
__pycache__/
*.pyc
*.log
.venv/
.claude/
```

---

## Git Commands to Push

### First-Time Setup

```bash
# Initialize git repository (if not already done)
git init

# Add all files (respects .gitignore)
git add .

# Commit
git commit -m "Initial commit: IPCom Home Anywhere Blue integration

- Complete Home Assistant integration (lights + covers)
- CLI interface with JSON contract v1.0
- Module 6 (EXO DIM) dimmer support
- Dual-relay shutter control with safety layer
- Full protocol implementation with XOR encryption"

# Add your private GitHub repository
git remote add origin https://github.com/YOUR_USERNAME/home-anywhere-ipcom.git

# Push to GitHub
git push -u origin main
```

### Subsequent Updates

```bash
# Check status
git status

# Add changed files
git add .

# Commit
git commit -m "Your commit message"

# Push
git push
```

---

## Repository Contents Summary

### Total Files in Git: ~20 files

**Core Protocol (5 files)**:
- ipcom/ipcom_cli.py
- ipcom/ipcom_tcp_client.py
- ipcom/models.py
- ipcom/frame_builder.py
- ipcom/devices.yaml

**Home Assistant (8 files)**:
- custom_components/ipcom/*.py (7 files)
- custom_components/ipcom/translations/en.json

**Documentation (5 files)**:
- README.md
- DEPLOYMENT_SUMMARY.md
- MODULE_6_QUICK_REFERENCE.md
- COVER_DEPLOYMENT.md
- CODEBASE_SANITATION_REPORT.md (optional)

**Config (1 file)**:
- .gitignore

---

## Clone and Deploy Instructions

After pushing to GitHub, anyone can clone and deploy:

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/home-anywhere-ipcom.git
cd home-anywhere-ipcom

# Copy to Home Assistant
scp -r ipcom root@homeassistant:/config/
scp -r custom_components/ipcom root@homeassistant:/config/custom_components/

# Restart Home Assistant
# Then add integration via UI
```

---

## Important Notes

### devices.yaml Configuration

⚠️ **Before pushing to GitHub**, decide whether to include your `devices.yaml`:

**Option 1: Include with your actual devices** (if private repo)
- Keep your real device configuration
- Others will need to edit it for their setup

**Option 2: Include a template** (if sharing)
- Create `devices.yaml.example` with example devices
- Add `devices.yaml` to `.gitignore`
- Users copy and customize the example

**Recommended for private repo**: Keep your actual `devices.yaml`

### Sensitive Information

✅ **Safe to commit**:
- All Python code (no secrets)
- devices.yaml (just device names/mappings)
- Home Assistant component code

❌ **DO NOT commit**:
- Your actual host/IP if you want it private
- Any passwords (none currently in code)
- PCAP files with network traffic

---

## After Pushing

Your GitHub repository will be clean, well-organized, and ready for:

1. ✅ **Private use**: Your own Home Assistant deployments
2. ✅ **Sharing**: With others who have Home Anywhere Blue systems
3. ✅ **Backup**: Safe backup of your integration code
4. ✅ **Version control**: Track changes over time

---

## Example devices.yaml for Sharing

If you want to create a template for others:

```yaml
# devices.yaml.example
lights:
  example_light:
    module: 3
    output: 1
    type: switch
    display_name: "EXAMPLE LIGHT"
    description: "Example on/off switch"

  example_dimmer:
    module: 6
    output: 1
    type: dimmer
    display_name: "EXAMPLE DIMMER"
    description: "Example EXO DIM dimmer"

shutters:
  example_shutter_d:
    module: 5
    output: 1
    type: switch
    display_name: "EXAMPLE SHUTTER D"
    relay_role: down
    paired_device: example_shutter_m

  example_shutter_m:
    module: 5
    output: 2
    type: switch
    display_name: "EXAMPLE SHUTTER M"
    relay_role: up
    paired_device: example_shutter_d
```

Then in README.md, add instructions to copy and customize it.

---

**Ready to push to GitHub!** 🚀
