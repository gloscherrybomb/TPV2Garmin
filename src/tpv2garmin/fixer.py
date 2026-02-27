"""FIT file fixer module for TPV2Garmin.

Wraps Fit-File-Faker to modify FIT files exported by TrainerRoad /
TP Virtual so they appear as native Garmin device recordings.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from tpv2garmin.config import build_profile, get_config_manager, PROCESSED_DIR, PROCESSED_LOG

logger = logging.getLogger(__name__)

# ── One-time FIT SDK patch ───────────────────────────────────────────────────
_patch_applied: bool = False


def ensure_patch() -> None:
    """Apply the FIT SDK tool patch exactly once per process."""
    global _patch_applied
    if _patch_applied:
        return
    from fit_file_faker.utils import apply_fit_tool_patch

    apply_fit_tool_patch()
    _patch_applied = True
    logger.debug("FIT tool patch applied")


# ── FitFixer ─────────────────────────────────────────────────────────────────
class FitFixer:
    """High-level helper that copies a FIT file, fixes it, and returns the
    path to the fixed output."""

    def fix_file(self, original_path: Path) -> Path | None:
        """Fix a single FIT file.

        Parameters
        ----------
        original_path:
            Path to the original ``.fit`` file on disk.

        Returns
        -------
        Path | None
            Path to the fixed file inside *PROCESSED_DIR*, or ``None`` if
            the operation failed.
        """
        try:
            ensure_patch()

            # Ensure the processed directory exists.
            PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

            # Copy original into the processed folder.
            copy_path = PROCESSED_DIR / original_path.name
            shutil.copy2(original_path, copy_path)
            logger.info("Copied %s -> %s", original_path, copy_path)

            # Build the fixed output path.
            stem = original_path.stem
            suffix = original_path.suffix
            fixed_path = PROCESSED_DIR / f"{stem}_fixed{suffix}"

            # Build a FFF profile from the current application config.
            config = get_config_manager().config
            profile = build_profile(config)

            # Run the editor.
            from fit_file_faker.fit_editor import FitEditor

            editor = FitEditor(profile=profile)
            result = editor.edit_fit(fit_input=copy_path, output=fixed_path, dryrun=False)

            if result is None:
                logger.error("FitEditor returned None for %s", original_path.name)
                return None

            logger.info("Fixed file written to %s", fixed_path)
            return fixed_path

        except Exception:
            logger.exception("Failed to fix %s", original_path)
            return None


# ── Standalone helpers ───────────────────────────────────────────────────────

def _is_readable_fit(path: Path) -> bool:
    """Return ``True`` when *path* can be parsed as a FIT file."""
    try:
        ensure_patch()
        from fit_tool.fit_file import FitFile

        fit_file = FitFile.from_file(str(path))
        return len(fit_file.records) > 0
    except Exception:
        logger.debug("FIT not readable yet: %s", path.name, exc_info=True)
        return False


def wait_for_write_complete(path: Path, timeout: float = 10.0) -> bool:
    """Poll *path* until size is stable and the file parses as FIT.

    This is useful when watching a directory for newly created FIT files;
    the producing application may still be writing data when we first
    detect the file.

    Parameters
    ----------
    path:
        File to monitor.
    timeout:
        Maximum wall-clock seconds to wait before giving up.

    Returns
    -------
    bool
        ``True`` if the file stabilised and became readable within *timeout*, ``False``
        otherwise.
    """
    poll_interval = 0.5  # seconds between size checks
    stable_threshold = 2.0  # seconds the size must remain unchanged

    deadline = time.monotonic() + timeout
    last_size: int | None = None
    stable_since: float | None = None

    while time.monotonic() < deadline:
        try:
            current_size = path.stat().st_size
        except OSError:
            # File may not exist yet; reset and retry.
            last_size = None
            stable_since = None
            time.sleep(poll_interval)
            continue

        now = time.monotonic()

        if last_size is None or current_size != last_size:
            last_size = current_size
            stable_since = now
        elif stable_since is not None and (now - stable_since) >= stable_threshold:
            if _is_readable_fit(path):
                logger.debug("File %s stable and readable at %d bytes", path.name, current_size)
                return True
            logger.debug("File %s is size-stable but not yet parseable; waiting", path.name)

        time.sleep(poll_interval)

    logger.warning("Timed out waiting for %s to finish writing", path)
    return False


def is_processed(filename: str) -> bool:
    """Return ``True`` if *filename* has already been recorded in the
    processed log."""
    if not PROCESSED_LOG.exists():
        return False
    try:
        entries = PROCESSED_LOG.read_text(encoding="utf-8").splitlines()
        return filename in entries
    except OSError:
        logger.exception("Unable to read processed log")
        return False


def mark_processed(filename: str) -> None:
    """Append *filename* to the processed log."""
    try:
        PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)
        with PROCESSED_LOG.open("a", encoding="utf-8") as fh:
            fh.write(filename + "\n")
        logger.debug("Marked %s as processed", filename)
    except OSError:
        logger.exception("Unable to write to processed log")


def get_unprocessed_files(folder: Path) -> list[Path]:
    """Return a sorted list of ``.fit`` files in *folder* that have not yet
    been recorded in the processed log.

    Parameters
    ----------
    folder:
        Directory to scan for FIT files.

    Returns
    -------
    list[Path]
        Unprocessed ``.fit`` files sorted by name.
    """
    if not folder.is_dir():
        logger.warning("Folder does not exist: %s", folder)
        return []

    fit_files = sorted(folder.glob("*.fit"))
    unprocessed = [f for f in fit_files if not is_processed(f.name)]

    logger.debug(
        "Found %d FIT file(s) in %s, %d unprocessed",
        len(fit_files),
        folder,
        len(unprocessed),
    )
    return unprocessed


def get_fit_distance(path: Path) -> float | None:
    """Return total distance (meters) from the FIT session, or None on failure."""
    try:
        ensure_patch()
        from fit_tool.fit_file import FitFile
        from fit_tool.profile.messages.session_message import SessionMessage

        fit_file = FitFile.from_file(str(path))
        for record in fit_file.records:
            msg = record.message
            if isinstance(msg, SessionMessage) and msg.total_distance is not None:
                return float(msg.total_distance)
    except Exception:
        logger.debug("Could not read distance from %s", path.name, exc_info=True)
    return None


# ── Lazy singleton ───────────────────────────────────────────────────────────
_fixer: FitFixer | None = None


def get_fixer() -> FitFixer:
    """Get or create the singleton :class:`FitFixer`."""
    global _fixer
    if _fixer is None:
        _fixer = FitFixer()
    return _fixer
