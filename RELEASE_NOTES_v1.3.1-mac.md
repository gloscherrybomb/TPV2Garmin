# TPV2Garmin 1.3.1-mac

Patch release fixing `ModuleNotFoundError: No module named 'fit_tool'` in the built macOS app.

## What's New in 1.3.1-mac

### Bug Fix
- **Fix PyInstaller build:** Resolved `ModuleNotFoundError: No module named 'fit_tool'` when processing FIT files. The fixer now correctly imports from `fit_file_faker.vendor.fit_tool` instead of the standalone `fit_tool` package, matching what is bundled in the app.

---

## Downloads

| Asset | Description |
|-------|-------------|
| **TPV2Garmin.app** | macOS application bundle — double-click to run |
| **TPV2Garmin-1.3.1-mac.zip** | Source code (zip) |
| **TPV2Garmin-1.3.1-mac.tar.gz** | Source code (tarball) |

---

## Building

```bash
pyinstaller build/tpv2garmin_mac.spec
```

The `.app` bundle will be in `dist/TPV2Garmin.app`.
