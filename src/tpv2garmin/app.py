"""TPV2Garmin main application — tkinter GUI entry point."""

from __future__ import annotations

import logging
import queue
import sys
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from tpv2garmin.config import get_config_manager, LOG_FILE
from tpv2garmin.fixer import ensure_patch
from tpv2garmin.notifications import (
    QueueLogHandler,
    get_notifier,
    setup_logging,
)

logger = logging.getLogger(__name__)

LOG_POLL_MS = 250  # ms between queue → Text widget updates


def _set_mac_dock_icon() -> None:
    """Set the Dock icon on macOS to match the menu bar icon (requires PyObjC)."""
    if sys.platform != "darwin":
        return
    icon_path = Path(__file__).parent / "assets" / "icon.png"
    if not icon_path.exists():
        return
    try:
        from AppKit import NSApplication, NSImage

        app = NSApplication.sharedApplication()
        img = NSImage.alloc().initWithContentsOfFile_(str(icon_path.resolve()))
        if img is not None:
            app.setApplicationIconImage_(img)
            logger.debug("Set Dock icon from %s", icon_path)
    except ImportError:
        pass  # PyObjC not available
    except Exception:
        logger.debug("Could not set Dock icon", exc_info=True)


def _set_mac_dock_visible(visible: bool) -> None:
    """Show or hide the Dock icon on macOS (for minimize-to-menu-bar behavior)."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
        )

        app = NSApplication.sharedApplication()
        if visible:
            app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
            app.activateIgnoringOtherApps_(True)
            _set_mac_dock_icon()  # Restore custom icon
        else:
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            logger.debug("Dock icon hidden (activation policy: Accessory)")
    except ImportError:
        pass  # PyObjC not available
    except Exception:
        logger.debug("Could not toggle Dock icon visibility", exc_info=True)


def _log_font() -> tuple[str, int]:
    """Monospace font for the activity log. Consolas on Windows, Menlo on Mac."""
    if sys.platform == "darwin":
        return ("Menlo", 9)
    if sys.platform == "win32":
        return ("Consolas", 9)
    return ("Monospace", 9)


class MainWindow:
    """Main application window for TPV2Garmin."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TPV2Garmin")
        self.root.geometry("560x420")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._cm = get_config_manager()
        self._pipeline = None
        self._watcher = None
        self._process_monitor = None
        self._tray = None
        self._watching = False
        self._ui_update_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._quit_requested = False

        self._build_ui()
        self._wire_pipeline()
        self._start_log_poll()
        self._update_status_display()

        # Auto-start watching if configured
        config = self._cm.config
        if config.run_mode == "tpv_linked":
            self._start_process_monitor()
        else:
            self._start_watching()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 4}
        config = self._cm.config

        # ── Info row ──────────────────────────────────────────────────────
        info_frame = tk.Frame(self.root)
        info_frame.pack(fill="x", padx=12, pady=(12, 0))

        tk.Label(info_frame, text="Watching:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self._folder_label = tk.Label(
            info_frame, text=config.fitfiles_path or "(not set)", anchor="w"
        )
        self._folder_label.grid(row=0, column=1, sticky="w", padx=(4, 0))

        tk.Label(info_frame, text="Device:", font=("", 9, "bold")).grid(
            row=1, column=0, sticky="w"
        )
        self._device_label = tk.Label(
            info_frame, text=config.device_name or "(not set)", anchor="w"
        )
        self._device_label.grid(row=1, column=1, sticky="w", padx=(4, 0))

        tk.Label(info_frame, text="Status:", font=("", 9, "bold")).grid(
            row=2, column=0, sticky="w"
        )
        self._status_var = tk.StringVar(value="Idle")
        self._status_label = tk.Label(
            info_frame, textvariable=self._status_var, fg="grey", anchor="w"
        )
        self._status_label.grid(row=2, column=1, sticky="w", padx=(4, 0))

        # ── Button row ────────────────────────────────────────────────────
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", **pad)

        self._watch_btn = ttk.Button(
            btn_frame, text="Start Watching", command=self._toggle_watching
        )
        self._watch_btn.pack(side="left", padx=(0, 8))

        ttk.Button(
            btn_frame, text="Process Now", command=self._process_now
        ).pack(side="left")

        # ── Activity log ──────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self.root, text="Activity Log")
        log_frame.pack(fill="both", expand=True, padx=12, pady=4)

        self._log_text = tk.Text(
            log_frame, height=12, wrap="word", state="disabled",
            bg="#1e1e1e", fg="#cccccc", font=_log_font(),
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True, padx=2, pady=2)

        # ── Bottom bar ────────────────────────────────────────────────────
        bottom = tk.Frame(self.root)
        bottom.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Button(bottom, text="Settings", command=self._open_settings).pack(
            side="left"
        )
        minimize_label = "Minimize to Menu Bar" if sys.platform == "darwin" else "Minimize to Tray"
        ttk.Button(bottom, text=minimize_label, command=self._minimize_to_tray).pack(
            side="right"
        )

    # ── Pipeline wiring ───────────────────────────────────────────────────

    def _wire_pipeline(self) -> None:
        from tpv2garmin.pipeline import Pipeline

        self._pipeline = Pipeline()
        self._pipeline.on_file_detected = self._cb_file_detected
        self._pipeline.on_file_processing = self._cb_file_processing
        self._pipeline.on_file_success = self._cb_file_success
        self._pipeline.on_file_error = self._cb_file_error
        self._pipeline.on_auth_required = self._cb_auth_required

    def _cb_file_detected(self, path: Path) -> None:
        # Pipeline runs in worker thread; Tk requires main thread on macOS
        self._ui_update_queue.put(("Processing...", "orange"))

    def _cb_file_processing(self, path: Path) -> None:
        pass  # already logged

    def _cb_file_success(self, path: Path) -> None:
        self._ui_update_queue.put(("Watching for new files", "green"))
        get_notifier().notify_success(path.name)

    def _cb_file_error(self, path: Path, error: str) -> None:
        self._ui_update_queue.put(("Error — see log", "red"))
        get_notifier().notify_error(path.name, error)

    def _cb_auth_required(self) -> None:
        self._ui_update_queue.put(("Authentication required", "red"))
        get_notifier().notify_auth_required()
        self.root.after(0, self._restore_window)

    def _drain_ui_updates(self) -> bool:
        """Process pending UI updates (main thread only). Returns False if quit requested."""
        if self._quit_requested:
            self._quit_requested = False
            self._quit()
            return False
        while True:
            try:
                text, colour = self._ui_update_queue.get_nowait()
                if text == "__open__":
                    self._restore_window()
                elif text == "__process_now__":
                    self._process_now()
                elif text == "__toggle__":
                    self._toggle_watching()
                else:
                    self._set_status(text, colour)
            except queue.Empty:
                break
        return True

    # ── Watching control ──────────────────────────────────────────────────

    def _start_watching(self) -> None:
        if self._watching:
            return

        config = self._cm.config
        if not config.fitfiles_path:
            logger.warning("No FIT files folder configured")
            return

        from tpv2garmin.watcher import FolderWatcher

        folder = Path(config.fitfiles_path)
        self._watcher = FolderWatcher(folder, self._pipeline.submit)
        self._watcher.start()
        self._watching = True
        self._update_status_display()
        logger.info("Watching started: %s", folder)

    def _stop_watching(self) -> None:
        if not self._watching:
            return
        if self._watcher:
            self._watcher.stop()
        self._watching = False
        self._update_status_display()
        logger.info("Watching stopped")

    def _toggle_watching(self) -> None:
        if self._watching:
            self._stop_watching()
        else:
            self._start_watching()

    def _process_now(self) -> None:
        config = self._cm.config
        if not config.fitfiles_path:
            logger.warning("No FIT files folder configured")
            return
        folder = Path(config.fitfiles_path)
        logger.info("Processing all unprocessed files in %s", folder)
        self._pipeline.process_all_unprocessed(folder)

    # ── TPV-linked mode ───────────────────────────────────────────────────

    def _start_process_monitor(self) -> None:
        from tpv2garmin.process_monitor import ProcessMonitor, TPV_PROCESS_NAME

        self._process_monitor = ProcessMonitor()
        self._process_monitor.on_tpv_detected = self._on_tpv_detected
        self._process_monitor.on_tpv_exited = self._on_tpv_exited
        self._process_monitor.on_grace_expired = self._on_grace_expired
        self._process_monitor.start()
        self._set_status(f"TPV-linked: waiting for {TPV_PROCESS_NAME}", "grey")
        logger.info("TPV-linked mode: monitoring for %s", TPV_PROCESS_NAME)

    def _on_tpv_detected(self) -> None:
        self.root.after(0, self._start_watching)

    def _on_tpv_exited(self) -> None:
        self.root.after(0, lambda: self._set_status("Grace period (5 min)", "orange"))

    def _on_grace_expired(self) -> None:
        from tpv2garmin.process_monitor import TPV_PROCESS_NAME

        self.root.after(0, self._stop_watching)
        self.root.after(0, lambda: self._set_status(
            f"TPV-linked: waiting for {TPV_PROCESS_NAME}", "grey"
        ))

    # ── Status display ────────────────────────────────────────────────────

    def _set_status(self, text: str, colour: str) -> None:
        self._status_var.set(text)
        self._status_label.config(fg=colour)

    def _update_status_display(self) -> None:
        if self._watching:
            self._set_status("Watching for new files", "green")
            self._watch_btn.config(text="Stop Watching")
        else:
            if self._cm.config.run_mode != "tpv_linked":
                self._set_status("Idle", "grey")
            self._watch_btn.config(text="Start Watching")

        config = self._cm.config
        self._folder_label.config(text=config.fitfiles_path or "(not set)")
        self._device_label.config(text=config.device_name or "(not set)")

    # ── Log polling ───────────────────────────────────────────────────────

    def _start_log_poll(self) -> None:
        self._poll_log()

    def _poll_log(self) -> None:
        if not self._drain_ui_updates():
            return  # Quit requested, root is being destroyed
        if _queue_handler is not None:
            messages = _queue_handler.get_messages()
            if messages:
                self._log_text.config(state="normal")
                for msg in messages:
                    self._log_text.insert("end", msg + "\n")
                self._log_text.see("end")
                self._log_text.config(state="disabled")
        self.root.after(LOG_POLL_MS, self._poll_log)

    # ── Settings ──────────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        from tpv2garmin.settings import SettingsDialog

        def _on_settings_saved():
            config = self._cm.config
            self._update_status_display()
            # Restart watching/monitor if mode changed
            if self._watcher:
                self._stop_watching()
            if self._process_monitor:
                self._process_monitor.stop()
                self._process_monitor = None

            if config.run_mode == "tpv_linked":
                self._start_process_monitor()
            else:
                self._start_watching()

        SettingsDialog(self.root, on_save_callback=_on_settings_saved)

    # ── Tray integration ──────────────────────────────────────────────────

    def _minimize_to_tray(self) -> None:
        self.root.withdraw()
        if self._tray is None:
            self._create_tray()
        _set_mac_dock_visible(False)

    def _create_tray(self) -> None:
        from tpv2garmin.tray import TrayManager

        # Quit uses a flag: root.after() from tray thread is unreliable on macOS
        self._tray = TrayManager(
            on_open=lambda: self._ui_update_queue.put(("__open__", "")),
            on_process_now=lambda: self._ui_update_queue.put(("__process_now__", "")),
            on_toggle_watching=lambda: self._ui_update_queue.put(("__toggle__", "")),
            on_quit=lambda: setattr(self, "_quit_requested", True),
        )
        self._tray.start()

    def _restore_window(self) -> None:
        _set_mac_dock_visible(True)
        self.root.deiconify()
        self.root.lift()

    def _on_close(self) -> None:
        """Window close → minimize to tray instead of quitting."""
        self._minimize_to_tray()

    def _quit(self) -> None:
        """Full application exit."""
        self._stop_watching()
        if self._process_monitor:
            self._process_monitor.stop()
        if self._pipeline:
            self._pipeline.shutdown()
        if self._tray:
            self._tray.stop()
        self.root.destroy()


# ── Module-level log handler (shared between setup_logging and MainWindow) ──
_queue_handler: QueueLogHandler | None = None


def main() -> None:
    """Application entry point."""
    global _queue_handler

    # Apply FIT SDK patch before any FIT operations
    ensure_patch()

    # Set up logging
    _queue_handler = QueueLogHandler()
    setup_logging(LOG_FILE, _queue_handler)

    logger.info("TPV2Garmin starting")

    root = tk.Tk()
    _set_mac_dock_icon()
    root.withdraw()  # hide while deciding wizard vs main

    cm = get_config_manager()

    if not cm.config.setup_complete:
        # Show setup wizard first
        from tpv2garmin.wizard import SetupWizard

        def _on_wizard_finish():
            root.deiconify()
            MainWindow(root)

        SetupWizard(root, on_finish=_on_wizard_finish)
    else:
        root.deiconify()
        MainWindow(root)

    root.mainloop()


if __name__ == "__main__":
    main()
