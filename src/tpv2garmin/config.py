"""Configuration management for TPV2Garmin."""

import json
import logging
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path

import appdirs

from fit_file_faker.config import (
    AppType,
    GarminDeviceInfo,
    Profile,
    SUPPLEMENTAL_GARMIN_DEVICES,
)

logger = logging.getLogger(__name__)

# ── Path constants ──────────────────────────────────────────────────────────
APP_DIR = Path(appdirs.user_data_dir("TPV2Garmin", appauthor=False))
CONFIG_FILE = APP_DIR / "config.json"
PROCESSED_LOG = APP_DIR / "processed.log"
PROCESSED_DIR = APP_DIR / "processed"
LOG_FILE = APP_DIR / "app.log"
GARTH_TOKENS_DIR = APP_DIR / "garth_tokens"

# ── Default device ──────────────────────────────────────────────────────────
DEFAULT_DEVICE_PRODUCT = 4440  # Edge 1050
DEFAULT_DEVICE_NAME = "Edge 1050"
DEFAULT_MANUFACTURER = 1  # Garmin


def _generate_serial_number() -> int:
    """Generate a random serial number valid for FIT spec (uint32z)."""
    return random.randint(1_000_000_000, 4_294_967_295)


# ── AppConfig ───────────────────────────────────────────────────────────────
@dataclass
class AppConfig:
    """Application configuration persisted to config.json."""

    fitfiles_path: str = ""
    device_product: int = DEFAULT_DEVICE_PRODUCT
    device_name: str = DEFAULT_DEVICE_NAME
    manufacturer: int = DEFAULT_MANUFACTURER
    serial_number: int = field(default_factory=_generate_serial_number)
    software_version: int | None = None
    run_mode: str = "watch"  # "watch" or "tpv_linked"
    auto_start: bool = False
    notifications_enabled: bool = True
    garmin_username: str = ""
    setup_complete: bool = False


# ── ConfigManager ───────────────────────────────────────────────────────────
class ConfigManager:
    """Load/save AppConfig to config.json in the platform user data directory.

    Typical paths:
    - Windows: %APPDATA%\\TPV2Garmin\\
    - macOS: ~/Library/Application Support/TPV2Garmin/
    """

    def __init__(self) -> None:
        self._ensure_dirs()
        self.config = self._load()

    def _ensure_dirs(self) -> None:
        for d in (APP_DIR, PROCESSED_DIR, GARTH_TOKENS_DIR):
            d.mkdir(parents=True, exist_ok=True)

    def _load(self) -> AppConfig:
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                return AppConfig(**{
                    k: v for k, v in data.items()
                    if k in AppConfig.__dataclass_fields__
                })
            except Exception:
                logger.exception("Failed to load config, using defaults")
        return AppConfig()

    def save(self) -> None:
        CONFIG_FILE.write_text(
            json.dumps(asdict(self.config), indent=2),
            encoding="utf-8",
        )
        logger.info("Config saved to %s", CONFIG_FILE)

    def reset(self) -> None:
        self.config = AppConfig()
        self.save()


# ── Device list helper ──────────────────────────────────────────────────────
def get_device_list() -> list[GarminDeviceInfo]:
    """Return FFF's curated list of Garmin devices."""
    return list(SUPPLEMENTAL_GARMIN_DEVICES)


def get_device_choices() -> list[tuple[str, int, str]]:
    """Return (display_name, product_id, category) tuples sorted for UI."""
    devices = get_device_list()
    devices.sort(key=lambda d: (not d.is_common, -d.year_released, d.name))
    return [(d.name, d.product_id, d.category) for d in devices]


# ── Profile bridge ──────────────────────────────────────────────────────────
def _lookup_software_version(product_id: int) -> int | None:
    """Look up software_version from the curated device list."""
    for device in SUPPLEMENTAL_GARMIN_DEVICES:
        if device.product_id == product_id:
            return device.software_version
    return None


def build_profile(config: AppConfig) -> Profile:
    """Create a FFF Profile from our AppConfig."""
    sw = config.software_version
    if sw is None:
        sw = _lookup_software_version(config.device_product)
    return Profile(
        name="tpv2garmin",
        app_type=AppType.TP_VIRTUAL,
        garmin_username=config.garmin_username,
        garmin_password="",  # not stored; auth handled via garth tokens
        fitfiles_path=Path(config.fitfiles_path) if config.fitfiles_path else Path("."),
        manufacturer=config.manufacturer,
        device=config.device_product,
        serial_number=config.serial_number,
        software_version=sw,
    )


# ── Lazy singleton ──────────────────────────────────────────────────────────
_config_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    """Get or create the singleton ConfigManager."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
