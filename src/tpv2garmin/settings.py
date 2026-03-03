"""Settings dialog (tkinter Toplevel) for TPV2Garmin."""

import plistlib
import subprocess
import sys
import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from tpv2garmin import __version__
from tpv2garmin.config import get_config_manager, get_device_choices
from tpv2garmin.auth import get_auth_manager

logger = logging.getLogger(__name__)

# Windows Registry constants
_REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REG_VALUE_NAME = "TPV2Garmin"

# macOS Launch Agent
_LAUNCH_AGENT_LABEL = "com.tpv2garmin"
_LAUNCH_AGENT_FILENAME = f"{_LAUNCH_AGENT_LABEL}.plist"


def _auto_start_label() -> str:
    """Platform-appropriate label for the auto-start checkbox."""
    if sys.platform == "darwin":
        return "Start at login"
    if sys.platform == "win32":
        return "Auto-start with Windows"
    return "Auto-start"


def _tpv_linked_label() -> str:
    """Platform-appropriate label for the TPV-linked run mode."""
    if sys.platform == "darwin":
        return "TPV-linked (activate when TPVirtual is running)"
    return "TPV-linked (activate when TPVirtual.exe is running)"


class SettingsDialog(tk.Toplevel):
    """Modal settings dialog for TPV2Garmin."""

    def __init__(self, parent: tk.Tk, on_save_callback=None) -> None:
        super().__init__(parent)
        self._on_save_callback = on_save_callback
        self._config_manager = get_config_manager()
        self._auth_manager = get_auth_manager()
        self._config = self._config_manager.config

        # Window setup
        self.title("Settings")
        self.geometry("400x500")
        self.resizable(False, False)
        self.transient(parent)

        # Tkinter variables
        self._run_mode_var = tk.StringVar(value=self._config.run_mode)
        self._auto_start_var = tk.BooleanVar(value=_get_auto_start())
        self._notifications_var = tk.BooleanVar(value=self._config.notifications_enabled)
        self._device_var = tk.StringVar()

        # Build the device lookup and display list
        self._device_choices = get_device_choices()
        self._device_display_list = [
            f"{name} ({product_id})"
            for name, product_id, _category in self._device_choices
        ]

        # Set current device selection
        current_display = self._find_device_display(self._config.device_product)
        if current_display:
            self._device_var.set(current_display)
        elif self._device_display_list:
            self._device_var.set(self._device_display_list[0])

        self._build_ui()

        # Make modal
        self.grab_set()
        self.focus_set()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build all widgets using pack layout."""
        pad = {"padx": 10, "pady": (5, 0)}

        # ── Run mode ─────────────────────────────────────────────────────
        run_frame = ttk.LabelFrame(self, text="Run mode")
        run_frame.pack(fill="x", **pad)

        ttk.Radiobutton(
            run_frame,
            text="Watch folder continuously",
            variable=self._run_mode_var,
            value="watch",
        ).pack(anchor="w", padx=10, pady=(5, 0))

        ttk.Radiobutton(
            run_frame,
            text=_tpv_linked_label(),
            variable=self._run_mode_var,
            value="tpv_linked",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        # ── Auto-start ───────────────────────────────────────────────────
        ttk.Checkbutton(
            self,
            text=_auto_start_label(),
            variable=self._auto_start_var,
        ).pack(anchor="w", **pad)

        # ── Notifications ────────────────────────────────────────────────
        ttk.Checkbutton(
            self,
            text="Show toast notifications",
            variable=self._notifications_var,
        ).pack(anchor="w", **pad)

        # ── Device ───────────────────────────────────────────────────────
        device_frame = ttk.LabelFrame(self, text="Device")
        device_frame.pack(fill="x", **pad)

        self._device_combo = ttk.Combobox(
            device_frame,
            textvariable=self._device_var,
            values=self._device_display_list,
            state="readonly",
            width=40,
        )
        self._device_combo.pack(padx=10, pady=5, fill="x")

        # ── Garmin Account ───────────────────────────────────────────────
        account_frame = ttk.LabelFrame(self, text="Garmin Account")
        account_frame.pack(fill="x", **pad)

        username = self._auth_manager.get_username() or "(not set)"
        ttk.Label(account_frame, text=username).pack(
            anchor="w", padx=10, pady=(5, 0),
        )
        ttk.Button(
            account_frame,
            text="Re-authenticate",
            command=self._on_reauth,
        ).pack(anchor="w", padx=10, pady=(2, 5))

        # ── About ────────────────────────────────────────────────────────
        ttk.Label(
            self,
            text=f"TPV2Garmin v{__version__}",
            foreground="grey",
        ).pack(**pad)

        # ── Buttons ──────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(side="bottom", fill="x", padx=10, pady=10)

        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(
            side="right", padx=(5, 0),
        )
        ttk.Button(btn_frame, text="Save", command=self._on_save).pack(
            side="right",
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def _find_device_display(self, product_id: int) -> str | None:
        """Return the display string for a given product_id, or None."""
        for name, pid, _cat in self._device_choices:
            if pid == product_id:
                return f"{name} ({pid})"
        return None

    def _selected_device(self) -> tuple[str, int] | None:
        """Return (name, product_id) for the currently selected device."""
        idx = self._device_combo.current()
        if idx < 0:
            return None
        name, product_id, _cat = self._device_choices[idx]
        return name, product_id

    def _on_reauth(self) -> None:
        """Handle re-authenticate button press via a simple login popup."""
        from tpv2garmin.wizard import SetupWizard
        # Open wizard at step 1 (login only); on_finish just closes it
        popup = SetupWizard(self, on_finish=lambda: None)
        popup.title("Re-authenticate")

    # ── Save / auto-start ────────────────────────────────────────────────

    def _on_save(self) -> None:
        """Persist all settings and close the dialog."""
        cfg = self._config

        # Run mode
        cfg.run_mode = self._run_mode_var.get()

        # Notifications
        cfg.notifications_enabled = self._notifications_var.get()

        # Device
        device = self._selected_device()
        if device:
            cfg.device_name, cfg.device_product = device

        # Auto-start
        auto_start = self._auto_start_var.get()
        cfg.auto_start = auto_start
        _set_auto_start(auto_start)

        # Persist
        self._config_manager.save()

        if self._on_save_callback:
            self._on_save_callback()

        self.destroy()


# ── Auto-start helpers (platform-specific) ───────────────────────────────────


def _get_auto_start() -> bool:
    """Return True if auto-start is configured for this platform."""
    if sys.platform == "win32":
        return _get_auto_start_windows()
    if sys.platform == "darwin":
        return _get_auto_start_mac()
    return False


def _set_auto_start(enabled: bool) -> None:
    """Enable or disable auto-start for this platform."""
    if sys.platform == "win32":
        _set_auto_start_windows(enabled)
    elif sys.platform == "darwin":
        _set_auto_start_mac(enabled)


def _get_auto_start_windows() -> bool:
    """Return True if the Windows Registry Run key exists."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _REG_VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
    except ImportError:
        logger.debug("winreg not available on this platform")
        return False


