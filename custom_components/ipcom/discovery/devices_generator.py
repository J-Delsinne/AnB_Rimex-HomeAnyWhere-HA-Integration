"""
Devices.yaml generator from HomeAnywhere site configuration.

This module converts HomeAnywhere site data into a devices.yaml file
compatible with the IPCom Home Assistant integration.

Uses GraphicType from Home Anywhere Blue application to automatically
map devices to the correct Home Assistant platform (light, switch, cover).
"""

import re
from dataclasses import dataclass, field
from typing import Optional

# Handle imports for both direct execution and module execution
try:
    from homeanywhere_api import FlashSite, FlashIPCom, FlashOutputModule, FlashMapElement
except ImportError:
    from .homeanywhere_api import FlashSite, FlashIPCom, FlashOutputModule, FlashMapElement

# Import GraphicType mapping from const
try:
    from const import GRAPHIC_TYPE_MAPPING, DEFAULT_GRAPHIC_TYPE_MAPPING
except ImportError:
    try:
        from ..const import GRAPHIC_TYPE_MAPPING, DEFAULT_GRAPHIC_TYPE_MAPPING
    except ImportError:
        # Fallback definitions for standalone execution
        GRAPHIC_TYPE_MAPPING = {
            "OutputLightBulb": {"platform": "light", "device_class": None, "icon": None},
            "OutputLightBulbEconomic": {"platform": "light", "device_class": None, "icon": "mdi:lightbulb-fluorescent-tube"},
            "OutputSocket": {"platform": "switch", "device_class": "outlet", "icon": None},
            "OutputTelevision": {"platform": "switch", "device_class": None, "icon": "mdi:television"},
            "OutputWashMachine": {"platform": "switch", "device_class": None, "icon": "mdi:washing-machine"},
            "OutputDishWasher": {"platform": "switch", "device_class": None, "icon": "mdi:dishwasher"},
            "OutputCoffeeMachine": {"platform": "switch", "device_class": None, "icon": "mdi:coffee-maker"},
            "OutputHeater": {"platform": "switch", "device_class": None, "icon": "mdi:radiator"},
            "OutputBoiler": {"platform": "switch", "device_class": None, "icon": "mdi:water-boiler"},
            "OutputShutterUp": {"platform": "cover", "device_class": "shutter", "relay_role": "up"},
            "OutputShutterDown": {"platform": "cover", "device_class": "shutter", "relay_role": "down"},
            "OutputBlindUp": {"platform": "cover", "device_class": "blind", "relay_role": "up"},
            "OutputBlindDown": {"platform": "cover", "device_class": "blind", "relay_role": "down"},
        }
        DEFAULT_GRAPHIC_TYPE_MAPPING = {"platform": "light", "device_class": None, "icon": None}


@dataclass
class DeviceEntry:
    """Represents a device entry for devices.yaml."""
    key: str
    module: int
    output: int
    type: str  # light, dimmer, switch
    display_name: str
    description: str
    # Additional fields from GraphicType mapping
    graphic_type: Optional[str] = None
    device_class: Optional[str] = None
    icon: Optional[str] = None
    # Shutter-specific fields
    relay_role: Optional[str] = None  # up, down
    paired_device: Optional[str] = None


@dataclass
class ShutterPair:
    """Represents a paired shutter (up + down relays)."""
    name: str
    down_module: int
    down_output: int
    up_module: int
    up_output: int


def sanitize_key(name: str) -> str:
    """Convert a display name to a valid YAML key."""
    # Convert to lowercase and replace spaces/special chars with underscores
    key = name.lower()
    key = re.sub(r'[^a-z0-9]+', '_', key)
    key = key.strip('_')
    return key


def detect_shutter_pairs(modules: list[FlashOutputModule]) -> list[ShutterPair]:
    """
    Detect shutter pairs from ExoStore modules.

    ExoStore outputs come in pairs:
    - Odd outputs (1, 3, 5, 7) = Down direction (D)
    - Even outputs (2, 4, 6, 8) = Up direction (M = Monter)

    Returns list of ShutterPair objects.
    """
    pairs = []

    for module in modules:
        if module.type != "ExoStore":
            continue

        # Process outputs in pairs
        for i in range(0, 8, 2):
            down_name = module.outputs[i] if i < len(module.outputs) else ""
            up_name = module.outputs[i + 1] if i + 1 < len(module.outputs) else ""

            if not down_name and not up_name:
                continue

            # Extract base name (remove D/M suffix if present)
            base_name = down_name or up_name
            for suffix in [" D", " M", "_D", "_M"]:
                if base_name.endswith(suffix):
                    base_name = base_name[:-2]
                    break

            pairs.append(ShutterPair(
                name=base_name,
                down_module=module.number,
                down_output=i + 1,
                up_module=module.number,
                up_output=i + 2,
            ))

    return pairs


