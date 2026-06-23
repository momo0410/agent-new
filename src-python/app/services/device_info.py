import platform
import subprocess
from typing import Optional
from app.models.types import DeviceInfo
def _get_windows_uuid() -> str:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"
def _get_macos_uuid() -> str:
    try:
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "IOPlatformUUID" in line:
                    parts = line.split('"')
                    if len(parts) >= 4:
                        return parts[3]
    except Exception:
        pass
    return "unknown"
def _get_linux_uuid() -> str:
    try:
        with open("/etc/machine-id") as f:
            return f.read().strip()
    except Exception:
        pass
    try:
        with open("/var/lib/dbus/machine-id") as f:
            return f.read().strip()
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["dmidecode", "-s", "system-uuid"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"
def _get_device_type() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "macos"
    elif system == "linux":
        return "linux"
    return "unknown"
def _get_device_name() -> str:
    system = platform.system().lower()
    if system == "windows":
        try:
            result = subprocess.run(
                ["hostname"], capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
    elif system == "darwin":
        try:
            result = subprocess.run(
                ["scutil", "--get", "ComputerName"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
    elif system == "linux":
        try:
            with open("/etc/hostname") as f:
                return f.read().strip()
        except Exception:
            pass
        try:
            result = subprocess.run(
                ["hostname"], capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
    return platform.node() or "Unknown Device"
def get_device_uuid() -> DeviceInfo:
    system = platform.system().lower()
    if system == "windows":
        device_uuid = _get_windows_uuid()
    elif system == "darwin":
        device_uuid = _get_macos_uuid()
    elif system == "linux":
        device_uuid = _get_linux_uuid()
    else:
        device_uuid = "unknown"
    return DeviceInfo(
        device_uuid=device_uuid,
        device_type=_get_device_type(),
        device_name=_get_device_name(),
    )