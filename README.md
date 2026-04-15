# iGame Vulcan LCD Monitor (RTX 3080 Ti)

A lightweight Python controller for the integrated LCD screen on Colorful iGame Vulcan RTX 3080 Ti graphics cards. This tool bypasses the proprietary iGameCenter software and uses the native high-performance telemetry protocol.

## Features
- **Flicker-Free**: Uses the native `0xED12` telemetry protocol.
- **Native UI**: Restores official iGame dashboards (Frequency, Usage, Fans).
- **Lightweight**: Low CPU usage, runs as a background systemd service.
- **Linux Native**: Designed for Fedora and other Linux distributions.

## Requirements
- Python 3.x
- `pyserial`
- `nvidia-ml-py` (pynvml)

## Installation
1. Install dependencies:
   ```bash
   pip install pyserial nvidia-ml-py
   ```
2. Copy the service file to systemd:
   ```bash
   sudo cp vulcan-lcd.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now vulcan-lcd
   ```

## License
MIT
