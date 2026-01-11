"""
Data models for HomeAnywhere IPCom protocol.

Based on protocol specification extracted from Home_Anywhere_D.dll decompilation.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Frame:
    """
    Represents a complete IPCom protocol frame.

    Frame Structure:
    ┌─────────┬────┬──────┬────────┬─────────────┬──────────┐
    │  Start  │ To │ From │ Length │    Data     │ Checksum │
    ├─────────┼────┼──────┼────────┼─────────────┼──────────┤
    │  0x23   │ 1B │  1B  │  1B    │ N bytes     │  1 byte  │
    └─────────┴────┴──────┴────────┴─────────────┴──────────┘

    Attributes:
        start: Frame start marker (must be 0x23)
        to: Destination address
        from_: Source address
        length: Length of Data field + 1
        data: Command data (includes command type as first byte)
        checksum: XOR of all bytes in Data field
    """

    start: int  # 0x23 (35 decimal)
    to: int
    from_: int  # 'from' is a keyword, use 'from_'
    length: int
    data: bytes
    checksum: int

    def __post_init__(self):
        """Validate frame after initialization."""
        if self.start != 0x23:
            raise ValueError(f"Invalid start byte: {self.start:#x} (expected 0x23)")

        if len(self.data) + 1 != self.length:
            raise ValueError(
                f"Length mismatch: data={len(self.data)}, length field={self.length}"
            )

    @property
    def command_type(self) -> Optional[int]:
        """Get command type (first byte of data)."""
        return self.data[0] if len(self.data) > 0 else None

    @property
    def total_size(self) -> int:
        """Get total frame size in bytes."""
        return 1 + 1 + 1 + 1 + len(self.data) + 1  # Start + To + From + Length + Data + Checksum

    def to_bytes(self) -> bytes:
        """Serialize frame to bytes."""
        return bytes([self.start, self.to, self.from_, self.length]) + self.data + bytes([self.checksum])

    def __repr__(self) -> str:
        """Human-readable representation."""
        cmd_type = self.command_type
        cmd_name = {
            1: "Connect",
            2: "Disconnect",
            3: "KeepAlive",
            4: "Frame",
            5: "ExoOutputs",
            6: "KeyboardStatus",
            14: "NonSecureConnect",
            35: "TriCom",
        }.get(cmd_type, f"Unknown({cmd_type})")

        return (
            f"Frame(type={cmd_name}, to={self.to}, from={self.from_}, "
            f"length={self.length}, data_len={len(self.data)}, checksum={self.checksum:#04x})"
        )


@dataclass
class StateSnapshot:
    """
    Represents a decoded ExoOutputs state snapshot (Command Type 5).

    The state snapshot contains the current state of all 16 modules,
    with each module having 8 outputs.

    Data Format:
        Byte 0:     Command type (5)
        Byte 1:     Unknown/padding
        Bytes 2-129: Module states (128 bytes = 16 modules × 8 bytes)

    Access Pattern (from decompiled C#):
        value = Outputs[module-1][output-1]
        values[module-1][output-1] = newValue

    Attributes:
        raw: Raw 130-byte data from frame
        outputs: 2D array [16 modules][8 outputs] with byte values (0-255)
        timestamp: When this snapshot was received
    """

    raw: bytes
    outputs: list[list[int]] = field(default_factory=list)
    timestamp: Optional[float] = None

    def __post_init__(self):
        """Parse raw data into outputs array if not already provided."""
        if not self.outputs and len(self.raw) >= 130:
            # Parse 16 modules × 8 bytes per module
            self.outputs = []
            for module_idx in range(16):
                offset = 2 + (module_idx * 8)
                module_data = list(self.raw[offset : offset + 8])
                self.outputs.append(module_data)

    def get_value(self, module: int, output: int) -> int:
        """
        Get state of specific output.

        Args:
            module: Module number (1-16)
            output: Output number (1-8)

        Returns:
            Byte value (0-255)

        Raises:
            ValueError: If module or output number is out of range
        """
        if not (1 <= module <= 16):
            raise ValueError(f"Invalid module number: {module} (must be 1-16)")
        if not (1 <= output <= 8):
            raise ValueError(f"Invalid output number: {output} (must be 1-8)")

        return self.outputs[module - 1][output - 1]

    def set_value(self, module: int, output: int, value: int) -> None:
        """
        Set state of specific output (in-memory only).

        Args:
            module: Module number (1-16)
            output: Output number (1-8)
            value: New value (0-255)

        Raises:
            ValueError: If module, output, or value is out of range
        """
        if not (1 <= module <= 16):
            raise ValueError(f"Invalid module number: {module}")
        if not (1 <= output <= 8):
            raise ValueError(f"Invalid output number: {output}")
        if not (0 <= value <= 255):
            raise ValueError(f"Invalid value: {value} (must be 0-255)")

        self.outputs[module - 1][output - 1] = value

    def is_on(self, module: int, output: int) -> bool:
        """
        Check if on/off output is on (for Exo8 modules).

        Args:
            module: Module number (1-16)
            output: Output number (1-8)

        Returns:
            True if output is on (value > 0)
        """
        return self.get_value(module, output) > 0

    def get_dimmer_level(self, module: int, output: int) -> int:
        """
        Get dimmer level as percentage (for ExoDim modules).

        Args:
            module: Module number (1-16)
            output: Output number (1-8)

        Returns:
            0-100 (percentage)
        """
        value = self.get_value(module, output)
        return min(int((value / 255.0) * 100), 100)

    def get_module_values(self, module: int) -> list[int]:
        """
        Get all 8 output values for a module.

        Args:
            module: Module number (1-16)

        Returns:
            List of 8 byte values
        """
        if not (1 <= module <= 16):
            raise ValueError(f"Invalid module number: {module}")

        return self.outputs[module - 1].copy()

    @property
    def timestamp_iso(self) -> str:
        """
        Get timestamp as ISO-8601 formatted string.

        Returns:
            ISO-8601 timestamp string, or current time if timestamp is None
        """
        from datetime import datetime

        if self.timestamp is None:
            # Use current time if no timestamp set
            dt = datetime.now()
        else:
            dt = datetime.fromtimestamp(self.timestamp)

        return dt.isoformat()

    def compare(self, other: "StateSnapshot") -> dict[tuple[int, int], tuple[int, int]]:
        """
        Compare this snapshot with another to find changes.

        Args:
            other: Another StateSnapshot to compare against

        Returns:
            Dict mapping (module, output) to (old_value, new_value) for changed outputs
        """
        changes = {}

        for module_idx in range(16):
            for output_idx in range(8):
                old_val = other.outputs[module_idx][output_idx]
                new_val = self.outputs[module_idx][output_idx]

                if old_val != new_val:
                    # Convert to 1-indexed
                    changes[(module_idx + 1, output_idx + 1)] = (old_val, new_val)

        return changes

    def __repr__(self) -> str:
        """Human-readable representation."""
        non_zero = sum(1 for module in self.outputs for val in module if val > 0)
        return f"StateSnapshot(modules=16, outputs=128, non_zero={non_zero})"


@dataclass
class ElementConfig:
    """
    Represents an element configuration from SOAP discovery.

    This maps SOAP element data to IPCom module/output addresses.

    Attributes:
        id: Element ID from SOAP
        name: Human-readable name
        bus: Bus number (typically 1)
        module: Module number (1-16)
        output: Output number (1-8)
        type: Module type (Exo8, ExoDim, ExoStore, etc.)
    """

    id: int
    name: str
    bus: int
    module: int
    output: int
    type: Optional[str] = None

    @classmethod
    def from_target_extra(cls, id: int, name: str, target_extra: str, module_type: Optional[str] = None):
        """
        Parse ElementConfig from SOAP TargetExtra string.

        Args:
            id: Element ID
            name: Element name
            target_extra: "BusNumber,ModuleNumber,OutputNumber" (e.g., "1,3,4")
            module_type: Optional module type (Exo8, ExoDim, etc.)

        Returns:
            ElementConfig instance
        """
        parts = target_extra.split(",")
        if len(parts) != 3:
            raise ValueError(f"Invalid TargetExtra format: {target_extra}")

        return cls(
            id=id,
            name=name,
            bus=int(parts[0]),
            module=int(parts[1]),
            output=int(parts[2]),
            type=module_type,
        )

    @property
    def frame_offset(self) -> int:
        """
        Calculate frame offset for this element.

        Formula: 2 + ((module - 1) * 8) + (output - 1)
        """
        return 2 + ((self.module - 1) * 8) + (self.output - 1)

    def __repr__(self) -> str:
        """Human-readable representation."""
        type_str = f", type={self.type}" if self.type else ""
        return f"ElementConfig(id={self.id}, name='{self.name}', module={self.module}, output={self.output}{type_str})"
