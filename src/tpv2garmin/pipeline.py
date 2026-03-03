"""Processing pipeline: detect -> fix -> upload -> log."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Callable

from tpv2garmin.auth import get_auth_manager
from tpv2garmin.fixer import (
    get_fit_distance,
    get_fixer,
    get_unprocessed_files,
    is_processed,
    mark_processed,
    wait_for_write_complete,
)

logger = logging.getLogger(__name__)

MIN_DISTANCE_METERS = 100
MAX_RETRIES = 3
RETRY_BACKOFF = 30  # seconds


class Pipeline:
    """Serialized file-processing pipeline backed by a single-thread executor."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._pending: set[str] = set()
        self._pending_lock = threading.Lock()

        # Callbacks — set by the GUI layer
        self.on_file_detected: Callable[[Path], None] | None = None
        self.on_file_processing: Callable[[Path], None] | None = None
        self.on_file_success: Callable[[Path], None] | None = None
        self.on_file_error: Callable[[Path, str], None] | None = None
        self.on_auth_required: Callable[[], None] | None = None

    # ── Public API ────────────────────────────────────────────────────────

    def submit(self, path: Path) -> None:
        """Submit a file for background processing. Skips if already queued."""
        with self._pending_lock:
            if path.name in self._pending:
                return
            self._pending.add(path.name)
        self._executor.submit(self._process_file_safe, path)

    def process_all_unprocessed(self, folder: Path) -> None:
        """Scan *folder* and submit every unprocessed .fit file."""
        for path in get_unprocessed_files(folder):
            self.submit(path)

    def shutdown(self) -> None:
        """Drain the queue and shut down the executor."""
        self._executor.shutdown(wait=False)

    # ── Internal processing ───────────────────────────────────────────────

    def _process_file_safe(self, path: Path) -> None:
        """Top-level wrapper with error handling."""
        try:
            self._process_file(path)
        except Exception:
            logger.exception("Unhandled error processing %s", path)
        finally:
            with self._pending_lock:
                self._pending.discard(path.name)

    def _process_file(self, path: Path) -> None:
        if self.on_file_detected:
            self.on_file_detected(path)
        logger.info("New file detected: %s", path.name)

        # Wait for the file to finish writing
        if not wait_for_write_complete(path):
            error = "Timed out waiting for file write to complete"
            logger.error(error)
            if self.on_file_error:
                self.on_file_error(path, error)
            return

        # Skip duplicates
        if is_processed(path.name):
            logger.info("Already processed: %s", path.name)
            return

        # Skip files not from today
        file_date = date.fromtimestamp(path.stat().st_mtime)
        if file_date != date.today():
            logger.info("Skipping %s: file date %s is not today", path.name, file_date)
            mark_processed(path.name)
            return

        # Skip short/non-activity files
        distance = get_fit_distance(path)
        if distance is not None and distance < MIN_DISTANCE_METERS:
            logger.info("Skipping %s: distance %.0fm < %dm", path.name, distance, MIN_DISTANCE_METERS)
            mark_processed(path.name)
            return

        if self.on_file_processing:
            self.on_file_processing(path)

        # Fix + upload with retry
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._fix_and_upload(path)
                mark_processed(path.name)
                logger.info("Successfully processed: %s", path.name)
                if self.on_file_success:
                    self.on_file_success(path)
                return
            except AuthError:
                logger.warning("Authentication required")
                if self.on_auth_required:
                    self.on_auth_required()
                return
            except Exception as exc:
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s — retrying in %ds",
                        attempt, MAX_RETRIES, path.name, exc, RETRY_BACKOFF,
                    )
                    time.sleep(RETRY_BACKOFF)
                else:
                    error = str(exc)
                    logger.error("All %d attempts failed for %s: %s", MAX_RETRIES, path.name, error)
                    if self.on_file_error:
                        self.on_file_error(path, error)

    def _fix_and_upload(self, path: Path) -> None:
        """Fix the FIT file and upload it. Raises on failure."""
        auth = get_auth_manager()

        # Ensure we have a valid session
        try:
            auth.refresh_if_needed()
        except Exception:
            raise AuthError("Garmin authentication expired")

        # Fix
        fixed = get_fixer().fix_file(path)
        if fixed is None:
            raise RuntimeError(f"FIT fixer returned None for {path.name}")

        # Upload
        auth.upload_fit_file(fixed)


class AuthError(Exception):
    """Raised when Garmin authentication is required."""
