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
import threading
import queue
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

    # Background loop intervals (from official app reverse engineering)
    KEEPALIVE_INTERVAL = 30.0  # seconds - prevents TCP timeout
    STATUS_POLL_INTERVAL = 0.350  # seconds (350ms) - continuous state updates
    COMMAND_QUEUE_INTERVAL = 0.250  # seconds (250ms) - process queued commands

    def __init__(self, host: str, port: int = DEFAULT_PORT,
                 username: str = "", password: str = "", debug: bool = False):
        """
        Initialize IPCom client.

        Args:
            host: IPCom device hostname or IP address
            port: TCP port (default: 5000)
            username: IPCom authentication username
            password: IPCom authentication password
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

        # Shadow state: tracks pending writes that haven't been confirmed by server yet
        # This prevents race conditions when rapid commands overwrite each other
        # Format: {module_number: [val1, val2, ..., val8]}
        self._pending_writes: dict[int, list[int]] = {}

        # Encryption and authentication
        self._encryption = IPComEncryption()
        self._authenticated = False
        self._username = username
        self._password = password
        self._bus_number = 1

        # Callbacks
        self._on_state_snapshot: Optional[Callable[[StateSnapshot], None]] = None
        self._on_frame: Optional[Callable[[Frame], None]] = None
        self._on_connect: Optional[Callable[[], None]] = None
        self._on_disconnect: Optional[Callable[[], None]] = None

        # Background threads and command queue (persistent connection mode)
        self._persistent_mode = False
        self._keepalive_thread: Optional[threading.Thread] = None
        self._status_poll_thread: Optional[threading.Thread] = None
        self._command_queue_thread: Optional[threading.Thread] = None
        self._receive_thread: Optional[threading.Thread] = None
        self._command_queue: queue.Queue = queue.Queue()
        self._shutdown_event = threading.Event()
        self._lock = threading.RLock()  # For thread-safe operations

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
            self.logger.info(
                "Initiating TCP connection to %s:%s (timeout: %.1fs)",
                self.host, self.port, self.SOCKET_TIMEOUT
            )

            # Create socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.SOCKET_TIMEOUT)

            # Connect
            self._socket.connect((self.host, self.port))
            self._connected = True

            self.logger.info(
                "TCP connection established to %s:%s | local endpoint: %s",
                self.host, self.port,
                self._socket.getsockname() if self._socket else "N/A"
            )

            # Trigger callback
            if self._on_connect:
                self._on_connect()

            return True

        except socket.timeout:
            self.logger.error(
                "Connection timeout after %.1fs - host %s:%s may be unreachable or slow",
                self.SOCKET_TIMEOUT, self.host, self.port
            )
            self._cleanup_socket()
            return False

        except socket.gaierror as e:
            self.logger.error(
                "DNS resolution failed for %s: %s - check hostname/network",
                self.host, e
            )
            self._cleanup_socket()
            return False

        except ConnectionRefusedError as e:
            self.logger.error(
                "Connection refused by %s:%s - IPCom server may be down or port blocked",
                self.host, self.port
            )
            self._cleanup_socket()
            return False

        except socket.error as e:
            self.logger.error(
                "Socket error connecting to %s:%s: %s (errno: %s)",
                self.host, self.port, e, getattr(e, 'errno', 'N/A')
            )
            self._cleanup_socket()
            return False

        except Exception as e:
            self.logger.error(
                "Unexpected error connecting to %s:%s: %s",
                self.host, self.port, e, exc_info=True
            )
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

        # Validate credentials are provided
        if not self._username or not self._password:
            self.logger.error(
                "Authentication failed: credentials missing | "
                "username provided: %s | password provided: %s",
                bool(self._username), bool(self._password)
            )
            return False

        try:
            # Build authentication packet dynamically from credentials
            self.logger.debug(
                "Building ConnectRequest packet | username: %s (len: %d) | bus: %d",
                self._username, len(self._username), self._bus_number
            )
            auth_payload = self._build_connect_request()
            auth_packet = self._encryption.encrypt(auth_payload)

            self.logger.info(
                "Sending authentication packet to %s:%s | username: %s | packet size: %d bytes",
                self.host, self.port, self._username, len(auth_packet)
            )

            if self.debug:
                hex_preview = ' '.join(f'{b:02x}' for b in auth_packet[:32])
                self.logger.debug(f"TX (RAW): {hex_preview}... ({len(auth_packet)} bytes total)")

            # Send encrypted authentication packet
            self._socket.sendall(auth_packet)
            self.logger.debug("Sent authentication packet (%d bytes)", len(auth_packet))

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
                self.logger.error(
                    "ConnectResponse size mismatch | expected: 135 bytes | received: %d bytes | "
                    "this may indicate auth failure or protocol mismatch",
                    len(response)
                )
                if len(response) > 0:
                    hex_dump = ' '.join(f'{b:02x}' for b in response[:64])
                    self.logger.error("Response data (first 64 bytes): %s", hex_dump)

                    # Check for 7e e3 error
                    if len(response) == 2 and response == b'\x7e\xe3':
                        self.logger.error(
                            "Received 7e e3 error response - server rejected authentication | "
                            "possible causes: invalid credentials, account locked, protocol error"
                        )
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
                self.logger.error(
                    "ConnectResponse command type mismatch | expected: 0x01 | received: 0x%02x | "
                    "authentication may have been rejected",
                    cmd_type
                )
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
            self.logger.info(
                "Authentication successful with %s:%s | username: %s | "
                "encryption mode: dual-key (PRIVATE_KEY + PUBLIC_KEY)",
                self.host, self.port, self._username
            )
            return True

        except socket.timeout:
            self.logger.error(
                "AUTH_TIMEOUT | no response from %s:%s within %.1fs | "
                "possible causes: server overloaded, firewall blocking, network latency",
                self.host, self.port, self.SOCKET_TIMEOUT
            )
            return False
        except ConnectionResetError as e:
            self.logger.error(
                "AUTH_RESET | connection reset by %s:%s | "
                "possible causes: invalid credentials, account disabled, server crash",
                self.host, self.port
            )
            return False
        except BrokenPipeError as e:
            self.logger.error(
                "AUTH_BROKEN_PIPE | connection broken to %s:%s | "
                "server closed connection before auth completed",
                self.host, self.port
            )
            return False
        except OSError as e:
            self.logger.error(
                "AUTH_OS_ERROR | OS-level error with %s:%s: %s (errno: %s) | "
                "possible causes: network interface down, routing issues",
                self.host, self.port, e, getattr(e, 'errno', 'N/A')
            )
            return False
        except Exception as e:
            self.logger.error(
                "AUTH_UNEXPECTED | unexpected error with %s:%s: %s",
                self.host, self.port, e, exc_info=True
            )
            return False

    def _build_connect_request(self) -> bytes:
        """
        Build ConnectRequestCommand payload.

        Based on ConnectRequestCommand.cs ToBytes()

        Format (56 bytes total):
        - ID: 1
        - Version: 2
        - Username: "USER:<username>" (padded to 26 bytes)
        - Password: "PWD:<password>" (padded to 26 bytes)
        - BusNumber: 1
        - BusLock: 0

        Returns:
            56-byte ConnectRequest payload
        """
        payload = bytearray()

        # Command ID and Version
        payload.extend([1, 2])

        # Username: "USER:<username>" padded to 26 bytes
        username_str = f"USER:{self._username}"
        username_padding = " " * (26 - len(username_str))
        username_field = (username_str + username_padding).encode('utf-8')
        payload.extend(username_field)

        # Password: "PWD:<password>" padded to 26 bytes
        password_str = f"PWD:{self._password}"
        password_padding = " " * (26 - len(password_str))
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
            self.logger.debug("_receive_loop called but socket is None")
            return

        # Receive data
        try:
            data = self._socket.recv(self.RECV_BUFFER_SIZE)
        except socket.timeout:
            # Timeout is normal in non-blocking mode, just return
            raise
        except ConnectionResetError as e:
            self.logger.error(
                "Connection reset by %s:%s - remote host forcibly closed connection",
                self.host, self.port
            )
            self._cleanup_socket()
            raise
        except BrokenPipeError as e:
            self.logger.error(
                "Broken pipe to %s:%s - connection was lost",
                self.host, self.port
            )
            self._cleanup_socket()
            raise
        except socket.error as e:
            self.logger.error(
                "Socket error receiving from %s:%s: %s (errno: %s)",
                self.host, self.port, e, getattr(e, 'errno', 'N/A')
            )
            self._cleanup_socket()
            raise

        if not data:
            # Empty recv() means connection closed
            self.logger.warning(
                "CONN_CLOSED | connection closed by %s:%s | "
                "recv() returned empty | server may have dropped connection or network issue",
                self.host, self.port
            )
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

                    # Clear shadow state - server has confirmed the state
                    self._pending_writes.clear()

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

            # Clear shadow state - server has confirmed the state
            self._pending_writes.clear()

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
        """Turn output ON (255).

        Uses set_value() which preserves other outputs in the module.
        """
        # Module 6 (EXO DIM) uses 100 for full brightness, others use 255
        value = 100 if module == 6 else 255
        self.set_value(module, output, value)

    def turn_off(self, module: int, output: int, **kwargs) -> None:
        """Turn output OFF (0).

        Uses set_value() which preserves other outputs in the module.
        """
        self.set_value(module, output, 0)

    def set_dimmer(self, module: int, output: int, percentage: int, **kwargs) -> None:
        """
        Set dimmer to percentage (0-100).

        Uses set_value() which preserves other outputs in the module.

        Args:
            percentage: Dimmer level 0-100
        """
        if not (0 <= percentage <= 100):
            raise ValueError(f"percentage must be 0-100, got {percentage}")

        # Module 6 (EXO DIM) uses 0-100 values directly
        # Regular modules use 0-255 range
        if module == 6:
            value = percentage
        else:
            value = int((percentage / 100.0) * 255)

        self.set_value(module, output, value)

    def set_value(self, module: int, output: int, value: int, bus: int = 2):
        """
        Set output value (send write frame).

        Based on ExoSetValuesFrame from decompiled source:
        - Module address: 60 + (module - 1)
        - Data format: [1, value1, value2, ..., value8]

        Args:
            module: Module number (1-16)
            output: Output number (1-8)
            value: New value (0-255)
            bus: Bus number (default: 2, matches official app)

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

        # Get current module values from shadow state (pending writes) or snapshot
        # This prevents race condition where rapid commands overwrite each other
        if module in self._pending_writes:
            # Use shadow state (includes pending writes not yet confirmed)
            values = self._pending_writes[module].copy()
        else:
            # No pending writes, use snapshot
            values = self._latest_snapshot.get_module_values(module)

        # Update target output while preserving others
        values[output - 1] = value

        # Store in shadow state so next command sees this pending write
        self._pending_writes[module] = values

        # Use frame_builder to construct the proper command
        from frame_builder import build_exo_set_values_frame, build_frame_request_command

        # Calculate module address: 60 + (module - 1)
        to_address = 60 + (module - 1)

        # Build ExoSetValuesFrame
        frame = build_exo_set_values_frame(
            from_addr=0,
            to_addr=to_address,
            exo_number=module,
            values=values,
            bus_number=bus
        )

        # Wrap in FrameRequestCommand
        command = build_frame_request_command(frame)

        # Send command (will be encrypted by send_command)
        self.logger.info(f"Setting module {module} output {output} to {value}")
        if self.debug:
            self.logger.debug(f"Sending values for module {module}: {values}")
        self.send_command(command)

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

    # ==================================================================================
    # PERSISTENT CONNECTION MODE - Background Loops (Official App Behavior)
    # ==================================================================================

    def start_persistent_connection(self, auto_reconnect: bool = True) -> bool:
        """
        Start persistent connection mode with background loops (matches official app).

        This replaces the inefficient connect-poll-disconnect pattern with:
        1. Keep-Alive Loop (30s interval) - Prevents TCP timeout
        2. Status Poll Loop (350ms interval) - Continuous state updates (~2.86/sec)
        3. Command Queue Loop (250ms interval) - Processes queued commands
        4. Receive Loop (continuous) - Handles incoming data

        Based on reverse engineering findings from HomeAnywhere Blue app.

        Args:
            auto_reconnect: Automatically reconnect on disconnection

        Returns:
            True if connection established and loops started, False otherwise
        """
        if self._persistent_mode:
            self.logger.warning("Already in persistent connection mode")
            return True

        # Connect and authenticate
        if not self._connected:
            if not self.connect():
                return False

        if not self._authenticated:
            if not self.authenticate():
                self.disconnect()
                return False

        # Enable persistent mode
        self._persistent_mode = True
        self._shutdown_event.clear()

        # Start background loops
        self.logger.info("Starting persistent connection mode (official app behavior)")

        # 1. Keep-Alive Loop (30s interval)
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop,
            name="IPCom-KeepAlive",
            daemon=True
        )
        self._keepalive_thread.start()

        # 2. Status Poll Loop (350ms interval)
        self._status_poll_thread = threading.Thread(
            target=self._status_poll_loop,
            name="IPCom-StatusPoll",
            daemon=True
        )
        self._status_poll_thread.start()

        # 3. Command Queue Loop (250ms interval)
        self._command_queue_thread = threading.Thread(
            target=self._command_queue_loop,
            name="IPCom-CommandQueue",
            daemon=True
        )
        self._command_queue_thread.start()

        # 4. Receive Loop (continuous)
        self._receive_thread = threading.Thread(
            target=self._persistent_receive_loop,
            args=(auto_reconnect,),
            name="IPCom-Receive",
            daemon=True
        )
        self._receive_thread.start()

        self.logger.info(
            "Persistent connection established: "
            f"keep-alive={self.KEEPALIVE_INTERVAL}s, "
            f"polling={self.STATUS_POLL_INTERVAL}s, "
            f"cmd_queue={self.COMMAND_QUEUE_INTERVAL}s"
        )

        return True

    def stop_persistent_connection(self):
        """
        Stop persistent connection mode and all background loops.
        """
        if not self._persistent_mode:
            return

        self.logger.info("Stopping persistent connection mode...")
        self._persistent_mode = False
        self._shutdown_event.set()

        # Give threads a moment to see the shutdown signal
        time.sleep(0.1)

        # Wait for threads to finish (with timeout)
        for thread in [
            self._keepalive_thread,
            self._status_poll_thread,
            self._command_queue_thread,
            self._receive_thread
        ]:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)

        # Disconnect (threads should have stopped by now)
        self.disconnect()

        self.logger.info("Persistent connection stopped")

    def _keepalive_loop(self):
        """
        Background loop: Send keep-alive every 30 seconds.

        Purpose:
        - Prevents TCP connection timeout
        - Detects disconnections early
        - Matches official app behavior (KeepAliveRequestCommand every 30s)

        From IPCommunication.cs: KeepAlive timer runs while connected.
        """
        self.logger.debug("Keep-Alive loop started (interval=30s)")

        while self._persistent_mode and not self._shutdown_event.is_set():
            try:
                if self._connected and self._authenticated:
                    # Don't send if command is processing
                    if not self._processing:
                        with self._lock:
                            try:
                                self.send_keepalive()
                                self.logger.debug("Keep-alive sent")
                            except Exception as e:
                                self.logger.error(f"Keep-alive failed: {e}")
                                # Connection might be dead, receive loop will handle reconnect

                # Wait for next interval
                self._shutdown_event.wait(timeout=self.KEEPALIVE_INTERVAL)

            except Exception as e:
                self.logger.error(f"Error in keep-alive loop: {e}")
                if not self._persistent_mode:
                    break
                time.sleep(1.0)

        self.logger.debug("Keep-Alive loop stopped")

    def _status_poll_loop(self):
        """
        Background loop: Poll status every 350ms.

        Purpose:
        - Continuous state updates (~2.86 updates per second)
        - Triggers on_state_snapshot callbacks for real-time UI updates
        - Matches official app behavior (GetExoOutputs() every 350ms)

        From IPCommunication.cs:554-599: GetExoOutputs() runs on timer with 350ms delay.
        """
        self.logger.debug("Status Poll loop started (interval=350ms)")

        while self._persistent_mode and not self._shutdown_event.is_set():
            try:
                if self._connected and self._authenticated:
                    # Don't send if command is processing
                    if not self._processing:
                        with self._lock:
                            try:
                                self.request_snapshot()
                            except Exception as e:
                                self.logger.error(f"Status poll failed: {e}")
                                # Connection might be dead, receive loop will handle reconnect

                # Wait for next interval
                self._shutdown_event.wait(timeout=self.STATUS_POLL_INTERVAL)

            except Exception as e:
                self.logger.error(f"Error in status poll loop: {e}")
                if not self._persistent_mode:
                    break
                time.sleep(0.5)

        self.logger.debug("Status Poll loop stopped")

    def _command_queue_loop(self):
        """
        Background loop: Process command queue every 250ms.

        Purpose:
        - Handles user commands without blocking status polling
        - Sets _processing flag to pause polling during command execution
        - Waits for command response before resuming polling
        - Matches official app behavior (command processing with polling pause)

        From official app: Commands set processing=true, pause polling, execute, resume.
        """
        self.logger.debug("Command Queue loop started (interval=250ms)")

        while self._persistent_mode and not self._shutdown_event.is_set():
            try:
                # Check for queued commands (non-blocking with timeout)
                try:
                    command = self._command_queue.get(timeout=self.COMMAND_QUEUE_INTERVAL)
                except queue.Empty:
                    continue

                # Process command
                if self._connected and self._authenticated:
                    # Set processing flag to pause polling
                    self._processing = True

                    try:
                        # Execute command
                        command_func = command["func"]
                        command_args = command.get("args", ())
                        command_kwargs = command.get("kwargs", {})

                        self.logger.debug(f"Executing queued command: {command_func.__name__}")
                        command_func(*command_args, **command_kwargs)

                        # Wait briefly for response
                        time.sleep(0.1)

                    except Exception as e:
                        self.logger.error(f"Error executing command: {e}")

                    finally:
                        # Resume polling
                        self._processing = False

                # Mark task as done
                self._command_queue.task_done()

            except Exception as e:
                self.logger.error(f"Error in command queue loop: {e}")
                if not self._persistent_mode:
                    break
                time.sleep(0.5)

        self.logger.debug("Command Queue loop stopped")

    def _persistent_receive_loop(self, auto_reconnect: bool):
        """
        Background loop: Continuous receive with auto-reconnect.

        Purpose:
        - Handles incoming data continuously
        - Maintains persistent connection
        - Auto-reconnects on disconnection

        Args:
            auto_reconnect: Enable automatic reconnection
        """
        self.logger.debug("Receive loop started (persistent mode)")
        reconnect_delay = self.RECONNECT_BASE_DELAY

        while self._persistent_mode and not self._shutdown_event.is_set():
            # Reconnect if disconnected
            if not self._connected:
                if auto_reconnect:
                    self.logger.info(f"Reconnecting in {reconnect_delay:.1f}s...")
                    time.sleep(reconnect_delay)

                    if self.connect() and self.authenticate():
                        reconnect_delay = self.RECONNECT_BASE_DELAY
                        self.logger.info("Reconnected successfully")
                    else:
                        reconnect_delay = min(
                            reconnect_delay * self.RECONNECT_MULTIPLIER,
                            self.RECONNECT_MAX_DELAY
                        )
                        continue
                else:
                    break

            # Receive and process data
            try:
                self._receive_loop()
            except socket.timeout:
                # Timeout is normal, just continue
                continue
            except socket.error as e:
                # Ignore errors if we're shutting down
                if self._persistent_mode and self._connected:
                    self.logger.error(f"Socket error in receive loop: {e}")
                self._cleanup_socket()
                if not auto_reconnect or not self._persistent_mode:
                    break
            except Exception as e:
                if self._persistent_mode:  # Only log if not shutting down
                    self.logger.error(f"Unexpected error in receive loop: {e}", exc_info=True)
                self._cleanup_socket()
                if not auto_reconnect or not self._persistent_mode:
                    break

        self.logger.debug("Receive loop stopped (persistent mode)")

    def queue_command(self, func: Callable, *args, **kwargs):
        """
        Queue a command for execution in the command queue loop.

        This allows commands to be executed without blocking the caller,
        and ensures proper synchronization with status polling.

        Args:
            func: Command function to execute (e.g., self.set_value)
            *args: Positional arguments for the command
            **kwargs: Keyword arguments for the command
        """
        self._command_queue.put({
            "func": func,
            "args": args,
            "kwargs": kwargs
        })

        if self.debug:
            self.logger.debug(f"Queued command: {func.__name__}")

    # ==================================================================================
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
