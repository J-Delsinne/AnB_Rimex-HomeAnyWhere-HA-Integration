"""Constants for the IPCom integration."""

DOMAIN = "ipcom"

# Configuration keys
CONF_CLI_PATH = "cli_path"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Defaults
DEFAULT_HOST = ""  # No default - user must provide their host
DEFAULT_PORT = 5000

# Entity platforms
PLATFORMS = ["light", "cover"]