def generate_devices_yaml(site: FlashSite, ipcom: FlashIPCom) -> str:
    """
    Generate devices.yaml content from site configuration.

    Args:
        site: FlashSite with full configuration
        ipcom: FlashIPCom to generate config for

    Returns:
        YAML content as string
    """
    lines = []

    # Header
    lines.append("# =====================================================")
    lines.append(f"# Home Anywhere Blue - Device Configuration")
    lines.append(f"# Site: {site.name or 'Unknown'}")
    lines.append(f"# IPCom: {ipcom.name} ({ipcom.local_address}:{ipcom.local_port})")
    lines.append(f"# Generated automatically from HomeAnywhere cloud")
    lines.append("# =====================================================")
    lines.append("")
    lines.append("# Connection info (for reference, configure in Home Assistant):")
    lines.append(f"#   Local:  {ipcom.local_address}:{ipcom.local_port}")
    lines.append(f"#   Remote: {ipcom.remote_address}:{ipcom.remote_port}")
    lines.append(f"#   Bus:    {ipcom.bus1}")
    lines.append("")

    # Build lookup of map elements for widget type info
    map_lookup: dict[tuple[int, int], FlashMapElement] = {}
    for elem in site.map_elements:
        config = elem.parse_config()
        if config:
            _, module, output = config
            map_lookup[(module, output)] = elem

    # Collect lights (Exo8 and ExoDim modules)
    lights: list[DeviceEntry] = []

    for module in ipcom.modules:
        if module.type not in ("Exo8", "ExoDim"):
            continue

        for output_idx, output_name in enumerate(module.outputs):
            if not output_name:
                continue

            output_num = output_idx + 1
            map_elem = map_lookup.get((module.number, output_num))

            # Determine type based on module type and widget type
            if module.type == "ExoDim":
                device_type = "dimmer"
            elif map_elem and map_elem.widget_type == "Dimmable":
                device_type = "dimmer"
            else:
                device_type = "light"

            lights.append(DeviceEntry(
                key=sanitize_key(output_name),
                module=module.number,
                output=output_num,
                type=device_type,
                display_name=output_name,
                description=f"Module {module.number} ({module.type}) - Output {output_num}",
            ))

    # Generate lights section
    if lights:
        lines.append("# =====================================================")
        lines.append("# LIGHTS")
        lines.append("# =====================================================")
        lines.append("")
        lines.append("lights:")

        for light in lights:
            lines.append(f"  {light.key}:")
            lines.append(f"    module: {light.module}")
            lines.append(f"    output: {light.output}")
            lines.append(f"    type: {light.type}")
            lines.append(f'    display_name: "{light.display_name}"')
            lines.append(f'    description: "{light.description}"')
            lines.append("")

    # Detect and generate shutter pairs
    shutter_pairs = detect_shutter_pairs(ipcom.modules)

    if shutter_pairs:
        lines.append("")
        lines.append("# =====================================================")
        lines.append("# SHUTTERS / ROLLER SHUTTERS")
        lines.append("# =====================================================")
        lines.append("#")
        lines.append("# Each shutter uses TWO relays:")
        lines.append("#   - relay_role: down = closing direction")
        lines.append("#   - relay_role: up   = opening direction")
        lines.append("#")
        lines.append("# =====================================================")
        lines.append("")
        lines.append("shutters:")

        for pair in shutter_pairs:
            base_key = sanitize_key(pair.name)
            down_key = f"shutter_{base_key}_d"
            up_key = f"shutter_{base_key}_u"

            # Down relay
            lines.append(f"  {down_key}:")
            lines.append(f"    module: {pair.down_module}")
            lines.append(f"    output: {pair.down_output}")
            lines.append(f"    type: switch")
            lines.append(f'    display_name: "{pair.name}"')
            lines.append(f'    description: "{pair.name} - DOWN relay"')
            lines.append(f"    relay_role: down")
            lines.append(f"    paired_device: {up_key}")
            lines.append("")

            # Up relay
            lines.append(f"  {up_key}:")
            lines.append(f"    module: {pair.up_module}")
            lines.append(f"    output: {pair.up_output}")
            lines.append(f"    type: switch")
            lines.append(f'    display_name: "{pair.name}"')
            lines.append(f'    description: "{pair.name} - UP relay"')
            lines.append(f"    relay_role: up")
            lines.append(f"    paired_device: {down_key}")
            lines.append("")

    return "\n".join(lines)


