"""
Auto-detect the installed Bambu Studio version.

Cross-platform detection with session-level caching.
Falls back to "02.00.00.00" if Bambu Studio is not found.
"""

import sys

_FALLBACK_VERSION = "02.00.00.00"
_cached_version = None


def get_bambu_version_string():
    """Return a string like ``"BambuStudio-02.04.00.70"``."""
    global _cached_version
    if _cached_version is not None:
        return _cached_version

    raw = _detect_version()
    _cached_version = f"BambuStudio-{raw}"
    return _cached_version


def _detect_version():
    """Try platform-specific detection, return dotted version string."""
    platform = sys.platform
    if platform == "win32":
        ver = _detect_windows_registry()
        if ver:
            return ver
        ver = _detect_windows_pe()
        if ver:
            return ver
    elif platform == "darwin":
        ver = _detect_macos()
        if ver:
            return ver
    # Linux and all other platforms: graceful fallback
    return _FALLBACK_VERSION


# ------------------------------------------------------------------ #
# Windows: registry lookup (primary)
# ------------------------------------------------------------------ #

def _detect_windows_registry():
    """Read DisplayVersion from the Windows Uninstall registry."""
    try:
        import winreg
    except ImportError:
        return None

    uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, uninstall_key
        ) as parent:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(parent, i)
                    i += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(parent, subkey_name) as subkey:
                        display_name, _ = winreg.QueryValueEx(
                            subkey, "DisplayName"
                        )
                        if "Bambu Studio" in str(display_name):
                            version, _ = winreg.QueryValueEx(
                                subkey, "DisplayVersion"
                            )
                            return _normalise(str(version))
                except OSError:
                    continue
    except OSError:
        pass
    return None


# ------------------------------------------------------------------ #
# Windows: PE file version (fallback)
# ------------------------------------------------------------------ #

def _detect_windows_pe():
    """Read file version from bambu-studio.exe via Win32 API."""
    import ctypes
    import os

    exe = r"C:\Program Files\Bambu Studio\bambu-studio.exe"
    if not os.path.isfile(exe):
        return None

    try:
        ver_dll = ctypes.windll.version
        size = ver_dll.GetFileVersionInfoSizeW(exe, None)
        if not size:
            return None

        buf = ctypes.create_string_buffer(size)
        if not ver_dll.GetFileVersionInfoW(exe, 0, size, buf):
            return None

        # Query the root block for VS_FIXEDFILEINFO
        p_val = ctypes.c_void_p()
        val_len = ctypes.c_uint()
        if not ver_dll.VerQueryValueW(
            buf, "\\", ctypes.byref(p_val), ctypes.byref(val_len)
        ):
            return None

        # VS_FIXEDFILEINFO structure: dwFileVersionMS, dwFileVersionLS
        # at offsets 8 and 12 (each 4 bytes, after dwSignature + dwStrucVersion)
        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature", ctypes.c_uint32),
                ("dwStrucVersion", ctypes.c_uint32),
                ("dwFileVersionMS", ctypes.c_uint32),
                ("dwFileVersionLS", ctypes.c_uint32),
            ]

        info = ctypes.cast(
            p_val, ctypes.POINTER(VS_FIXEDFILEINFO)
        ).contents
        major = (info.dwFileVersionMS >> 16) & 0xFFFF
        minor = info.dwFileVersionMS & 0xFFFF
        patch = (info.dwFileVersionLS >> 16) & 0xFFFF
        build = info.dwFileVersionLS & 0xFFFF
        return f"{major:02d}.{minor:02d}.{patch:02d}.{build:02d}"
    except Exception:
        return None


# ------------------------------------------------------------------ #
# macOS: Info.plist
# ------------------------------------------------------------------ #

def _detect_macos():
    """Read CFBundleShortVersionString from BambuStudio.app."""
    import os

    plist_path = "/Applications/BambuStudio.app/Contents/Info.plist"
    if not os.path.isfile(plist_path):
        return None

    try:
        import plistlib
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)
        version = plist.get("CFBundleShortVersionString", "")
        if version:
            return _normalise(version)
    except Exception:
        pass
    return None


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _normalise(version_str):
    """Ensure the version has exactly 4 dot-separated zero-padded parts."""
    parts = version_str.replace("-", ".").split(".")
    # Keep only numeric parts
    numeric = []
    for p in parts:
        digits = "".join(c for c in p if c.isdigit())
        if digits:
            numeric.append(digits)
    while len(numeric) < 4:
        numeric.append("0")
    return ".".join(f"{int(n):02d}" for n in numeric[:4])
