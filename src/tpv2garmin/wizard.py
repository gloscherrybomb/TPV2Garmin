"""Three-step setup wizard for TPV2Garmin (tkinter Toplevel)."""

import queue
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import Callable

from tpv2garmin.config import (
    get_config_manager,
    get_device_choices,
    DEFAULT_DEVICE_PRODUCT,
)
from tpv2garmin.auth import get_auth_manager

# ── Constants ────────────────────────────────────────────────────────────────
WIZARD_WIDTH = 450
WIZARD_HEIGHT = 400
PAD_X = 20
PAD_Y = 6


class SetupWizard(tk.Toplevel):
    """Three-step setup wizard: Garmin Login, Folder Selection, Device."""

    def __init__(self, parent: tk.Tk, on_finish: Callable[[], None] | None = None):
        super().__init__(parent)
        self.parent = parent
        self.on_finish = on_finish

        # ── Window chrome ────────────────────────────────────────────────
        self.title("TPV2Garmin Setup")
        self.resizable(False, False)
        self._center_window(WIZARD_WIDTH, WIZARD_HEIGHT)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.grab_set()

        # ── State ────────────────────────────────────────────────────────
        self._current_step = 0
        self._garmin_authenticated = False
        self._garmin_email = ""
        self._detected_paths: list[Path] = []
        self._device_choices: list[tuple[str, int, str]] = []

        # ── Container for all steps ──────────────────────────────────────
        self._container = tk.Frame(self)
        self._container.pack(fill="both", expand=True)

        self._frames: list[tk.Frame] = []
        self._build_step1()
        self._build_step2()
        self._build_step3()

        # ── Navigation bar ───────────────────────────────────────────────
        nav = tk.Frame(self)
        nav.pack(fill="x", side="bottom", padx=PAD_X, pady=(0, 12))

        self._btn_back = ttk.Button(nav, text="Back", command=self._go_back)
        self._btn_back.pack(side="left")

        self._btn_next = ttk.Button(nav, text="Next", command=self._go_next)
        self._btn_next.pack(side="right")

        self._show_step(0)

    # ── Step 1: Garmin Login ─────────────────────────────────────────────────

    def _build_step1(self) -> None:
        frame = tk.Frame(self._container)
        self._frames.append(frame)

        tk.Label(frame, text="Step 1: Garmin Connect Login", font=("", 12, "bold")).pack(
            anchor="w", padx=PAD_X, pady=(16, 4)
        )
        tk.Label(frame, text="Sign in to your Garmin Connect account.").pack(
            anchor="w", padx=PAD_X, pady=(0, PAD_Y)
        )

        # Email
        tk.Label(frame, text="Email:").pack(anchor="w", padx=PAD_X, pady=(PAD_Y, 0))
        self._email_var = tk.StringVar()
        self._email_entry = ttk.Entry(frame, textvariable=self._email_var, width=40)
        self._email_entry.pack(anchor="w", padx=PAD_X, pady=(0, PAD_Y))

        # Password
        tk.Label(frame, text="Password:").pack(anchor="w", padx=PAD_X, pady=(PAD_Y, 0))
        self._password_var = tk.StringVar()
        self._password_entry = ttk.Entry(
            frame, textvariable=self._password_var, show="*", width=40
        )
        self._password_entry.pack(anchor="w", padx=PAD_X, pady=(0, PAD_Y))

        # Connect button
        self._connect_btn = ttk.Button(frame, text="Connect", command=self._do_login)
        self._connect_btn.pack(anchor="w", padx=PAD_X, pady=PAD_Y)

        # MFA section (hidden initially)
        self._mfa_frame = tk.Frame(frame)

        tk.Label(self._mfa_frame, text="MFA Code:").pack(
            anchor="w", padx=0, pady=(PAD_Y, 0)
        )
        self._mfa_var = tk.StringVar()
        self._mfa_entry = ttk.Entry(self._mfa_frame, textvariable=self._mfa_var, width=20)
        self._mfa_entry.pack(anchor="w", pady=(0, PAD_Y))

        self._mfa_btn = ttk.Button(
            self._mfa_frame, text="Verify", command=self._do_mfa
        )
        self._mfa_btn.pack(anchor="w", pady=PAD_Y)

        # Status label
        self._login_status_var = tk.StringVar()
        self._login_status = tk.Label(
            frame, textvariable=self._login_status_var, fg="grey"
        )
        self._login_status.pack(anchor="w", padx=PAD_X, pady=PAD_Y)

    def _do_login(self) -> None:
        email = self._email_var.get().strip()
        password = self._password_var.get().strip()
        if not email or not password:
            self._set_login_status("Please enter both email and password.", "red")
            return

        self._connect_btn.config(state="disabled")
        self._set_login_status("Connecting...", "grey")

        # Use a queue instead of after() from worker thread — on macOS,
        # after() scheduled from a non-main thread may not fire reliably.
        login_queue: queue.Queue[tuple[str | None, str]] = queue.Queue()

        def _worker():
            auth = get_auth_manager()
            result = auth.login(email, password)
            login_queue.put((result, email))

        threading.Thread(target=_worker, daemon=True).start()
        self._poll_login_result(login_queue)

    def _poll_login_result(
        self, login_queue: queue.Queue[tuple[str | None, str]]
    ) -> None:
        """Poll for login result on main thread (macOS-safe)."""
        try:
            result, email = login_queue.get_nowait()
            self._handle_login_result(result, email)
        except queue.Empty:
            self.after(100, lambda: self._poll_login_result(login_queue))

    def _handle_login_result(self, result: str | None, email: str) -> None:
        self._connect_btn.config(state="normal")

        if result is None:
            # Success
            self._garmin_authenticated = True
            self._garmin_email = email
            self._set_login_status("Logged in successfully.", "green")
            self._mfa_frame.pack_forget()
        elif result == "needs_mfa":
            self._set_login_status("MFA code required. Check your authenticator app.", "orange")
            self._mfa_frame.pack(anchor="w", padx=PAD_X, pady=PAD_Y)
            self._mfa_entry.focus_set()
        else:
            self._set_login_status(result, "red")

    def _do_mfa(self) -> None:
        code = self._mfa_var.get().strip()
        if not code:
            self._set_login_status("Please enter the MFA code.", "red")
            return

        self._mfa_btn.config(state="disabled")
        self._set_login_status("Verifying MFA code...", "grey")

        mfa_queue: queue.Queue[str | None] = queue.Queue()

        def _worker():
            auth = get_auth_manager()
            result = auth.handle_mfa(code)
            mfa_queue.put(result)

        threading.Thread(target=_worker, daemon=True).start()
        self._poll_mfa_result(mfa_queue)

    def _poll_mfa_result(self, mfa_queue: queue.Queue[str | None]) -> None:
        """Poll for MFA result on main thread (macOS-safe)."""
        try:
            result = mfa_queue.get_nowait()
            self._handle_mfa_result(result)
        except queue.Empty:
            self.after(100, lambda: self._poll_mfa_result(mfa_queue))

    def _handle_mfa_result(self, result: str | None) -> None:
        self._mfa_btn.config(state="normal")

        if result is None:
            self._garmin_authenticated = True
            self._garmin_email = self._email_var.get().strip()
            self._set_login_status("MFA verified. Logged in successfully.", "green")
            self._mfa_frame.pack_forget()
        else:
            self._set_login_status(result, "red")

    def _set_login_status(self, text: str, colour: str) -> None:
        self._login_status_var.set(text)
        self._login_status.config(fg=colour)

    # ── Step 2: Folder Selection ─────────────────────────────────────────────

    def _build_step2(self) -> None:
        frame = tk.Frame(self._container)
        self._frames.append(frame)

        tk.Label(frame, text="Step 2: FIT Files Folder", font=("", 12, "bold")).pack(
            anchor="w", padx=PAD_X, pady=(16, 4)
        )
        tk.Label(
            frame,
            text="Select the folder where TPVirtual saves .FIT files.",
            wraplength=WIZARD_WIDTH - 2 * PAD_X,
            justify="left",
        ).pack(anchor="w", padx=PAD_X, pady=(0, PAD_Y))

        # Combobox for detected paths
        self._folder_var = tk.StringVar()
        self._folder_combo = ttk.Combobox(
            frame, textvariable=self._folder_var, width=50, state="readonly"
        )
        self._folder_combo.pack(anchor="w", padx=PAD_X, pady=PAD_Y)

        # Browse button
        ttk.Button(frame, text="Browse...", command=self._browse_folder).pack(
            anchor="w", padx=PAD_X, pady=PAD_Y
        )

        # Status
        self._folder_status_var = tk.StringVar()
        self._folder_status = tk.Label(
            frame, textvariable=self._folder_status_var, fg="grey",
            wraplength=WIZARD_WIDTH - 2 * PAD_X, justify="left",
        )
        self._folder_status.pack(anchor="w", padx=PAD_X, pady=PAD_Y)

    def _detect_fit_folders(self) -> list[Path]:
        """Search common locations for TPVirtual FIT file folders."""
        base_dirs: list[Path] = []
        home = Path.home()

        if sys.platform == "darwin":
            # macOS: ~/TPVirtual/<account_id>/FitFiles (TrainingPeaks help)
            base_dirs.append(home)
        else:
            # Windows: Documents, OneDrive, etc.
            base_dirs.append(home / "Documents")
            base_dirs.append(home / "OneDrive" / "Documents")
            for p in home.glob("OneDrive - *"):
                if p.is_dir():
                    base_dirs.append(p / "Documents")

        # Subfolder may be FITFiles or FitFiles (docs vary)
        fit_subdir_names = ("FITFiles", "FitFiles")
        found: list[Path] = []
        for base in base_dirs:
            if not base.is_dir():
                continue
            tpv_dir = base / "TPVirtual"
            if not tpv_dir.is_dir():
                continue
            for child in tpv_dir.iterdir():
                if not child.is_dir():
                    continue
                for subdir_name in fit_subdir_names:
                    fit_dir = child / subdir_name
                    if fit_dir.is_dir():
                        found.append(fit_dir)
                        break

        # Deduplicate (resolve symlinks / case differences)
        seen: set[str] = set()
        unique: list[Path] = []
        for p in found:
            key = str(p.resolve()).lower()
            if key not in seen:
                seen.add(key)
                unique.append(p)

        return unique

    def _populate_folder_step(self) -> None:
        """Run auto-detection and populate the combobox."""
        self._detected_paths = self._detect_fit_folders()

        if self._detected_paths:
            values = [str(p) for p in self._detected_paths]
            self._folder_combo.config(values=values, state="readonly")
            # Pre-select the first (or only) option
            self._folder_var.set(values[0])
            count = len(self._detected_paths)
            if count == 1:
                self._folder_status_var.set("Auto-detected FIT folder.")
                self._folder_status.config(fg="green")
            else:
                self._folder_status_var.set(
                    f"Found {count} FIT folders. Please select the correct one."
                )
                self._folder_status.config(fg="orange")
        else:
            self._folder_combo.config(values=[], state="disabled")
            self._folder_var.set("")
            self._folder_status_var.set(
                "No FIT folders found automatically. Use Browse to select one."
            )
            self._folder_status.config(fg="orange")

    def _browse_folder(self) -> None:
        chosen = filedialog.askdirectory(
            title="Select FIT Files Folder",
            parent=self,
        )
        if chosen:
            path_str = str(Path(chosen))
            # Add to combo values if not already present
            current_values = list(self._folder_combo.cget("values") or ())
            if path_str not in current_values:
                current_values.append(path_str)
                self._folder_combo.config(values=current_values, state="readonly")
            self._folder_var.set(path_str)
            self._folder_status_var.set("Folder selected manually.")
            self._folder_status.config(fg="green")

    # ── Step 3: Device Selection ─────────────────────────────────────────────

    def _build_step3(self) -> None:
        frame = tk.Frame(self._container)
        self._frames.append(frame)

        tk.Label(frame, text="Step 3: Garmin Device", font=("", 12, "bold")).pack(
            anchor="w", padx=PAD_X, pady=(16, 4)
        )
        tk.Label(
            frame,
            text=(
                "Choose the Garmin device to emulate when uploading activities. "
                "This controls how the activity appears in Garmin Connect."
            ),
            wraplength=WIZARD_WIDTH - 2 * PAD_X,
            justify="left",
        ).pack(anchor="w", padx=PAD_X, pady=(0, PAD_Y))

        # Device combobox
        self._device_var = tk.StringVar()
        self._device_combo = ttk.Combobox(
            frame, textvariable=self._device_var, width=40, state="readonly"
        )
        self._device_combo.pack(anchor="w", padx=PAD_X, pady=PAD_Y)

        # Info label showing category
        self._device_info_var = tk.StringVar()
        tk.Label(frame, textvariable=self._device_info_var, fg="grey").pack(
            anchor="w", padx=PAD_X, pady=(0, PAD_Y)
        )

        self._device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)

    def _populate_device_step(self) -> None:
        """Load device choices and populate the combobox."""
        self._device_choices = get_device_choices()

        # Group: recommended first, then bike computers, watches, trainers, other
        category_order = {
            "bike_computer": 0,
            "watch": 1,
            "trainer": 2,
        }

        display_values: list[str] = []
        for name, product_id, category in self._device_choices:
            display_values.append(f"{name} ({product_id})")

        self._device_combo.config(values=display_values, state="readonly")

        # Select default (Edge 1050)
        default_idx = 0
        for i, (_, product_id, _) in enumerate(self._device_choices):
            if product_id == DEFAULT_DEVICE_PRODUCT:
                default_idx = i
                break

        if display_values:
            self._device_var.set(display_values[default_idx])
            self._update_device_info(default_idx)

    def _on_device_selected(self, _event: tk.Event) -> None:
        idx = self._device_combo.current()
        if idx >= 0:
            self._update_device_info(idx)

    def _update_device_info(self, idx: int) -> None:
        if 0 <= idx < len(self._device_choices):
            _, _, category = self._device_choices[idx]
            label = category.replace("_", " ").title()
            self._device_info_var.set(f"Category: {label}")

    # ── Navigation ───────────────────────────────────────────────────────────

    def _show_step(self, step: int) -> None:
        for f in self._frames:
            f.pack_forget()
        self._frames[step].pack(fill="both", expand=True)
        self._current_step = step

        # Update button text and state
        self._btn_back.config(state="normal" if step > 0 else "disabled")
        self._btn_next.config(text="Finish" if step == 2 else "Next")

        # Populate data when entering a step
        if step == 1:
            self._populate_folder_step()
        elif step == 2:
            self._populate_device_step()

    def _go_back(self) -> None:
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _go_next(self) -> None:
        if not self._validate_current_step():
            return

        if self._current_step < 2:
            self._show_step(self._current_step + 1)
        else:
            self._finish()

    def _validate_current_step(self) -> bool:
        if self._current_step == 0:
            if not self._garmin_authenticated:
                messagebox.showwarning(
                    "Login Required",
                    "Please log in to Garmin Connect before continuing.",
                    parent=self,
                )
                return False
        elif self._current_step == 1:
            folder = self._folder_var.get().strip()
            if not folder:
                messagebox.showwarning(
                    "Folder Required",
                    "Please select a FIT files folder before continuing.",
                    parent=self,
                )
                return False
            if not Path(folder).is_dir():
                messagebox.showwarning(
                    "Invalid Folder",
                    f"The selected folder does not exist:\n{folder}",
                    parent=self,
                )
                return False
        elif self._current_step == 2:
            if self._device_combo.current() < 0:
                messagebox.showwarning(
                    "Device Required",
                    "Please select a Garmin device before finishing.",
                    parent=self,
                )
                return False
        return True

    # ── Finish ───────────────────────────────────────────────────────────────

    def _finish(self) -> None:
        """Save configuration and close the wizard."""
        device_idx = self._device_combo.current()
        device_name, device_product, _ = self._device_choices[device_idx]

        cm = get_config_manager()
        cm.config.garmin_username = self._garmin_email
        cm.config.fitfiles_path = self._folder_var.get().strip()
        cm.config.device_product = device_product
        cm.config.device_name = device_name
        cm.config.setup_complete = True
        cm.save()

        self.grab_release()
        self.destroy()

        if self.on_finish is not None:
            self.on_finish()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _center_window(self, width: int, height: int) -> None:
        self.update_idletasks()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _on_close(self) -> None:
        if self._garmin_authenticated:
            if not messagebox.askyesno(
                "Cancel Setup",
                "Setup is not complete. Are you sure you want to cancel?",
                parent=self,
            ):
                return
        self.grab_release()
        self.destroy()