def _set_auto_start_windows(enabled: bool) -> None:
    """Add or remove the Windows Registry Run entry."""
    try:
        import winreg
    except ImportError:
        logger.debug("winreg not available on this platform")
        return

    if enabled:
        exe_path = sys.executable
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                _REG_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, _REG_VALUE_NAME, 0, winreg.REG_SZ, exe_path)
            logger.info("Auto-start enabled: %s", exe_path)
        except OSError:
            logger.exception("Failed to set auto-start registry value")
    else:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                _REG_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, _REG_VALUE_NAME)
            logger.info("Auto-start disabled")
        except FileNotFoundError:
            pass
        except OSError:
            logger.exception("Failed to remove auto-start registry value")


def _launch_agent_path() -> Path:
    """Path to the Launch Agent plist file."""
    return Path.home() / "Library" / "LaunchAgents" / _LAUNCH_AGENT_FILENAME


def _get_auto_start_mac() -> bool:
    """Return True if the Launch Agent plist exists."""
    return _launch_agent_path().exists()


def _get_launch_agent_program_args() -> list[str]:
    """Return ProgramArguments for the Launch Agent."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "tpv2garmin"]


def _set_auto_start_mac(enabled: bool) -> None:
    """Create or remove the Launch Agent plist and load/unload it."""
    plist_path = _launch_agent_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    if enabled:
        program_args = _get_launch_agent_program_args()
        plist = {
            "Label": _LAUNCH_AGENT_LABEL,
            "ProgramArguments": program_args,
            "RunAtLoad": True,
            "LimitLoadToSessionType": "Aqua",
        }
        plist_path.write_bytes(plistlib.dumps(plist))
        logger.info("Auto-start enabled: %s", program_args)
        # Plist is loaded automatically at next login; no need to launchctl load now
    else:
        # Unload first, then remove plist
        try:
            subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                capture_output=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        if plist_path.exists():
            plist_path.unlink()
            logger.info("Auto-start disabled")
