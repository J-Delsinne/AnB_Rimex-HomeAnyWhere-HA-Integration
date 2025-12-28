"""Constants for the IPCom integration."""

DOMAIN = "ipcom"

# Configuration keys
CONF_CLI_PATH = "cli_path"

# CLI command configuration
CLI_SCRIPT = "ipcom_cli.py"
CLI_PYTHON = "python3"  # Use python3 for Linux/Home Assistant compatibility

# Default configuration
DEFAULT_HOST = "megane-david.dyndns.info"
DEFAULT_PORT = 5000
DEFAULT_SCAN_INTERVAL = 10  # seconds

# Entity platforms
PLATFORMS = ["light", "cover"]

# CLI JSON contract version
JSON_CONTRACT_VERSION = "1.0"
