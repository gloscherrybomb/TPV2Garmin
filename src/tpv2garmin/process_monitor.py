"""Process monitor: detect TPVirtual for TPV-linked mode."""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Callable

import psutil

logger = logging.getLogger(__name__)

TPV_PROCESS_NAME = "TPVirtual.exe" if sys.platform == "win32" else "TPVirtual"
POLL_INTERVAL = 5  # seconds between process checks
GRACE_PERIOD = 300  # 5 minutes after TPV exits


class ProcessMonitor:
    """Daemon thread that monitors for TPVirtual.

    On detection → calls on_tpv_detected callback.
    On exit → waits for grace period, then calls on_grace_expired.
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False

        # Callbacks
        self.on_tpv_detected: Callable[[], None] | None = None
        self.on_tpv_exited: Callable[[], None] | None = None
        self.on_grace_expired: Callable[[], None] | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start monitoring in a daemon thread."""
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="tpv-monitor"
        )
        self._thread.start()
        logger.info("Process monitor started")

    def stop(self) -> None:
        """Stop the monitor thread."""
        if not self._running:
            return
        self._stop_event.set()
        self._running = False
        self._thread = None
        logger.info("Process monitor stopped")

    def _monitor_loop(self) -> None:
        """Main loop: idle-poll for TPV, then wait for exit + grace."""
        while not self._stop_event.is_set():
            proc = self._find_tpv()
            if proc is not None:
                logger.info("TPVirtual detected (PID %d)", proc.pid)
                if self.on_tpv_detected:
                    self.on_tpv_detected()

                # Wait for the process to exit (zero CPU — blocks on OS wait)
                self._wait_for_exit(proc)

                logger.info("TPVirtual exited")
                if self.on_tpv_exited:
                    self.on_tpv_exited()

                # Grace period
                logger.info("Grace period: %ds", GRACE_PERIOD)
                if self._stop_event.wait(GRACE_PERIOD):
                    break

                logger.info("Grace period expired")
                if self.on_grace_expired:
                    self.on_grace_expired()
            else:
                self._stop_event.wait(POLL_INTERVAL)

    def _find_tpv(self) -> psutil.Process | None:
        """Scan running processes for TPVirtual."""
        try:
            for proc in psutil.process_iter(["name"]):
                try:
                    if proc.info["name"] and proc.info["name"].lower() == TPV_PROCESS_NAME.lower():
                        return proc
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            logger.debug("Error scanning processes", exc_info=True)
        return None

    def _wait_for_exit(self, proc: psutil.Process) -> None:
        """Block until *proc* exits, or until stop is requested."""
        try:
            while not self._stop_event.is_set():
                try:
                    proc.wait(timeout=2)
                    return  # Process exited
                except psutil.TimeoutExpired:
                    continue
                except psutil.NoSuchProcess:
                    return
        except Exception:
            logger.debug("Error waiting for process exit", exc_info=True)