def generate_devices_config(site: FlashSite, ipcom: FlashIPCom) -> dict:
    """
    Generate device configuration as a dictionary for storage in config entry.

    This is the preferred method for Home Assistant integration as it stores
    the configuration in HA's config entry system, which survives HACS updates.

    Uses GraphicType from Home Anywhere Blue to automatically categorize devices
    into the correct Home Assistant platforms (light, switch, cover).

    Args:
        site: FlashSite with full configuration
        ipcom: FlashIPCom to generate config for

    Returns:
        Dictionary with 'lights', 'switches', and 'shutters' keys containing device configs
    """
    config = {
        "lights": {},
        "switches": {},
        "shutters": {},
    }

    # Build lookup of map elements for GraphicType and WidgetType info
    map_lookup: dict[tuple[int, int], FlashMapElement] = {}
    for elem in site.map_elements:
        parsed = elem.parse_config()
        if parsed:
            _, module, output = parsed
            map_lookup[(module, output)] = elem

    # Process Exo8 and ExoDim modules (lights and switches)
    for module in ipcom.modules:
        if module.type not in ("Exo8", "ExoDim"):
            continue

        for output_idx, output_name in enumerate(module.outputs):
            if not output_name:
                continue

            output_num = output_idx + 1
            map_elem = map_lookup.get((module.number, output_num))

            # Get GraphicType from map element, default to OutputLightBulb
            graphic_type = map_elem.graphic_type if map_elem else "OutputLightBulb"
            
            # Get platform mapping based on GraphicType
            mapping = GRAPHIC_TYPE_MAPPING.get(graphic_type, DEFAULT_GRAPHIC_TYPE_MAPPING)
            platform = mapping.get("platform", "light")

            # Determine if dimmable (ExoDim module or Dimmable widget type)
            is_dimmable = (
                module.type == "ExoDim" or 
                (map_elem and map_elem.widget_type == "Dimmable")
            )

            # Set device type based on platform and dimmability
            if platform == "light" and is_dimmable:
                device_type = "dimmer"
            elif platform == "light":
                device_type = "light"
            else:
                device_type = platform  # switch, cover, etc.

            key = sanitize_key(output_name)
            
            device_entry = {
                "module": module.number,
                "output": output_num,
                "type": device_type,
                "display_name": output_name,
                "description": f"Module {module.number} ({module.type}) - Output {output_num}",
                "graphic_type": graphic_type,
            }
            
            # Add device_class if specified
            if mapping.get("device_class"):
                device_entry["device_class"] = mapping["device_class"]
            
            # Add icon if specified
            if mapping.get("icon"):
                device_entry["icon"] = mapping["icon"]

            # Add to appropriate platform bucket
            if platform == "light":
                config["lights"][key] = device_entry
            elif platform == "switch":
                config["switches"][key] = device_entry
            # Note: covers from Exo8/ExoDim are rare, usually from ExoStore

    # Detect and add shutter pairs from ExoStore modules
    shutter_pairs = detect_shutter_pairs(ipcom.modules)

    for pair in shutter_pairs:
        base_key = sanitize_key(pair.name)
        down_key = f"shutter_{base_key}_d"
        up_key = f"shutter_{base_key}_u"

        # Down relay
        config["shutters"][down_key] = {
            "module": pair.down_module,
            "output": pair.down_output,
            "type": "switch",
            "display_name": pair.name,
            "description": f"{pair.name} - DOWN relay",
            "relay_role": "down",
            "paired_device": up_key,
        }

        # Up relay
        config["shutters"][up_key] = {
            "module": pair.up_module,
            "output": pair.up_output,
            "type": "switch",
            "display_name": pair.name,
            "description": f"{pair.name} - UP relay",
            "relay_role": "up",
            "paired_device": down_key,
        }

    return config
