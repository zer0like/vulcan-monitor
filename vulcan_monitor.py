#!/usr/bin/env python3
"""
iGame Vulcan LCD Monitor (RTX 3080 Ti)
Author: zer0like
License: MIT
Description: High-performance native telemetry dashboard for Colorful iGame Vulcan GPUs.
"""
import serial
import time
import sys
import os
import signal
from collections import deque

# --- CONFIGURATION SETTINGS ---
PORT = '/dev/ttyACM0'
BAUD = 115200
UPDATE_INTERVAL = 1    # Seconds between each telemetry update
ROTATION_INTERVAL = 10   # How many updates to stay on one widget before switching
# ------------------------------

# Native Command IDs for Vulcan X (LCD3 Protocol)
WIDGET_GPU_FREQ = 0x44BB
WIDGET_GPU_LOAD = 0x55AA
WIDGET_GPU_FAN  = 0x7788
CMD_SET_MONITOR_RECORD = 0xED12 
CMD_SET_OP = 0xEB14

# Constants for scaling
GPU_FREQ_MAX = 2500
FAN_SPEED_MAX = 100

try:
    import pynvml
except ImportError:
    print("[!] Error: pynvml not installed. Please run 'pip install nvidia-ml-py'")
    sys.exit(1)

class VulcanMonitor:
    def __init__(self):
        self.ser = None
        self.running = True
        self.handle = None
        self.current_widget = WIDGET_GPU_FREQ
        
        # History buffers (110 points each) for native scrolling graphs
        self.histories = {
            WIDGET_GPU_FREQ: deque([0]*110, maxlen=110),
            WIDGET_GPU_LOAD: deque([0]*110, maxlen=110),
            WIDGET_GPU_FAN:  deque([0]*110, maxlen=110)
        }
        
    def signal_handler(self, sig, frame):
        """Handle system termination signals."""
        self.running = False

    def connect_nvml(self):
        """Initialize NVIDIA Management Library."""
        try:
            pynvml.nvmlInit()
            self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            return True
        except Exception as e:
            print(f"[!] NVML Initialization Error: {e}")
            return False

    def build_packet_raw(self, full_payload):
        """Wrap payload with LCD3 header and checksum."""
        data_len = len(full_payload) + 2
        packet = bytearray([0xF6, 0x5A, 0xA9, (data_len >> 8) & 0xFF, data_len & 0xFF])
        packet.extend(full_payload)
        checksum = sum(packet) & 0xFFFF
        packet.append((checksum >> 8) & 0xFF)
        packet.append(checksum & 0xFF)
        return bytes(packet)

    def build_widget_update(self, widget_id, value, max_val=None):
        """Prepare widget header and data payload (1 or 4 bytes)."""
        header = bytearray([
            (widget_id >> 8) & 0xFF, 
            widget_id & 0xFF, 
            0x00, # Horizontal
            0x00, 0xFF, 0xFF # Cyan color
        ])
        
        if max_val is None:
            data = bytearray([value & 0xFF])
        else:
            data = bytearray([
                (value >> 8) & 0xFF, 
                value & 0xFF, 
                (max_val >> 8) & 0xFF, 
                max_val & 0xFF
            ])
        
        return self.build_packet_raw(header + data)

    def connect_serial(self):
        """Establish serial connection and perform handshake."""
        try:
            self.ser = serial.Serial(PORT, BAUD, timeout=0.1)
            self.ser.dtr = True
            self.ser.rts = True
            time.sleep(0.1)
            self.ser.write(self.build_packet_raw(b'\xEB\x14\x01'))
            return True
        except Exception as e:
            print(f"[!] Serial Communication Error: {e}")
            return False

    def run(self):
        """Main monitoring loop."""
        if not self.connect_nvml():
            return
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        count = 0
        while self.running:
            if self.ser is None or not self.ser.is_open:
                if not self.connect_serial():
                    time.sleep(5)
                    continue

            try:
                # 1. Fetch live telemetry
                freq = pynvml.nvmlDeviceGetClockInfo(self.handle, pynvml.NVML_CLOCK_GRAPHICS)
                util = pynvml.nvmlDeviceGetUtilizationRates(self.handle).gpu
                try:
                    fan_pct = pynvml.nvmlDeviceGetFanSpeed(self.handle)
                except:
                    fan_pct = 0
                
                # 2. Update graph histories
                self.histories[WIDGET_GPU_FREQ].append(int(min(100, (freq / GPU_FREQ_MAX) * 100)))
                self.histories[WIDGET_GPU_LOAD].append(util)
                self.histories[WIDGET_GPU_FAN].append(fan_pct)
                
                # 3. Push Current Widget Stats
                if self.current_widget == WIDGET_GPU_FREQ:
                    p = self.build_widget_update(WIDGET_GPU_FREQ, freq, GPU_FREQ_MAX)
                elif self.current_widget == WIDGET_GPU_FAN:
                    p = self.build_widget_update(WIDGET_GPU_FAN, fan_pct, FAN_SPEED_MAX)
                else: # GPU Load
                    p = self.build_widget_update(WIDGET_GPU_LOAD, util)
                
                self.ser.write(p)
                time.sleep(0.05)
                
                # 4. Push 110-byte history for the Graph
                h_data = bytearray([0xED, 0x12]) + bytes(list(self.histories[self.current_widget]))
                self.ser.write(self.build_packet_raw(h_data))
                
                # Auto-rotation logic
                count += 1
                if count >= ROTATION_INTERVAL:
                    self.current_widget = {
                        WIDGET_GPU_FREQ: WIDGET_GPU_LOAD, 
                        WIDGET_GPU_LOAD: WIDGET_GPU_FAN, 
                        WIDGET_GPU_FAN:  WIDGET_GPU_FREQ
                    }[self.current_widget]
                    count = 0
                
                time.sleep(UPDATE_INTERVAL)
                
            except Exception as e:
                print(f"[!] Loop Runtime Error: {e}")
                self.ser = None

        pynvml.nvmlShutdown()
        if self.ser:
            self.ser.close()

if __name__ == "__main__":
    monitor = VulcanMonitor()
    monitor.run()
