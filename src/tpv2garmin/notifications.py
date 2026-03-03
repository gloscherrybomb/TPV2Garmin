"""Notifications, logging and queue-based log handler for TPV2Garmin."""

import logging
import queue
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from tpv2garmin.config import get_config_manager

logger = logging.getLogger(__name__)


# ── Toast notifications ──────────────────────────────────────────────────────
class ToastNotifier:
    """Cross-platform desktop notifications (winotify on Windows, desktop-notifier elsewhere)."""

    def __init__(self, app_id: str = "TPV2Garmin") -> None:
        self.app_id = app_id

    def _is_enabled(self) -> bool:
        """Check whether notifications are enabled in config."""
        return get_config_manager().config.notifications_enabled

    def notify_success(self, filename: str) -> None:
        """Toast confirming a successful upload."""
        if not self._is_enabled():
            return
        if sys.platform == "win32":
            self._notify_winotify("Upload Complete", f"Uploaded {filename} to Garmin Connect")
        else:
            self._notify_desktop("Upload Complete", f"Uploaded {filename} to Garmin Connect")

    def notify_error(self, filename: str, error: str) -> None:
        """Toast reporting a processing failure."""
        if not self._is_enabled():
            return
        if sys.platform == "win32":
            self._notify_winotify("Processing Error", f"Failed to process {filename}: {error}")
        else:
            self._notify_desktop("Processing Error", f"Failed to process {filename}: {error}")

    def notify_auth_required(self) -> None:
        """Toast prompting the user to re-authenticate."""
        if not self._is_enabled():
            return
        if sys.platform == "win32":
            self._notify_winotify("Authentication Required", "Please re-authenticate with Garmin Connect")
        else:
            self._notify_desktop("Authentication Required", "Please re-authenticate with Garmin Connect")

    def _notify_winotify(self, title: str, msg: str) -> None:
        """Show notification via winotify (Windows only)."""
        try:
            from winotify import Notification
            toast = Notification(
                app_id=self.app_id,
                title=title,
                msg=msg,
                duration="short",
            )
            toast.show()
        except Exception:
            logger.debug("Failed to show toast", exc_info=True)

    def _notify_desktop(self, title: str, message: str) -> None:
        """Show notification via desktop-notifier (macOS, Linux)."""
        try:
            import asyncio
            from desktop_notifier import DesktopNotifier
            notifier = DesktopNotifier(app_name=self.app_id)
            asyncio.run(notifier.send(title=title, message=message))
        except Exception:
            logger.debug("Failed to show notification", exc_info=True)


# ── Queue-based log handler ─────────────────────────────────────────────────
class QueueLogHandler(logging.Handler):
    """Thread-safe handler that buffers formatted log messages in a queue."""

    def __init__(self) -> None:
        super().__init__()
        self._queue: queue.Queue[str] = queue.Queue()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._queue.put(msg)
        except Exception:
            self.handleError(record)

    def get_messages(self) -> list[str]:
        """Drain the queue and return all pending messages."""
        messages: list[str] = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return messages


# ── Logging setup ────────────────────────────────────────────────────────────
def setup_logging(
    log_file: Path,
    queue_handler: QueueLogHandler | None = None,
) -> None:
    """Configure the root logger with file, console, and optional queue handlers.

    Parameters
    ----------
    log_file:
        Path to the rotating log file (1 MB, 3 backups).
    queue_handler:
        Optional :class:`QueueLogHandler` for in-app log display.
    """
    fmt = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Rotating file handler
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1_048_576, backupCount=3, encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Console handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    # Optional queue handler for GUI consumption
    if queue_handler is not None:
        queue_handler.setFormatter(fmt)
        root.addHandler(queue_handler)


# ── Lazy singleton ───────────────────────────────────────────────────────────
_notifier: ToastNotifier | None = None


def get_notifier() -> ToastNotifier:
    """Get or create the singleton ToastNotifier."""
    global _notifier
    if _notifier is None:
        _notifier = ToastNotifier()
    return _notifier
