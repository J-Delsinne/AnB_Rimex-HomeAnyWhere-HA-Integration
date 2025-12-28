"""
HomeAnywhere IPCom TCP Client

Production-ready TCP client for HomeAnywhere IPCom protocol (port 5000).
Based on protocol specification extracted from Home_Anywhere_D.dll decompilation.

Protocol Reference: PROTOCOL_SPECIFICATION.md

Author: Claude Code
Date: 2025-12-27
"""

import socket
import time
import logging
from typing import Optional, Callable, Iterator
from dataclasses import dataclass

from models import Frame, StateSnapshot


class IPComEncryption:
    """
    XOR-based encryption for IPCom protocol.

    Based on TCPSecureCommunication.cs from Home_Anywhere_D.dll decompilation.
    Implements both single-key (PRIVATE_KEY2) and dual-key (PRIVATE_KEY + PUBLIC_KEY) modes.
    """

    # PRIVATE_KEY (256 bytes) - from TCPSecureCommunication.cs:17-45 (CORRECTED)
    PRIVATE_KEY = bytes([
        83, 131, 251, 50, 127, 126, 154, 233, 1, 179,
        127, 128, 6, 207, 57, 38, 111, 93, 37, 91,
        30, 38, 40, 196, 179, 120, 4, 172, 159, 11,
        174, 157, 87, 172, 78, 130, 14, 180, 186, 108,
        39, 56, 10, 113, 155, 225, 247, 253, 20, 204,
        20, 13, 113, 229, 184, 247, 124, 203, 224, 11,
        4, 120, 177, 127, 43, 234, 133, 65, 149, 34,
        24, 238, 6, 255, 121, 19, 38, 211, 8, 16,
        117, 4, 83, 108, 4, 253, 145, 243, 49, 147,
        182, 20, 227, 83, 246, 206, 110, 195, 116, 254,
        206, 98, 1, 189, 141, 17, 38, 57, 10, 116,
        81, 202, 86, 66, 81, 213, 123, 142, 166, 71,
        220, 127, 116, 9, 144, 143, 154, 242, 12, 116,
        129, 100, 16, 13, 100, 206, 84, 181, 120, 129,
        165, 144, 54, 235, 130, 201, 231, 92, 189, 63,
        59, 41, 211, 47, 34, 110, 111, 36, 221, 251,
        221, 152, 0, 29, 75, 130, 206, 18, 209, 51,
        41, 34, 79, 146, 249, 148, 235, 18, 87, 47,
        250, 48, 199, 241, 157, 114, 202, 141, 37, 235,
        44, 61, 227, 251, 204, 188, 84, 17, 83, 37,
        226, 206, 120, 249, 220, 111, 232, 226, 251, 65,
        60, 237, 111, 154, 177, 243, 114, 120, 2, 204,
        145, 61, 32, 127, 190, 233, 83, 212, 251, 255,
        110, 66, 177, 246, 94, 77, 20, 3, 180, 251,
        47, 83, 122, 188, 158, 167, 206, 142, 202, 8,
        196, 123, 25, 161, 43, 127
    ])

    # PRIVATE_KEY2 (256 bytes) - from TCPSecureCommunication.cs:47-75 (CORRECTED)
    # This is a rotated version of PRIVATE_KEY, used as fallback before public key is set
    PRIVATE_KEY2 = bytes([
        12, 116, 129, 100, 16, 13, 100, 206, 84, 181,
        120, 129, 165, 144, 54, 235, 130, 201, 231, 92,
        189, 63, 59, 41, 211, 47, 34, 110, 111, 36,
        221, 251, 221, 152, 0, 29, 75, 130, 206, 18,
        209, 51, 41, 34, 79, 146, 249, 148, 235, 18,
        87, 47, 250, 48, 199, 241, 157, 114, 202, 141,
        37, 235, 44, 61, 227, 251, 204, 188, 84, 17,
        83, 37, 226, 206, 120, 249, 220, 111, 232, 226,
        251, 65, 60, 237, 111, 154, 177, 243, 114, 120,
        2, 204, 145, 61, 32, 127, 190, 233, 83, 212,
        251, 255, 110, 66, 177, 246, 94, 77, 20, 3,
        180, 251, 47, 83, 122, 188, 158, 167, 206, 142,
        202, 8, 196, 123, 25, 161, 43, 127, 83, 131,
        251, 50, 127, 126, 154, 233, 1, 179, 127, 128,
        6, 207, 57, 38, 111, 93, 37, 91, 30, 38,
        40, 196, 179, 120, 4, 172, 159, 11, 174, 157,
        87, 172, 78, 130, 14, 180, 186, 108, 39, 56,
        10, 113, 155, 225, 247, 253, 20, 204, 20, 13,
        113, 229, 184, 247, 124, 203, 224, 11, 4, 120,
        177, 127, 43, 234, 133, 65, 149, 34, 24, 238,
        6, 255, 121, 19, 38, 211, 8, 16, 117, 4,
        83, 108, 4, 253, 145, 243, 49, 147, 182, 20,
        227, 83, 246, 206, 110, 195, 116, 254, 206, 98,
        1, 189, 141, 17, 38, 57, 10, 116, 81, 202,
        86, 66, 81, 213, 123, 142, 166, 71, 220, 127,
        116, 9, 144, 143, 154, 242
    ])

    def __init__(self):
        """Initialize encryption with default settings."""
        self._public_key: Optional[bytes] = None
        self._secure = True  # Encryption always enabled by default

    def set_public_key(self, public_key: Optional[bytes]):
        """
        Set public key for dual-key encryption mode.

        Args:
            public_key: 128-byte public key from ConnectResponse, or None to use single-key mode

        Raises:
            ValueError: If public key is not 128 bytes
        """
        if public_key is not None and len(public_key) != 128:
            raise ValueError(f"Public key must be 128 bytes, got {len(public_key)}")
        self._public_key = public_key

    def encrypt(self, data: bytes) -> bytes:
        """
        Encrypt data using XOR cipher.

        Based on TCPSecureCommunication.cs:14-36 SendBytes()

        Encryption modes:
        - Before auth (no public key): encrypted = plain XOR PRIVATE_KEY2[pingPong]
        - After auth (has public key):  encrypted = plain XOR PRIVATE_KEY[pingPong] XOR PUBLIC_KEY[pingPong % 128]

        CRITICAL: pingPong state updates with ENCRYPTED byte (not plaintext)

        Args:
            data: Plaintext bytes

        Returns:
            Encrypted bytes
        """
        if not self._secure:
            return data

        result = bytearray(len(data))
        ping_pong = 0  # Reset for each message

        for pos in range(len(data)):
            ping_pong ^= pos
            a = data[pos]

            if self._public_key is not None and len(self._public_key) > 0:
                # Dual-key mode: XOR with both PRIVATE_KEY and PUBLIC_KEY
                encrypted_byte = a ^ self.PRIVATE_KEY[ping_pong] ^ self._public_key[ping_pong % len(self._public_key)]
            else:
                # Single-key mode: XOR with PRIVATE_KEY2 only
                encrypted_byte = a ^ self.PRIVATE_KEY2[ping_pong]

            result[pos] = encrypted_byte
            ping_pong = encrypted_byte  # Update with ENCRYPTED byte

        return bytes(result)

    def decrypt(self, data: bytes) -> bytes:
        """
        Decrypt data using XOR cipher.

        Based on TCPSecureCommunication.cs:104-124 ReceiveBytes()

        CRITICAL: pingPong state updates with ENCRYPTED byte (same as encrypt)
        XOR is symmetric, so decrypt logic is identical to encrypt.

        Args:
            data: Encrypted bytes

        Returns:
            Plaintext bytes
        """
        if not self._secure:
            return data

        result = bytearray(len(data))
        ping_pong = 0  # Reset for each message

        for pos in range(len(data)):
            ping_pong ^= pos
            encrypted_byte = data[pos]

            if self._public_key is not None and len(self._public_key) > 0:
                # Dual-key mode: XOR with both PRIVATE_KEY and PUBLIC_KEY
                plaintext_byte = encrypted_byte ^ self.PRIVATE_KEY[ping_pong] ^ self._public_key[ping_pong % len(self._public_key)]
            else:
                # Single-key mode: XOR with PRIVATE_KEY2 only
                plaintext_byte = encrypted_byte ^ self.PRIVATE_KEY2[ping_pong]

            result[pos] = plaintext_byte
            ping_pong = encrypted_byte  # Update with ENCRYPTED byte (not decrypted!)

        return bytes(result)

    @property
    def is_secure(self) -> bool:
        """Check if encryption is enabled."""
        return self._secure

    @property
    def has_public_key(self) -> bool:
        """Check if public key is set (dual-key mode)."""
        return self._public_key is not None


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class IPComClient:
    """
    TCP client for HomeAnywhere IPCom protocol.

    Features:
    - Robust connection management with exponential backoff
    - Stream fragmentation handling
    - Frame parsing and validation
    - Checksum verification (XOR algorithm)
    - State snapshot decoding
    - Write operations with module addressing

    Protocol Specification:
    - Port: 5000
    - Frame format: Start(0x23), To, From, Length, Data, Checksum
    - Checksum: XOR of all Data bytes
    - State frames: 130 bytes (16 modules × 8 bytes/module)
    """

    # Protocol constants
    FRAME_START_BYTE = 0x23
    DEFAULT_PORT = 5000
    RECV_BUFFER_SIZE = 8192
    SOCKET_TIMEOUT = 5.0  # seconds
    WRITE_RATE_LIMIT = 0.2  # seconds between writes

    # Command types (from ResponseCommandFactory.cs)
    CMD_CONNECT_RESPONSE = 1
    CMD_DISCONNECT_RESPONSE = 2
    CMD_KEEPALIVE_RESPONSE = 3
    CMD_FRAME_RESPONSE = 4
    CMD_EXO_OUTPUTS_RESPONSE = 5  # State snapshot
    CMD_KEYBOARD_STATUS_RESPONSE = 6
    CMD_NONSECURE_CONNECT = 14
    CMD_TRICOM_RESPONSE = 35

    # Reconnection strategy
    RECONNECT_BASE_DELAY = 1.0  # seconds
    RECONNECT_MAX_DELAY = 30.0  # seconds
    RECONNECT_MULTIPLIER = 2.0

    def __init__(self, host: str, port: int = DEFAULT_PORT, debug: bool = False):
        """
        Initialize IPCom client.

        Args:
            host: IPCom device IP address (e.g., "192.168.0.251")
            port: TCP port (default: 5000)
            debug: Enable debug logging
        """
        self.host = host
        self.port = port
        self.debug = debug

        # Logging
        self.logger = logging.getLogger(f"IPComClient({host}:{port})")
        if debug:
            self.logger.setLevel(logging.DEBUG)

        # Connection state
        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._recv_buffer = bytearray()

        # State tracking
        self._latest_snapshot: Optional[StateSnapshot] = None
        self._last_write_time = 0.0
        self._polling_enabled = False
        self._processing = False

        # Encryption and authentication (from AUTH_HANDSHAKE_SPEC.md)
        self._encryption = IPComEncryption()
        self._authenticated = False
        self._username = "ppssecurity"  # From SOAP CheckSiteVersion
        self._password = "667166mm"     # From SOAP CheckSiteVersion
        self._bus_number = 1

        # Callbacks
        self._on_state_snapshot: Optional[Callable[[StateSnapshot], None]] = None
        self._on_frame: Optional[Callable[[Frame], None]] = None
        self._on_connect: Optional[Callable[[], None]] = None
        self._on_disconnect: Optional[Callable[[], None]] = None

    def connect(self) -> bool:
        """
        Establish TCP connection to IPCom device.

        Returns:
            True if connection successful, False otherwise
        """
        if self._connected:
            self.logger.warning("Already connected")
            return True

        try:
            self.logger.info(f"Connecting to {self.host}:{self.port}...")

            # Create socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.SOCKET_TIMEOUT)

            # Connect
            self._socket.connect((self.host, self.port))
            self._connected = True

            self.logger.info("Connection established")

            # Trigger callback
            if self._on_connect:
                self._on_connect()

            return True

        except socket.timeout:
            self.logger.error(f"Connection timeout after {self.SOCKET_TIMEOUT}s")
            self._cleanup_socket()
            return False

        except socket.error as e:
            self.logger.error(f"Connection failed: {e}")
            self._cleanup_socket()
            return False

        except Exception as e:
            self.logger.error(f"Unexpected error during connection: {e}")
            self._cleanup_socket()
            return False

    def disconnect(self):
        """Gracefully disconnect from IPCom device."""
        if not self._connected:
            return

        self.logger.info("Disconnecting...")

        # Send disconnect command (optional, device will handle TCP close)
        try:
            disconnect_frame = self._build_frame(to=1, from_=0, data=bytes([self.CMD_DISCONNECT_RESPONSE]))
            self.send_frame_bytes(disconnect_frame.to_bytes())
        except Exception as e:
            self.logger.debug(f"Error sending disconnect frame: {e}")

        # Close socket
        self._cleanup_socket()

        # Trigger callback
        if self._on_disconnect:
            self._on_disconnect()

        self.logger.info("Disconnected")

    def _cleanup_socket(self):
        """Clean up socket resources."""
        self._connected = False
        self._authenticated = False
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None

    def authenticate(self) -> bool:
        """
        Perform authentication handshake with IPCom.

        CRITICAL FINDING: ConnectRequest must be sent as RAW encrypted data,
        NOT wrapped in a frame! The official app sends 56 bytes raw encrypted,
        and the server rejects framed ConnectRequests with a 7e e3 error.

        Based on:
        - IPCommunication.cs:293-380 ConnectLocal() and ConnectResponded()
        - Wireshark analysis of official app (BREAKTHROUGH_FINDINGS.md)

        Flow:
        1. Send ConnectRequest as RAW encrypted data (56 bytes)
        2. Receive ConnectResponse #1 as RAW encrypted data (56 bytes)
        3. Receive ConnectResponse #2 as RAW encrypted data (135 bytes with public key)
        4. Extract public key from bytes[7:135]
        5. Switch to dual-key encryption mode

        Returns:
            True if authentication successful, False otherwise

        Raises:
            RuntimeError: If not connected
        """
        if not self._connected:
            raise RuntimeError("Not connected - call connect() first")

        if self._authenticated:
            self.logger.warning("Already authenticated")
            return True

        # HARDCODED authentication packet from official app
        # This packet is ALWAYS the same and works universally
        # See CRITICAL_FINDING_HARDCODED_PACKET.md for details
        OFFICIAL_AUTH_PACKET = bytes.fromhex(
            '0da7e127586fcc633d89411daa195b064f59d9594f22daf3192ce7b0cbc67564'
            '628a101efca55fa706b48e945c731d7705daad8ec0aeb27e'
        )

        try:
            self.logger.info("Authenticating with hardcoded official app packet...")

            if self.debug:
                hex_preview = ' '.join(f'{b:02x}' for b in OFFICIAL_AUTH_PACKET[:32])
                self.logger.debug(f"TX (RAW): {hex_preview}... ({len(OFFICIAL_AUTH_PACKET)} bytes total)")

            # Send hardcoded authentication packet
            self._socket.sendall(OFFICIAL_AUTH_PACKET)
            self.logger.debug("Sent authentication packet (56 bytes)")

            # Receive ConnectResponse (135 bytes RAW encrypted with public key)
            self.logger.debug("Waiting for ConnectResponse (135 bytes)...")
            response = self._socket.recv(135)

            if len(response) < 135:
                # Try to receive remaining bytes
                while len(response) < 135:
                    chunk = self._socket.recv(135 - len(response))
                    if not chunk:
                        break
                    response += chunk

            if len(response) != 135:
                self.logger.error(f"ConnectResponse: Expected 135 bytes, got {len(response)}")
                if self.debug and len(response) > 0:
                    hex_dump = ' '.join(f'{b:02x}' for b in response[:64])
                    self.logger.debug(f"RX: {hex_dump}...")

                    # Check for 7e e3 error
                    if len(response) == 2 and response == b'\x7e\xe3':
                        self.logger.error("Received 7e e3 error response!")
                return False

            if self.debug:
                hex_preview = ' '.join(f'{b:02x}' for b in response[:32])
                self.logger.debug(f"RX (RAW): {hex_preview}... (135 bytes)")

            # Decrypt ConnectResponse
            decrypted = self._encryption.decrypt(response)
            cmd_type = decrypted[0]

            if self.debug:
                dec_preview = ' '.join(f'{b:02x}' for b in decrypted[:20])
                self.logger.debug(f"Decrypted: {dec_preview}... (Command type: 0x{cmd_type:02x})")

            if cmd_type != 0x01:
                self.logger.error(f"ConnectResponse: Expected type 0x01, got 0x{cmd_type:02x}")
                return False

            # Extract public key from bytes[7:135]
            public_key = decrypted[7:135]
            self._encryption.set_public_key(public_key)

            if self.debug:
                pk_preview = ' '.join(f'{b:02x}' for b in public_key[:16])
                self.logger.debug(f"Public key extracted: {pk_preview}... (128 bytes)")

            self.logger.info("Received ConnectResponse (135 bytes) - Public key extracted")
            self.logger.info("Switched to dual-key encryption mode (PRIVATE_KEY + PUBLIC_KEY)")

            self._authenticated = True
            self.logger.info("Authentication successful!")
            return True

        except socket.timeout:
            self.logger.error("Authentication timeout - no response received")
            return False
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            if self.debug:
                import traceback
                self.logger.debug(traceback.format_exc())
            return False

    def _build_connect_request(self) -> bytes:
        """
        Build ConnectRequestCommand payload.

        Based on ConnectRequestCommand.cs ToBytes()

        Format (56 bytes total):
        - ID: 1
        - Version: 2
        - Username: "USER:ppssecurity" (padded to 26 bytes)
        - Password: "PWD:667166mm" (padded to 26 bytes)
        - BusNumber: 1
        - BusLock: 0

        Returns:
            56-byte ConnectRequest payload
        """
        payload = bytearray()

        # Command ID and Version
        payload.extend([1, 2])

        # Username: "USER:ppssecurity" padded to 26 bytes
        username_str = f"USER:{self._username}"  # "USER:ppssecurity" = 16 chars
        username_padding = " " * (26 - len(username_str))  # 10 spaces
        username_field = (username_str + username_padding).encode('utf-8')
        payload.extend(username_field)

        # Password: "PWD:667166mm" padded to 26 bytes
        password_str = f"PWD:{self._password}"  # "PWD:667166mm" = 12 chars
        password_padding = " " * (26 - len(password_str))  # 14 spaces
        password_field = (password_str + password_padding).encode('utf-8')
        payload.extend(password_field)

        # Bus number and lock
        payload.append(self._bus_number)
        payload.append(0)

        return bytes(payload)

    def _handle_connect_response(self, frame: Frame):
        """
        Handle ConnectResponseCommand from IPCom.

        Based on ConnectResponseCommand.cs FromBytes() and IPCommunication.cs:353-380

        Response types:
        - [1, ...]: Success - extract public key
        - [14, 101]: NonSecure mode - disable encryption and reconnect

        Args:
            frame: ConnectResponse frame
        """
        data = frame.data

        if len(data) < 1:
            self.logger.error("Invalid ConnectResponse: empty data")
            return

        # Check for NonSecure response [14, 101]
        if len(data) >= 2 and data[0] == 14 and data[1] == 101:
            self.logger.warning("IPCom requested NonSecure mode - disabling encryption")
            self._encryption._secure = False
            self._authenticated = True  # Mark as authenticated (but without encryption)
            return

        # Standard ConnectResponse
        connection_status = data[0]

        if connection_status != 1:
            self.logger.error(f"Authentication failed: connection_status={connection_status}")
            return

        # Short response (3 bytes): [status, ?, ?]
        if len(data) == 3:
            self.logger.info("Received short ConnectResponse (no public key)")
            self._authenticated = True
            return

        # Full response: Extract public key from bytes[7:135] (128 bytes)
        if len(data) >= 135:
            public_key = data[7:135]
            self._encryption.set_public_key(public_key)
            self._authenticated = True
            self.logger.info(f"Public key set ({len(public_key)} bytes) - dual-key mode active")
        else:
            self.logger.warning(f"ConnectResponse too short for public key: {len(data)} bytes")
            self._authenticated = True

    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._connected

    def run_forever(self, auto_reconnect: bool = True):
        """
        Run receive loop indefinitely with automatic reconnection.

        Args:
            auto_reconnect: Enable automatic reconnection on disconnect

        This is a blocking call. Use in a separate thread if needed.
        """
        reconnect_delay = self.RECONNECT_BASE_DELAY

        while True:
            # Connect if not connected
            if not self._connected:
                if self.connect():
                    reconnect_delay = self.RECONNECT_BASE_DELAY  # Reset delay on successful connect
                else:
                    if not auto_reconnect:
                        self.logger.error("Connection failed and auto_reconnect is disabled")
                        break

                    # Exponential backoff
                    self.logger.info(f"Reconnecting in {reconnect_delay:.1f}s...")
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * self.RECONNECT_MULTIPLIER, self.RECONNECT_MAX_DELAY)
                    continue

            # Receive and process frames
            try:
                self._receive_loop()
            except socket.timeout:
                # Timeout is normal, just continue
                continue
            except socket.error as e:
                self.logger.error(f"Socket error: {e}")
                self._cleanup_socket()
                if not auto_reconnect:
                    break
            except KeyboardInterrupt:
                self.logger.info("Interrupted by user")
                self.disconnect()
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in receive loop: {e}", exc_info=True)
                self._cleanup_socket()
                if not auto_reconnect:
                    break

    def _receive_loop(self):
        """
        Internal receive loop (single iteration).

        Receives data, parses frames, and processes them.
        """
        if not self._socket:
            return

        # Receive data
        data = self._socket.recv(self.RECV_BUFFER_SIZE)

        if not data:
            # Empty recv() means connection closed
            self.logger.warning("Connection closed by remote host")
            self._cleanup_socket()
            return

        if self.debug:
            hex_dump = ' '.join(f'{b:02x}' for b in data[:64])
            self.logger.debug(f"RX {len(data)} bytes: {hex_dump}")

        # Append to buffer
        self._recv_buffer.extend(data)

        # Parse all complete frames from buffer
        for frame in self._parse_frames():
            self._process_frame(frame)

    def _parse_frames(self) -> Iterator[Frame]:
        """
        Parse complete frames from receive buffer.

        Yields:
            Frame objects

        The buffer may contain:
        - RAW StateSnapshot messages (130 bytes: 79 db + 128 encrypted)
        - Partial frames (need more data)
        - Complete frames (parse and yield)
        - Multiple frames (parse all)

        CRITICAL: StateSnapshot responses are NOT framed!
        From Wireshark analysis, the server sends:
        - 79 db (2-byte header)
        - 128 bytes encrypted StateSnapshot data
        - No frame wrapper, no checksum byte

        We must check for RAW StateSnapshot BEFORE looking for framed messages.
        """
        while len(self._recv_buffer) >= 2:
            # Check for RAW StateSnapshot message (79 db header)
            if len(self._recv_buffer) >= 130 and self._recv_buffer[0] == 0x79 and self._recv_buffer[1] == 0xdb:
                if self.debug:
                    self.logger.debug("Detected RAW StateSnapshot message (130 bytes)")

                # Extract 130 bytes (FULLY ENCRYPTED ExoOutputsResponseCommand)
                encrypted_snapshot = bytes(self._recv_buffer[:130])

                # Remove from buffer
                self._recv_buffer = self._recv_buffer[130:]

                try:
                    # CRITICAL FIX: The entire 130 bytes are encrypted!
                    # "79 db" is NOT a plaintext header - it's the encrypted [05 01] command ID/version!
                    # When we encrypt ExoOutputsRequestCommand [05 01], we get [79 db]
                    # So the response [79 db + 128 bytes] is actually [05 01 + 128 bytes] encrypted

                    # Decrypt ALL 130 bytes
                    decrypted = self._encryption.decrypt(encrypted_snapshot)

                    if self.debug:
                        self.logger.debug(f"Decrypted StateSnapshot: ID={decrypted[0]:02x} Ver={decrypted[1]:02x} Data={decrypted[2:18].hex()}...")

                    # After decryption, we should have:
                    # Byte 0-1: [05 01] (ExoOutputsResponseCommand ID and version)
                    # Byte 2-129: 128 bytes of module data (16 modules × 8 outputs)
                    full_snapshot_data = decrypted

                    snapshot = StateSnapshot(raw=full_snapshot_data, timestamp=time.time())

                    if self.debug:
                        self.logger.debug(f"StateSnapshot created: {snapshot}")

                    # Store latest snapshot
                    self._latest_snapshot = snapshot

                    # Trigger callback
                    if self._on_state_snapshot:
                        self._on_state_snapshot(snapshot)

                except Exception as e:
                    self.logger.error(f"Error parsing RAW StateSnapshot: {e}")
                    import traceback
                    traceback.print_exc()

                # Continue to next iteration
                continue

            # No RAW StateSnapshot, check for framed messages
            if len(self._recv_buffer) < 5:  # Minimum frame size
                break

            # Find start byte
            start_idx = self._recv_buffer.find(self.FRAME_START_BYTE)

            if start_idx == -1:
                # No start byte found, check if buffer starts with 79 db but not enough bytes yet
                if len(self._recv_buffer) >= 2 and self._recv_buffer[0] == 0x79 and self._recv_buffer[1] == 0xdb:
                    if self.debug:
                        self.logger.debug(f"Partial StateSnapshot: have {len(self._recv_buffer)}/130 bytes")
                    break  # Wait for more data

                # Not a StateSnapshot and no frame start, discard
                if self.debug:
                    hex_dump = ' '.join(f'{b:02x}' for b in self._recv_buffer[:32])
                    self.logger.debug(f"No start byte found, discarding {len(self._recv_buffer)} bytes: {hex_dump}")
                self._recv_buffer.clear()
                break

            if start_idx > 0:
                # Discard bytes before start byte
                if self.debug:
                    self.logger.debug(f"Discarding {start_idx} bytes before start byte")
                self._recv_buffer = self._recv_buffer[start_idx:]

            # Check if we have enough bytes for header
            if len(self._recv_buffer) < 4:
                break  # Need more data

            # Parse header
            start = self._recv_buffer[0]
            to = self._recv_buffer[1]
            from_ = self._recv_buffer[2]
            length = self._recv_buffer[3]

            # Calculate total frame size
            # Frame = Start(1) + To(1) + From(1) + Length(1) + Data(length-1) + Checksum(1)
            data_size = length - 1
            total_size = 4 + data_size + 1

            # Check if we have complete frame
            if len(self._recv_buffer) < total_size:
                if self.debug:
                    self.logger.debug(f"Incomplete frame: have {len(self._recv_buffer)}, need {total_size}")
                break  # Need more data

            # Extract frame bytes
            frame_bytes = bytes(self._recv_buffer[:total_size])

            # Remove from buffer
            self._recv_buffer = self._recv_buffer[total_size:]

            # Parse frame
            try:
                encrypted_data = frame_bytes[4 : 4 + data_size]
                checksum = frame_bytes[4 + data_size]

                # Verify checksum on ENCRYPTED data
                if not self._verify_checksum(encrypted_data, checksum):
                    self.logger.warning(f"BADCHECKSUM: frame discarded (to={to}, from={from_}, length={length})")
                    continue

                # Decrypt data AFTER checksum verification
                data = self._encryption.decrypt(encrypted_data)

                # Create Frame object with decrypted data
                frame = Frame(
                    start=start,
                    to=to,
                    from_=from_,
                    length=length,
                    data=data,
                    checksum=checksum
                )

                if self.debug:
                    self.logger.debug(f"Received: {frame}")

                yield frame

            except Exception as e:
                self.logger.error(f"Error parsing frame: {e}")
                continue

    def _verify_checksum(self, data: bytes, checksum: int) -> bool:
        """
        Verify frame checksum (XOR algorithm).

        Args:
            data: Frame data bytes
            checksum: Received checksum byte

        Returns:
            True if checksum is valid
        """
        computed = 0
        for byte in data:
            computed ^= byte
        return computed == checksum

    def _compute_checksum(self, data: bytes) -> int:
        """
        Compute frame checksum (XOR algorithm).

        Args:
            data: Frame data bytes

        Returns:
            Checksum byte
        """
        checksum = 0
        for byte in data:
            checksum ^= byte
        return checksum

    def _process_frame(self, frame: Frame):
        """
        Process received frame.

        Args:
            frame: Parsed frame
        """
        # Trigger generic frame callback
        if self._on_frame:
            self._on_frame(frame)

        # Handle specific command types
        if frame.command_type == self.CMD_CONNECT_RESPONSE:
            self._handle_connect_response(frame)
        elif frame.command_type == self.CMD_EXO_OUTPUTS_RESPONSE:
            self._handle_state_snapshot(frame)
        elif frame.command_type == self.CMD_KEEPALIVE_RESPONSE:
            if self.debug:
                self.logger.debug("Received KeepAlive response")
        elif frame.command_type == self.CMD_DISCONNECT_RESPONSE:
            self.logger.info("Received Disconnect response")
        else:
            if self.debug:
                self.logger.debug(f"Received frame type {frame.command_type}")

    def _handle_state_snapshot(self, frame: Frame):
        """
        Handle ExoOutputs state snapshot frame.

        Args:
            frame: State snapshot frame (command type 5)
        """
        try:
            # Decode snapshot
            snapshot = StateSnapshot(raw=frame.data, timestamp=time.time())

            # Store latest
            self._latest_snapshot = snapshot

            if self.debug:
                self.logger.debug(f"State snapshot received: {snapshot}")

            # Trigger callback
            if self._on_state_snapshot:
                self._on_state_snapshot(snapshot)

        except Exception as e:
            self.logger.error(f"Error decoding state snapshot: {e}")

    def _build_frame(self, to: int, from_: int, data: bytes) -> Frame:
        """
        Build a frame with checksum.

        Args:
            to: Destination address
            from_: Source address
            data: Frame data (including command type)

        Returns:
            Frame object
        """
        length = len(data) + 1
        checksum = self._compute_checksum(data)

        return Frame(
            start=self.FRAME_START_BYTE,
            to=to,
            from_=from_,
            length=length,
            data=data,
            checksum=checksum
        )

    def send_frame_bytes(self, frame_bytes: bytes):
        """
        Send raw frame bytes over TCP.

        Args:
            frame_bytes: Complete frame bytes

        Raises:
            RuntimeError: If not connected
            socket.error: On send failure
        """
        if not self._connected or not self._socket:
            raise RuntimeError("Not connected")

        # Rate limiting
        elapsed = time.time() - self._last_write_time
        if elapsed < self.WRITE_RATE_LIMIT:
            time.sleep(self.WRITE_RATE_LIMIT - elapsed)

        # Send
        self._socket.sendall(frame_bytes)
        self._last_write_time = time.time()

        if self.debug:
            hex_dump = ' '.join(f'{b:02x}' for b in frame_bytes[:64])
            self.logger.debug(f"TX {len(frame_bytes)} bytes: {hex_dump}")

    def send_frame(self, to: int, from_: int, data: bytes):
        """
        Build and send a frame with encryption.

        Args:
            to: Destination address
            from_: Source address
            data: Frame data (including command type)
        """
        # Encrypt data before building frame
        encrypted_data = self._encryption.encrypt(data)

        # Build frame with encrypted data (checksum computed on encrypted data)
        frame = self._build_frame(to, from_, encrypted_data)
        self.send_frame_bytes(frame.to_bytes())

    def get_latest_snapshot(self) -> Optional[StateSnapshot]:
        """
        Get the most recent state snapshot.

        Returns:
            StateSnapshot or None if no snapshot received yet
        """
        return self._latest_snapshot

    def get_value(self, module: int, output: int) -> Optional[int]:
        """
        Get current value of an output from latest snapshot.

        Args:
            module: Module number (1-16)
            output: Output number (1-8)

        Returns:
            Value (0-255) or None if no snapshot available
        """
        if not self._latest_snapshot:
            return None

        return self._latest_snapshot.get_value(module, output)

    def send_command(self, command_bytes: bytes) -> None:
        """
        Send a command to the device.

        Args:
            command_bytes: Plaintext command bytes (will be encrypted before sending)

        Raises:
            RuntimeError: If not connected
        """
        if not self._connected:
            raise RuntimeError("Not connected")

        # Encrypt the command
        encrypted = self._encryption.encrypt(command_bytes)

        # Send encrypted command
        self._socket.sendall(encrypted)
        self._last_write_time = time.time()

        if self.debug:
            self.logger.debug(f"Sent command: {command_bytes.hex()} (encrypted: {encrypted.hex()})")

    def set_output(self, module: int, output: int, value: int, bus_address: int = 60, bus_number: int = 2) -> None:
        """
        Set an output to a specific value.

        Args:
            module: Module number (1-16)
            output: Output number (1-8)
            value: Output value (0=OFF, 255=ON, 1-254=dimming level)
            bus_address: Base bus address (default 60)
            bus_number: Bus number (default 2 - correct for most setups)

        Raises:
            RuntimeError: If not connected
        """
        from frame_builder import set_output

        command = set_output(module, output, value, bus_address, bus_number)
        self.send_command(command)

        if self.debug:
            self.logger.debug(f"Set Module {module}, Output {output} to {value}")

    def turn_on(self, module: int, output: int, **kwargs) -> None:
        """Turn output ON (255)."""
        self.set_output(module, output, 255, **kwargs)

    def turn_off(self, module: int, output: int, **kwargs) -> None:
        """Turn output OFF (0)."""
        self.set_output(module, output, 0, **kwargs)

    def set_dimmer(self, module: int, output: int, percentage: int, **kwargs) -> None:
        """
        Set dimmer to percentage (0-100).

        Args:
            percentage: Dimmer level 0-100
        """
        from frame_builder import set_dimmer

        command = set_dimmer(module, output, percentage, **kwargs)
        self.send_command(command)

    def set_value(self, module: int, output: int, value: int, bus: int = 1):
        """
        Set output value (send write frame).

        Based on ExoSetValuesFrame from decompiled source:
        - Module address: 60 + (module - 1)
        - Data format: [1, value1, value2, ..., value8]

        Args:
            module: Module number (1-16)
            output: Output number (1-8)
            value: New value (0-255)
            bus: Bus number (default: 1)

        Raises:
            ValueError: If parameters are out of range
            RuntimeError: If not connected or no snapshot available
        """
        if not (1 <= module <= 16):
            raise ValueError(f"Invalid module number: {module} (must be 1-16)")
        if not (1 <= output <= 8):
            raise ValueError(f"Invalid output number: {output} (must be 1-8)")
        if not (0 <= value <= 255):
            raise ValueError(f"Invalid value: {value} (must be 0-255)")

        if not self._connected:
            raise RuntimeError("Not connected")

        if not self._latest_snapshot:
            raise RuntimeError("No state snapshot available yet (need current values)")

        # Get current module values
        values = self._latest_snapshot.get_module_values(module)

        # Update target output
        values[output - 1] = value

        # Build frame data: [1, value1, value2, ..., value8]
        data = bytes([1] + values)

        # Calculate module address: 60 + (module - 1)
        to_address = 60 + (module - 1)

        # Send frame
        self.logger.info(f"Setting module {module} output {output} to {value}")
        self.send_frame(to=to_address, from_=0, data=data)

    def send_keepalive(self):
        """Send keepalive frame."""
        if not self._connected:
            raise RuntimeError("Not connected")

        data = bytes([self.CMD_KEEPALIVE_RESPONSE])
        self.send_frame(to=1, from_=0, data=data)

        if self.debug:
            self.logger.debug("Sent KeepAlive")

    def request_snapshot(self):
        """
        Request state snapshot from IPCom device.

        CRITICAL FINDING from Wireshark analysis:
        The official app sends RAW keepalive bytes `79 db` (NOT framed!).
        The server responds with StateSnapshot messages (130 bytes encrypted).

        Pattern from official_handshake.pcap:
        - Client sends: 79 db (2 bytes RAW, not encrypted, not framed)
        - Server sends: 130 bytes (79 db header + 128 bytes encrypted StateSnapshot)

        This is sent every ~400ms to maintain connection and receive state updates.

        Raises:
            RuntimeError: If not connected
        """
        if not self._connected:
            raise RuntimeError("Not connected")

        # Send RAW keepalive (matches official app behavior from Wireshark)
        KEEPALIVE_BYTES = b'\x79\xdb'

        if self.debug:
            self.logger.debug("Sending RAW keepalive (79 db)")

        self._socket.sendall(KEEPALIVE_BYTES)
        self._last_write_time = time.time()

    def start_snapshot_polling(self, interval: float = 0.350):
        """
        Start periodic snapshot polling (matches original app behavior).

        Args:
            interval: Polling interval in seconds (default: 0.350s = 350ms)

        Based on decompiled C# from IPCommunication.cs:554-599
        - Method: GetExoOutputs() runs on a timer
        - Delay: this.delay (350ms by default, from line 54)
        - Task runs while connected and not disposed

        This replicates the WidgetOutput behavior when Domotique panel opens.
        """
        import threading

        if not self._connected:
            raise RuntimeError("Not connected")

        # Set flag
        self._polling_enabled = True

        def polling_loop():
            """Background polling thread."""
            while self._connected and self._polling_enabled:
                try:
                    if not self._processing:  # Don't send if other command in progress
                        self.request_snapshot()
                    time.sleep(interval)
                except Exception as e:
                    self.logger.error(f"Error in polling loop: {e}")
                    break

        # Start daemon thread
        polling_thread = threading.Thread(target=polling_loop, daemon=True)
        polling_thread.start()
        self.logger.info(f"Started snapshot polling (interval={interval}s)")

    def stop_snapshot_polling(self):
        """Stop periodic snapshot polling."""
        self._polling_enabled = False
        self.logger.info("Stopped snapshot polling")

    # Callback registration
    def on_state_snapshot(self, callback: Callable[[StateSnapshot], None]):
        """
        Register callback for state snapshot events.

        Args:
            callback: Function(StateSnapshot) -> None
        """
        self._on_state_snapshot = callback

    def on_frame(self, callback: Callable[[Frame], None]):
        """
        Register callback for all frame events.

        Args:
            callback: Function(Frame) -> None
        """
        self._on_frame = callback

    def on_connect(self, callback: Callable[[], None]):
        """
        Register callback for connection events.

        Args:
            callback: Function() -> None
        """
        self._on_connect = callback

    def on_disconnect(self, callback: Callable[[], None]):
        """
        Register callback for disconnection events.

        Args:
            callback: Function() -> None
        """
        self._on_disconnect = callback
