"""System tray icon module using pystray and Pillow."""

import sys
import threading
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pystray
from pystray import MenuItem, Menu

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / "assets"


def _icon_path() -> Path:
    """Platform-appropriate icon path. PNG on Mac (better support), ICO on Windows."""
    if sys.platform == "darwin":
        p = ASSETS_DIR / "icon.png"
        if p.exists():
            return p
    return ASSETS_DIR / "icon.ico"


class TrayManager:
    """Manages a system-tray icon with menu actions.

    Parameters
    ----------
    on_open : callable
        Callback invoked when the user clicks *Open*.
    on_process_now : callable
        Callback invoked when the user clicks *Process Now*.
    on_toggle_watching : callable
        Callback invoked when the user clicks *Start/Stop Watching*.
    on_quit : callable
        Callback invoked when the user clicks *Quit*.
    """

    def __init__(self, on_open, on_process_now, on_toggle_watching, on_quit):
        self._on_open = on_open
        self._on_process_now = on_process_now
        self._on_toggle_watching = on_toggle_watching
        self._on_quit = on_quit
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Create the tray icon and run it on a daemon thread."""
        image = self._create_icon()
        menu = self._build_menu()
        self._icon = pystray.Icon("TPV2Garmin", image, "TPV2Garmin", menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        logger.info("System tray icon started.")

    def stop(self) -> None:
        """Stop the tray icon (and its background thread)."""
        if self._icon is not None:
            self._icon.stop()
            logger.info("System tray icon stopped.")

    def update_title(self, text: str) -> None:
        """Update the icon hover/tooltip text."""
        if self._icon is not None:
            self._icon.title = text

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_icon() -> Image.Image:
        """Load the icon from assets, or generate a fallback."""
        icon_path = _icon_path()
        if icon_path.exists():
            try:
                img = Image.open(icon_path)
                logger.debug("Loaded tray icon from %s", icon_path)
                return img
            except Exception:
                logger.warning(
                    "Failed to open %s; falling back to generated icon.",
                    icon_path,
                    exc_info=True,
                )

        # Fallback: 64x64 blue square with a white "G".
        img = Image.new("RGB", (64, 64), color=(41, 98, 255))
        draw = ImageDraw.Draw(img)
        if sys.platform == "win32":
            font_paths = ["arial.ttf"]
        else:
            font_paths = [
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            ]
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, 40)
                break
            except OSError:
                continue
        if font is None:
            font = ImageFont.load_default()
        draw.text((16, 8), "G", fill="white", font=font)
        logger.debug("Using generated fallback tray icon.")
        return img

    def _build_menu(self) -> Menu:
        """Build and return the right-click context menu."""
        return Menu(
            MenuItem("Open", self._on_open),
            MenuItem("Process Now", self._on_process_now),
            Menu.SEPARATOR,
            MenuItem("Start/Stop Watching", self._on_toggle_watching),
            Menu.SEPARATOR,
            MenuItem("Quit", self._on_quit),
        )
