# iGame Vulcan LCD Monitor (RTX 3080 Ti)

A native Rust controller for the integrated LCD screen on Colorful iGame Vulcan RTX 3080 Ti graphics cards. This tool bypasses the proprietary iGameCenter software and uses the native high-performance telemetry protocol to display real-time GPU statistics.

## Features
- **Zero Overhead**: Written in pure Rust. Consumes < 2MB of RAM and effectively 0% CPU in the background thanks to packet caching.
- **Flicker-Free**: Uses the native `0xED12` telemetry protocol.
- **Native UI**: Restores official iGame dashboards (Frequency, Usage, Fans) in real-time.
- **Linux Native**: Designed for Fedora and other Linux distributions.

## Requirements
- Rust toolchain (`cargo`)
- System libraries: `libudev-devel` (for serialport communication)
- GPU Driver: NVIDIA proprietary driver (for NVML)

## Installation (Rust Edition)

1. Install system dependencies (Fedora example):
   ```bash
   sudo dnf install rust cargo libudev-devel
   ```

2. Build the optimized release binary:
   ```bash
   cd rust
   cargo build --release
   ```

3. Install the binary and systemd service:
   ```bash
   sudo cp target/release/vulcan-monitor-rs /opt/vulcan-monitor/
   sudo cp vulcan-lcd-rs.service /etc/systemd/system/vulcan-lcd.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now vulcan-lcd
   ```

---

## Legacy Python Version
If you prefer not to compile Rust code, a Python fallback is available in the `python/` directory.

### Requirements
- `pyserial`, `nvidia-ml-py`

### Installation
```bash
pip install pyserial nvidia-ml-py
cd python
sudo cp vulcan_monitor.py /opt/vulcan-monitor/
sudo cp vulcan-lcd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vulcan-lcd
```

## License
MIT
