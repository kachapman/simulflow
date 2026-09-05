"""Connection manager - wraps all ADB/RDP/GNOME shell commands."""

import queue
import secrets
import string
import subprocess
import time
from dataclasses import dataclass

from PyQt6.QtCore import QThread, pyqtSignal
from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

RDP_PORT = 3389
POLL_INTERVAL = 2
HEALTH_CHECK_INTERVAL = 10
WIRELESS_POLL_ATTEMPTS = 10
PAIR_DISCOVER_TIMEOUT = 90.0
CONNECT_DISCOVER_TIMEOUT = 30.0
ADB_CONNECT_TIMEOUT = 10.0
PREPAIRED_DISCOVER_TIMEOUT = 3.0

ADB_PAIRING_SERVICE = "_adb-tls-pairing._tcp.local."
ADB_CONNECT_SERVICE = "_adb-tls-connect._tcp.local."


class PairingDiscoveryTimeout(RuntimeError):
    """Raised when the tablet never scans the QR code within the wait window."""


@dataclass
class WirelessInfo:
    """Connection details for Android 11+ wireless debugging."""
    ip: str = ""
    pair_port: str = ""
    pair_code: str = ""
    connect_port: str = ""


def _is_wireless_serial(serial: str) -> bool:
    """True if a device serial looks like a TCP/wireless transport."""
    return ":" in serial or serial.endswith("._tcp")


