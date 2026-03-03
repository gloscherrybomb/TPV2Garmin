# TPV2Garmin

Automatically upload [TrainingPeaks Virtual](https://www.trainingpeaks.com/virtual/) FIT files to Garmin Connect with device spoofing.

TPV2Garmin watches your TPV FIT folder, rewrites each file to appear as a real Garmin device (via [Fit-File-Faker](https://github.com/jat255/Fit-File-Faker)), and uploads it to Garmin Connect — all in the background.

I really like coffee, so if this enhances your life, please buy me one :)

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/jeastwood)

## Download

Grab the latest release from the [Releases](https://github.com/gloscherrybomb/TPV2Garmin/releases/latest) page: **TPV2Garmin.exe** (Windows) or **TPV2Garmin.app** (macOS).

## Features

- Watches your TPV FIT output folder for new activity files
- Rewrites device metadata so Garmin Connect accepts the file as a real device
- Uploads directly to Garmin Connect (supports MFA)
- Desktop notifications on success/error (toast on Windows, native on macOS)
- System tray (Windows) or menu bar (macOS) — runs quietly in the background
- TPV-linked mode: auto-starts watching when TrainingPeaks Virtual is running
- First-run setup wizard walks you through configuration

## Requirements

- **Windows:** Windows 10 or 11
- **macOS:** macOS 10.15 or later
- A Garmin Connect account
- TrainingPeaks Virtual installed

## Getting Started

1. Download the app for your platform from the [latest release](https://github.com/gloscherrybomb/TPV2Garmin/releases/latest):
   - Windows: `TPV2Garmin.exe`
   - macOS: `TPV2Garmin.app`
2. Run the app (double-click the .exe or .app)
3. The setup wizard will guide you through:
   - Selecting your TPV FIT files folder
   - Choosing a Garmin device to emulate
   - Signing in to Garmin Connect
4. Once configured, the app watches for new files and uploads them automatically

Configuration is stored in the platform user data directory: `%APPDATA%\TPV2Garmin\` (Windows) or `~/Library/Application Support/TPV2Garmin/` (macOS).

## Development Setup

Requires Python 3.12+.

```bash
pip install -e .
tpv2garmin
```

### Building

**Windows (.exe):**
```bash
pip install pyinstaller
pyinstaller build/tpv2garmin.spec
```
Output: `dist/TPV2Garmin.exe`

**macOS (.app):**
```bash
pip install pyinstaller
python build/create_icns.py   # Regenerate icon.icns from icon.png (if needed)
pyinstaller build/tpv2garmin_mac.spec
```
Output: `dist/TPV2Garmin.app`

## License

MIT
