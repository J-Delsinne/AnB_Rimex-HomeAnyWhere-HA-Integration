#!/usr/bin/env python3
"""
Frame and Command builders for HomeAnywhere IPCom protocol.

Based on reverse engineering of Home_Anywhere_D.dll
"""

def build_exo_set_values_frame(
    from_addr: int,
    to_addr: int,
    exo_number: int,
    values: list[int],
    bus_number: int = 1
) -> bytes:
    """
    Build ExoSetValuesFrame to control device outputs.

    Args:
        from_addr: Source address (typically 0)
        to_addr: Destination address (bus_address + exo_number - 1)
        exo_number: EXO module number (1-16)
        values: 8-byte array of output values (0x00=OFF, 0xFF=ON, 0x01-0xFE=dimming)
        bus_number: Bus number (1 or 2)

    Returns:
        Complete frame bytes ready to encrypt and send

    Frame Structure:
        [Optional: BusNumber (1)] [Start=0x23] [To] [From] [Length] [Data] [Checksum]

    Data Structure for ExoSetValues:
        [0x01] [8 output values]
    """
    if len(values) != 8:
        raise ValueError(f"values must be 8 bytes, got {len(values)}")

    if not all(0 <= v <= 255 for v in values):
        raise ValueError("All values must be 0-255")

    # Build frame data: [0x01] + [8 output values]
    data = bytes([0x01] + values)

    # Calculate checksum (XOR of all data bytes)
    checksum = 0
    for b in data:
        checksum ^= b

    # Build complete frame
    frame = bytearray()

    # Add bus number if not bus 0
    if bus_number != 0:
        frame.append(bus_number)

    # Frame structure
    frame.append(0x23)  # Start marker
    frame.append(to_addr)
    frame.append(from_addr)
    frame.append(len(data) + 1)  # Length = data length + 1 (as per Frame.cs line 60)
    frame.extend(data)
    frame.append(checksum)

    return bytes(frame)


def build_frame_request_command(frame: bytes) -> bytes:
    """
    Wrap a frame in FrameRequestCommand.

    Args:
        frame: Complete frame bytes

    Returns:
        FrameRequestCommand bytes (ready to encrypt)

    Structure:
        [ID=0x04] [Version=0x01] [Frame bytes...]
    """
    return bytes([0x04, 0x01]) + frame


def build_exo_outputs_request_command() -> bytes:
    """
    Build ExoOutputsRequestCommand to request device status.

    Returns:
        Command bytes (ready to encrypt)

    Structure:
        [ID=0x05] [Version=0x01]
    """
    return bytes([0x05, 0x01])


# Convenience functions for common operations

def set_output(
    module: int,
    output: int,
    value: int,
    bus_address: int = 60,
    bus_number: int = 2  # CRITICAL: Default to bus 2 (discovered from official app)
) -> bytes:
    """
    Build command to set a single output value.

    ⚠️ WARNING - DEPRECATED: This function has a critical bug!
    ==========================================
    This function sends [0,0,0,0,0,0,0,0] for all outputs except the target,
    which TURNS OFF all other outputs in the module!

    DO NOT USE THIS FUNCTION. Use IPComClient.set_value() instead, which:
    1. Reads current state from StateSnapshot
    2. Modifies only the target output
    3. Sends all 8 values preserving others

    This matches the official app behavior (see reverse engineering findings).

    Args:
        module: Module number (1-16)
        output: Output number (1-8)
        value: Output value (0=OFF, 255=ON, 1-254=dimming level)
        bus_address: Base bus address (typically 60)
        bus_number: Bus number (default 2 - this is correct for most setups)

    Returns:
        Complete FrameRequestCommand ready to encrypt and send
    """
    if not (1 <= module <= 16):
        raise ValueError(f"module must be 1-16, got {module}")
    if not (1 <= output <= 8):
        raise ValueError(f"output must be 1-8, got {output}")
    if not (0 <= value <= 255):
        raise ValueError(f"value must be 0-255, got {value}")

    # ❌ BUG: Creates array of zeros, turning off all other outputs!
    # This causes Issue #1: "Turning on one light turns off previously active light"
    # The official app maintains module state and modifies only the target output.
    values = [0] * 8
    values[output - 1] = value

    # Calculate destination address
    to_addr = bus_address + (module - 1)

    # Build frame
    frame = build_exo_set_values_frame(
        from_addr=0,
        to_addr=to_addr,
        exo_number=module,
        values=values,
        bus_number=bus_number
    )

    # Wrap in FrameRequestCommand
    return build_frame_request_command(frame)


def turn_on(module: int, output: int, **kwargs) -> bytes:
    """
    Turn output ON.

    ⚠️ DEPRECATED: Use IPComClient.turn_on() instead to preserve other outputs.

    For regular modules: Uses 255 (full power)
    For Module 6 (EXO DIM): Uses 100 (100% brightness)
    """
    if module == 6:
        # EXO DIM: 100 = 100% brightness
        value = 100
    else:
        # Regular outputs: 255 = ON
        value = 255

    return set_output(module, output, value, **kwargs)


def turn_off(module: int, output: int, **kwargs) -> bytes:
    """
    Turn output OFF (0).

    ⚠️ DEPRECATED: Use IPComClient.turn_off() instead to preserve other outputs.
    """
    return set_output(module, output, 0, **kwargs)


def set_dimmer(module: int, output: int, percentage: int, **kwargs) -> bytes:
    """
    Set dimmer to percentage (0-100).

    ⚠️ DEPRECATED: Use IPComClient.set_dimmer() instead to preserve other outputs.

    IMPORTANT: Module 6 (EXO DIM) uses raw 0-100 values, NOT 0-255!
    Regular modules use 0/255 for ON/OFF, but EXO DIM uses percentage directly.

    Args:
        module: Module number (1-16)
        output: Output number (1-8)
        percentage: Dimmer level 0-100
        **kwargs: Additional parameters (bus_address, bus_number)

    Returns:
        Complete FrameRequestCommand ready to encrypt and send
    """
    if not (0 <= percentage <= 100):
        raise ValueError(f"percentage must be 0-100, got {percentage}")

    # Module 6 (EXO DIM) uses 0-100 values directly
    # See: EXO_DIM_STRUCTURE.md - "Dimmer Value Encoding"
    if module == 6:
        # EXO DIM: Send percentage as-is (0-100)
        value = percentage
    else:
        # Regular modules: Convert percentage to 0-255 range
        value = int((percentage / 100.0) * 255)

    return set_output(module, output, value, **kwargs)