class ConnectionManager(QThread):
    """Manages the USB desktop extend connection in a background thread."""

    log_message = pyqtSignal(str, str)  # (level, message)
    status_changed = pyqtSignal(dict)   # {"adb": bool, "rdp": bool, "tunnel": bool}
    finished = pyqtSignal(bool)         # success
    connection_lost = pyqtSignal(str)   # reason
    qr_data_ready = pyqtSignal(str, str)  # (qr_text, service_name)

    def __init__(self, username: str, password: str, sudo_password: str,
                 mode: str = "usb", wireless: WirelessInfo | None = None):
        super().__init__()
        self.username = username
        self.password = password
        self.sudo_password = sudo_password
        self.mode = mode
        self.wireless = wireless or WirelessInfo()
        self._serial: str | None = None
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def _log(self, level: str, msg: str):
        self.log_message.emit(level, msg)

    def _run_cmd(self, cmd: list[str], check: bool = True, sudo: bool = False,
                 timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a command, optionally with sudo. Returns CompletedProcess."""
        if sudo:
            cmd = ["sudo", "-S"] + cmd

        self._log("info", f"  $ {' '.join(cmd)}")

        proc = subprocess.run(
            cmd,
            input=self.sudo_password.encode() if sudo else None,
            capture_output=True,
            timeout=timeout,
        )

        if proc.returncode != 0 and check:
            stderr = proc.stderr.decode().strip()
            raise RuntimeError(f"Command failed (exit {proc.returncode}): {stderr}")

        return proc

    def _run_cmd_streaming(self, cmd: list[str], sudo: bool = False) -> tuple[int, str]:
        """Run a command and stream output via log signals. Returns (returncode, combined output)."""
        if sudo:
            cmd = ["sudo", "-S"] + cmd

        self._log("info", f"  $ {' '.join(cmd)}")

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if sudo else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        if sudo and self.sudo_password:
            proc.stdin.write(self.sudo_password + "\n")
            proc.stdin.flush()

        output_lines = []
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line:
                self._log("info", f"  {line}")
                output_lines.append(line)

        proc.wait()
        return proc.returncode, "\n".join(output_lines)

    def run(self):
        """Execute the full connection sequence, then monitor."""
        try:
            self._log("info", "=== Starting Simulflow Connection ===")
            self._connect()
            self._log("success", "=== Connection Established Successfully ===")
            self.finished.emit(True)
            self._monitor()
        except Exception as e:
            self._log("error", f"Connection failed: {e}")
            self.finished.emit(False)

    def _connect(self):
        self._warn_gnome_49_incompatibility()

        # Step 1: Wait for tablet
        self._log("info", f"[1/4] Waiting for tablet {'wireless' if self.mode == 'wireless' else 'USB'} connection...")
        self.status_changed.emit({"adb": False, "rdp": False, "tunnel": False})

        if self.mode == "wireless":
            tablet_serial = self._pair_and_connect_wireless()
        else:
            tablet_serial = None
            while not self._stop_requested:
                tablet_serial = self._detect_tablet()
                if tablet_serial:
                    break
                time.sleep(POLL_INTERVAL)

        if self._stop_requested:
            raise RuntimeError("Cancelled by user")

        self._serial = tablet_serial
        self._log("success", f"  Tablet detected: {tablet_serial}")
        self.status_changed.emit({"adb": True, "rdp": False, "tunnel": False})

        # Step 2: Disable system-level Remote Login
        self._log("info", "[2/4] Disabling Remote Login (system-level)...")
        self._disable_system_rdp()

        # Step 3: Enable user-level Desktop Sharing with EXTEND mode
        self._log("info", "[3/4] Configuring Desktop Sharing in EXTEND mode...")
        self._enable_user_rdp()
        self.status_changed.emit({"adb": True, "rdp": True, "tunnel": False})

        # Step 4: Set up ADB reverse tunnel
        self._log("info", "[4/4] Setting up ADB reverse tunnel...")
        self._setup_adb_tunnel()
        self.status_changed.emit({"adb": True, "rdp": True, "tunnel": True})

        # Step 5: Verify actual connectivity
        self._log("info", "[5/5] Verifying RDP connectivity...")
        if not self._verify_rdp_connectivity():
            self._log("warning", "  RDP connectivity check failed, attempting restart...")
            self._restart_grd_service()
            time.sleep(3)
            if not self._verify_rdp_connectivity():
                self._log("warning", "  RDP still not responding after restart")

    def _detect_tablet(self) -> str | None:
        """Poll adb devices for a connected tablet matching the active mode."""
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True, text=True, timeout=5,
            )
            wireless = self.mode == "wireless"
            configured_ip = self.wireless.ip.strip()
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith("List") or "daemon" in line:
                    continue
                parts = line.split()
                if len(parts) < 2 or parts[1] != "device":
                    continue
                serial = parts[0]
                is_wireless = _is_wireless_serial(serial)
                if wireless:
                    if configured_ip and serial.startswith(f"{configured_ip}:"):
                        return serial
                    if is_wireless:
                        return serial
                else:
                    if not is_wireless:
                        return serial
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def _pair_and_connect_wireless(self) -> str | None:
        """Pair + connect a wireless device, or return an already-visible serial."""
        wi = self.wireless
        fully_filled = bool(wi.ip and wi.pair_port and wi.pair_code and wi.connect_port)

        # Generate the QR code right away so the dialog is already open while the
        # app also tries to auto-connect to an already-paired tablet. The same
        # credentials are reused below so the QR shown never changes.
        qr_data: tuple[str, str, str] | None = None
        if not fully_filled:
            qr_data = self._generate_qr_pairing_data()
            self.qr_data_ready.emit(qr_data[0], qr_data[1])

        for _ in range(WIRELESS_POLL_ATTEMPTS):
            if self._stop_requested:
                raise RuntimeError("Cancelled by user")
            serial = self._detect_tablet()
            if serial:
                return serial
            time.sleep(POLL_INTERVAL)

        self._log("info", "  Looking for an already-paired tablet on the network...")
        pre_paired = self._discover_service(ADB_CONNECT_SERVICE, timeout=PREPAIRED_DISCOVER_TIMEOUT)
        if pre_paired:
            ip, port = pre_paired
            self._log("success", f"  Previously paired tablet found: {ip}:{port}")
            try:
                self._run_cmd(["adb", "connect", f"{ip}:{port}"],
                              check=False, timeout=int(ADB_CONNECT_TIMEOUT))
            except Exception as e:
                self._log("warning", f"  adb connect failed: {e}")
            for _ in range(5):
                if self._stop_requested:
                    raise RuntimeError("Cancelled by user")
                serial = self._detect_tablet()
                if serial:
                    return serial
                time.sleep(POLL_INTERVAL)
            self._log("warning",
                      "  Could not reach the pre-paired tablet — connecting fresh instead. "
                      "If you switched Wi-Fi networks, that address is stale and the QR "
                      "code pairs the tablet on the current network.")

        if fully_filled:
            return self._pair_and_connect_manual()

        assert qr_data is not None
        try:
            return self._pair_and_connect_qr(qr_data=qr_data, timeout=PAIR_DISCOVER_TIMEOUT)
        except PairingDiscoveryTimeout as e:
            self._log("warning", f"  {e}")

        raise RuntimeError(
            "Wireless pairing did not complete. Scan the QR code on the tablet "
            "(Settings → Developer Options → Wireless debugging → Pair device "
            "with QR code) and try again."
        )

    def _pair_and_connect_manual(self) -> str:
        """Pair + connect a wireless device from the manually entered details."""
        wi = self.wireless
        if not (wi.ip and wi.pair_port and wi.pair_code and wi.connect_port):
            raise RuntimeError(
                "No paired wireless device found. Enter the tablet's details "
                "(Settings → Developer Options → Wireless debugging → Pair device "
                "with pairing code)."
            )

        self._log("info", f"  Pairing with {wi.ip}:{wi.pair_port}...")
        result = self._run_cmd(
            ["adb", "pair", f"{wi.ip}:{wi.pair_port}", wi.pair_code],
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode().strip()
            self._log("warning", f"  Pairing failed: {stderr or 'unknown error'}")
            self._log("warning",
                      "  'protocol fault ... Success' usually means pairing actually "
                      "succeeded before the response arrived. Retry if it didn't.")
            self._log("warning",
                      "  If it timed out, reopen 'Pair device with pairing code' "
                      "on the tablet and retry.")

        self._log("info", f"  Connecting to {wi.ip}:{wi.connect_port}...")
        try:
            self._run_cmd(
                ["adb", "connect", f"{wi.ip}:{wi.connect_port}"],
                check=False, timeout=int(ADB_CONNECT_TIMEOUT),
            )
        except Exception as e:
            self._log("warning", f"  adb connect failed: {e}")

        for _ in range(WIRELESS_POLL_ATTEMPTS):
            if self._stop_requested:
                raise RuntimeError("Cancelled by user")
            serial = self._detect_tablet()
            if serial:
                return serial
            time.sleep(POLL_INTERVAL)

        raise RuntimeError(
            "Wireless pairing/connect completed but the device is not visible "
            "in 'adb devices'. Check the IP, ports, and that both devices share "
            "the same network."
        )

    def _generate_qr_pairing_data(self) -> tuple[str, str, str]:
        """Return (qr_text, service_name, password) for ADB wireless QR pairing."""
        alphabet = string.ascii_letters + string.digits + "*@!/>"
        service_name = "studio-" + "".join(secrets.choice(alphabet) for _ in range(10))
        password = "".join(secrets.choice(alphabet) for _ in range(16))
        qr_text = f"WIFI:T:ADB;S:{service_name};P:{password};;"
        return qr_text, service_name, password

    def _discover_service(self, service_type: str, match_name: str | None = None,
                          match_ip: str | None = None,
                          timeout: float = 90.0) -> tuple[str, int] | None:
        """Wait for an mDNS service matching the criteria; returns (ip, port) or None."""
        found: queue.Queue = queue.Queue()

        def on_change(zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange):
            if state_change is not ServiceStateChange.Added:
                return
            if match_name and not name.startswith(match_name):
                return
            info = zeroconf.get_service_info(service_type, name)
            if not info:
                return
            ip = next((a for a in info.parsed_addresses() if ":" not in a), None)
            if not ip:
                return
            if match_ip and ip != match_ip:
                return
            found.put((ip, info.port))

        zc = Zeroconf()
        try:
            ServiceBrowser(zc, service_type, handlers=[on_change])
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self._stop_requested:
                    return None
                try:
                    return found.get(timeout=0.5)
                except queue.Empty:
                    continue
            return None
        finally:
            zc.close()

    def _pair_and_connect_qr(self, timeout: float = PAIR_DISCOVER_TIMEOUT,
                             qr_data: tuple[str, str, str] | None = None) -> str:
        """Pair + connect a wireless device by having the tablet scan a QR code."""
        if qr_data is None:
            qr_text, service_name, password = self._generate_qr_pairing_data()
            self.qr_data_ready.emit(qr_text, service_name)
        else:
            qr_text, service_name, password = qr_data

        self._log("info", "  Waiting for the tablet to scan the QR code...")
        self._log("info",
                  "  On the tablet: Settings → Developer Options → Wireless debugging → "
                  "'Pair device with QR code'.")

        pair_addr = self._discover_service(
            ADB_PAIRING_SERVICE, match_name=service_name, timeout=timeout,
        )
        if pair_addr is None:
            raise PairingDiscoveryTimeout(
                f"Timed out after {int(timeout)}s waiting for the tablet to scan the QR code."
            )

        pair_ip, pair_port = pair_addr
        self._log("success", f"  Tablet found for pairing: {pair_ip}:{pair_port}")
        self._log("info", "  Pairing...")

        result = self._run_cmd(
            ["adb", "pair", f"{pair_ip}:{pair_port}", password], check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode().strip()
            self._log("warning", f"  Pairing reported: {stderr or 'unknown error'}")
            if "protocol fault" in stderr:
                self._log("warning",
                          "  'protocol fault' here is usually a race with the tablet — "
                          "pairing may have actually succeeded. Continuing to connect.")

        self._log("info", "  Waiting for the tablet's connect port...")
        conn_addr = self._discover_service(
            ADB_CONNECT_SERVICE, match_ip=pair_ip, timeout=CONNECT_DISCOVER_TIMEOUT,
        )
        if conn_addr:
            conn_ip, conn_port = conn_addr
        elif self.wireless.ip and self.wireless.connect_port:
            conn_ip = self.wireless.ip.strip()
            conn_port = int(self.wireless.connect_port)
        else:
            raise RuntimeError(
                "Could not discover the tablet's connect port. Check that Wireless "
                "debugging is still on and both devices are on the same network."
            )

        self._log("info", f"  Connecting to {conn_ip}:{conn_port}...")
        try:
            self._run_cmd(["adb", "connect", f"{conn_ip}:{conn_port}"],
                          check=False, timeout=int(ADB_CONNECT_TIMEOUT))
        except Exception as e:
            self._log("warning", f"  adb connect failed: {e}")

        for _ in range(WIRELESS_POLL_ATTEMPTS):
            if self._stop_requested:
                raise RuntimeError("Cancelled by user")
            serial = self._detect_tablet()
            if serial:
                return serial
            time.sleep(POLL_INTERVAL)

        raise RuntimeError(
            "QR pairing/connect completed but the device is not visible in "
            "'adb devices'. Check that both devices share the same network."
        )

    def _detect_gnome_major(self) -> int | None:
        """Return the GNOME major version, or None if it can't be determined."""
        for cmd in (["gnome-shell", "--version"], ["mutter", "--version"]):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=5,
                )
                version = result.stdout.strip()
                for token in version.replace(",", " ").split():
                    parts = token.split(".")
                    if len(parts) >= 2 and parts[0].isdigit():
                        return int(parts[0])
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        return None

    def _warn_gnome_49_incompatibility(self):
        """Warn if GNOME 49+ will break the Microsoft Windows App RDP client."""
        major = self._detect_gnome_major()
        if major is not None and major >= 49:
            self._log("warning",
                      "GNOME 49+ uses RDSTLS security. Microsoft Windows App may fail to connect; "
                      "use aRDP or Remmina on the tablet instead.")

    def _disable_system_rdp(self):
        """Disable system-level Remote Login (conflicts with user-level)."""
        cmds = [
            ["grdctl", "--system", "rdp", "disable"],
            ["systemctl", "stop", "gnome-remote-desktop.service"],
            ["systemctl", "disable", "gnome-remote-desktop.service"],
        ]
        for cmd in cmds:
            try:
                self._run_cmd(cmd, check=False, sudo=True)
            except Exception:
                pass  # These are best-effort; may fail if already disabled

    def _enable_user_rdp(self):
        """Enable user-level Desktop Sharing with extend mode."""
        # Enable RDP
        self._run_cmd(["grdctl", "rdp", "enable"])

        # Disable view-only (allows control from tablet)
        self._run_cmd(["grdctl", "rdp", "disable-view-only"])

        # THE KEY SETTING - creates a virtual extended monitor
        self._run_cmd([
            "gsettings", "set",
            "org.gnome.desktop.remote-desktop.rdp",
            "screen-share-mode", "extend",
        ])

        # Set credentials
        self._run_cmd([
            "grdctl", "rdp", "set-credentials", self.username, self.password,
        ])

        # Restart the user service
        self._run_cmd(["systemctl", "--user", "daemon-reload"])
        self._run_cmd(["systemctl", "--user", "restart", "gnome-remote-desktop"])

        # Verify configuration
        time.sleep(2)
        result = self._run_cmd(["grdctl", "status"])
        status_output = result.stdout.decode()
        if "Status: enabled" not in status_output or "View-only: no" not in status_output:
            self._log("warning", "  RDP status verification failed, but continuing...")

        # Verify extend mode
        result = self._run_cmd([
            "gsettings", "get",
            "org.gnome.desktop.remote-desktop.rdp",
            "screen-share-mode",
        ])
        mode = result.stdout.decode().strip()
        self._log("success", f"  Screen share mode: {mode}")

        # Verify port is listening
        result = self._run_cmd(["ss", "-tlnp"], check=False)
        if f":{RDP_PORT}" in result.stdout.decode():
            self._log("success", f"  Port {RDP_PORT} is listening")
        else:
            self._log("warning", f"  Port {RDP_PORT} may not be listening yet")

    def _adb_prefix(self) -> list[str]:
        """Return ['adb', '-s', serial] when a device serial is known, else ['adb']."""
        return ["adb", "-s", self._serial] if self._serial else ["adb"]

    def _setup_adb_tunnel(self):
        """Create ADB reverse tunnel for RDP."""
        self._run_cmd(self._adb_prefix() + [
            "reverse", f"tcp:{RDP_PORT}", f"tcp:{RDP_PORT}",
        ])

        # Verify tunnel
        result = self._run_cmd(self._adb_prefix() + ["reverse", "--list"], check=False)
        if f"tcp:{RDP_PORT}" in result.stdout.decode():
            self._log("success", f"  Tunnel established: tablet 127.0.0.1:{RDP_PORT} -> laptop :{RDP_PORT}")
        else:
            raise RuntimeError("Failed to verify ADB tunnel")

    def _verify_rdp_connectivity(self) -> bool:
        """Verify RDP port is actually accepting connections."""
        try:
            result = subprocess.run(
                ["nc", "-z", "127.0.0.1", str(RDP_PORT)],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                self._log("success", f"  RDP port {RDP_PORT} is accepting connections")
                return True
            else:
                self._log("warning", f"  RDP port {RDP_PORT} is not accepting connections")
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._log("warning", "  RDP connectivity check skipped (nc not available)")
            return True  # Assume OK if we can't check

    def _restart_grd_service(self):
        """Restart gnome-remote-desktop service."""
        self._log("info", "  Restarting gnome-remote-desktop service...")
        try:
            self._run_cmd(["systemctl", "--user", "restart", "gnome-remote-desktop"])
            time.sleep(2)
            self._log("success", "  gnome-remote-desktop restarted")
        except Exception as e:
            self._log("warning", f"  Failed to restart gnome-remote-desktop: {e}")

    def _check_health(self) -> dict:
        """Check health of all connection components."""
        health = {"adb": False, "tunnel": False, "rdp": False}

        # Check ADB device
        tablet = self._detect_tablet()
        if tablet:
            health["adb"] = True

        # Check tunnel
        try:
            result = subprocess.run(
                self._adb_prefix() + ["reverse", "--list"],
                capture_output=True, text=True, timeout=5,
            )
            if f"tcp:{RDP_PORT}" in result.stdout:
                health["tunnel"] = True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Check RDP port
        try:
            result = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True, text=True, timeout=5,
            )
            if f":{RDP_PORT}" in result.stdout:
                health["rdp"] = True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return health

    def _monitor(self):
        """Monitor connection health after successful setup."""
        self._log("info", "=== Monitoring connection (health check every 10s) ===")
        consecutive_failures = 0

        while not self._stop_requested:
            time.sleep(HEALTH_CHECK_INTERVAL)

            if self._stop_requested:
                break

            health = self._check_health()

            # Log state changes
            if not health["adb"]:
                self._log("warning", "Health check: tablet disconnected")
            if not health["tunnel"]:
                self._log("warning", "Health check: ADB tunnel broken")
            if not health["rdp"]:
                self._log("warning", "Health check: RDP port not listening")

            self.status_changed.emit(health)

            # If everything is fine, reset failure counter
            if health["adb"] and health["tunnel"] and health["rdp"]:
                consecutive_failures = 0
                continue

            consecutive_failures += 1

            # Try to reconnect once
            if consecutive_failures == 1:
                self._log("info", "Attempting automatic reconnection...")
                if self._reconnect():
                    self._log("success", "Reconnection successful")
                    consecutive_failures = 0
                    continue

            # If reconnection failed or we've already retried, give up
            if consecutive_failures >= 2:
                reason = self._get_failure_reason(health)
                self._log("error", f"Connection lost: {reason}")
                self.connection_lost.emit(reason)
                break

    def _reconnect(self) -> bool:
        """Attempt to reconnect after failure."""
        try:
            # Check if tablet is still connected
            if not self._detect_tablet():
                self._log("warning", "  Tablet not found, cannot reconnect")
                return False

            # Restart gnome-remote-desktop if RDP port is down
            health = self._check_health()
            if not health["rdp"]:
                self._restart_grd_service()
                time.sleep(3)

            # Re-establish ADB tunnel if broken
            if not health["tunnel"]:
                self._log("info", "  Re-establishing ADB tunnel...")
                try:
                    subprocess.run(
                        self._adb_prefix() + ["reverse", "--remove-all"],
                        capture_output=True, timeout=5,
                    )
                except Exception:
                    pass

                try:
                    result = subprocess.run(
                        self._adb_prefix() + ["reverse", f"tcp:{RDP_PORT}", f"tcp:{RDP_PORT}"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode != 0:
                        self._log("warning", f"  Failed to create tunnel: {result.stderr}")
                        return False
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    self._log("warning", f"  Failed to create tunnel: {e}")
                    return False

            # Verify everything is working now
            time.sleep(2)
            final_health = self._check_health()
            if final_health["adb"] and final_health["tunnel"] and final_health["rdp"]:
                return True

            self._log("warning", "  Reconnection incomplete")
            return False

        except Exception as e:
            self._log("warning", f"  Reconnection error: {e}")
            return False

    def _get_failure_reason(self, health: dict) -> str:
        """Generate a human-readable failure reason."""
        reasons = []
        if not health["adb"]:
            reasons.append("tablet disconnected")
        if not health["tunnel"]:
            reasons.append("ADB tunnel broken")
        if not health["rdp"]:
            reasons.append("RDP service not running")
        return "; ".join(reasons) if reasons else "unknown error"

    def disconnect(self):
        """Tear down the connection."""
        self._log("info", "=== Disconnecting ===")

        try:
            self._run_cmd(self._adb_prefix() + ["reverse", "--remove-all"], check=False)
            self._log("info", "  ADB tunnels removed")
        except Exception as e:
            self._log("warning", f"  Error removing ADB tunnels: {e}")

        if self.mode == "wireless" and self.wireless.ip:
            try:
                self._run_cmd(["adb", "disconnect", self.wireless.ip], check=False)
                self._log("info", "  Wireless device disconnected")
            except Exception as e:
                self._log("warning", f"  Error disconnecting wireless device: {e}")

        try:
            self._run_cmd(["grdctl", "rdp", "disable"], check=False)
            self._log("info", "  RDP disabled")
        except Exception as e:
            self._log("warning", f"  Error disabling RDP: {e}")

        try:
            self._run_cmd(["systemctl", "--user", "stop", "gnome-remote-desktop"], check=False)
            self._log("info", "  gnome-remote-desktop service stopped")
        except Exception as e:
            self._log("warning", f"  Error stopping service: {e}")

        self.status_changed.emit({"adb": False, "rdp": False, "tunnel": False})
        self._log("success", "=== Disconnected ===")
