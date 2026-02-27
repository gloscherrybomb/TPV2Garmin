# TPV2Garmin

Automatically upload [TrainingPeaks Virtual](https://www.trainingpeaks.com/virtual/) FIT files to Garmin Connect with device spoofing.

TPV2Garmin watches your TPV FIT folder, rewrites each file to appear as a real Garmin device (via [Fit-File-Faker](https://github.com/gloscherrybomb/Fit-File-Faker)), and uploads it to Garmin Connect — all in the background.

I really like coffee, so if this enhances your life, please buy me one :)

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/jeastwood)

## Download

Grab the latest **TPV2Garmin.exe** from the [Releases](https://github.com/gloscherrybomb/TPV2Garmin/releases/latest) page.

Official releases are currently Windows-first.

## Features

- Watches your TPV FIT output folder for new activity files
- Rewrites device metadata so Garmin Connect accepts the file as a real device
- Uploads directly to Garmin Connect (supports MFA)
- Waits until each file is actually parseable as FIT before conversion/upload
- Skips short/non-activity recordings (`< 100 m`) to avoid bad uploads
- Windows toast notifications on success/error
- System tray integration — runs quietly in the background
- TPV-linked mode: auto-starts watching when TPVirtual.exe is running
- First-run setup wizard walks you through configuration

## Requirements

- Windows 10 or 11
- A Garmin Connect account
- TrainingPeaks Virtual installed

## Getting Started

1. Download `TPV2Garmin.exe` from the [latest release](https://github.com/gloscherrybomb/TPV2Garmin/releases/latest)
2. Run `TPV2Garmin.exe`
3. The setup wizard will guide you through:
   - Selecting your TPV FIT files folder
   - Choosing a Garmin device to emulate
   - Signing in to Garmin Connect
4. Once configured, the app watches for new files and uploads them automatically

Configuration is stored in `%APPDATA%/TPV2Garmin/`.

## Development Setup

Requires Python 3.12+.

```bash
pip install -e .
tpv2garmin
```

### Building the Windows `.exe`

```bash
pip install pyinstaller
pyinstaller build/tpv2garmin.spec
```

Output: `dist/TPV2Garmin.exe`

### Building a macOS app and `.dmg`

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name TPV2Garmin --paths src --add-data "src/tpv2garmin/assets:tpv2garmin/assets" src/tpv2garmin/app.py
hdiutil create -volname "TPV2Garmin" -srcfolder "dist/TPV2Garmin.app" -ov -format UDZO "dist/TPV2Garmin-macOS.dmg"
```

Outputs:
- `dist/TPV2Garmin.app`
- `dist/TPV2Garmin-macOS.dmg`

## License

MIT
