#!/usr/bin/env python3
"""
iGame Vulcan LCD Monitor (RTX 3080 Ti) - Cache Optimized Version
Author: zer0like
License: MIT
Description: Ultra-low CPU usage native telemetry dashboard.
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
UPDATE_INTERVAL = 1.2    # Balanced interval for smooth graphs and low CPU
ROTATION_INTERVAL = 10   # Number of updates per widget
FAN_MAX_RPM = 3000       
# ------------------------------

# Native Command IDs for Vulcan X (LCD3 Protocol)
WIDGET_GPU_FREQ = 0x44BB
WIDGET_GPU_LOAD = 0x55AA
WIDGET_GPU_FAN  = 0x7788
CMD_SET_MONITOR_RECORD = 0xED12 
CMD_SET_OP = 0xEB14
CMD_SET_ID = 0xEC13

# Constants for scaling
GPU_FREQ_MAX = 2500

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
        
        # Caching layer to eliminate CPU recalculations
        self.last_val = -1
        self.last_widget = -1
        self.cached_widget_packet = b''
        
        # Fast arrays for history
        self.histories = {
            WIDGET_GPU_FREQ: deque([0]*110, maxlen=110),
            WIDGET_GPU_LOAD: deque([0]*110, maxlen=110),
            WIDGET_GPU_FAN:  deque([0]*110, maxlen=110)
        }
        
    def signal_handler(self, sig, frame):
        self.running = False

    def connect_nvml(self):
        try:
            pynvml.nvmlInit()
            self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            return True
        except:
            return False

    def build_packet_raw(self, full_payload):
        """Build full binary packet with header and checksum."""
        data_len = len(full_payload) + 2
        packet = bytearray([0xF6, 0x5A, 0xA9, (data_len >> 8) & 0xFF, data_len & 0xFF])
        packet.extend(full_payload)
        checksum = sum(packet) & 0xFFFF
        packet.append((checksum >> 8) & 0xFF)
        packet.append(checksum & 0xFF)
        return bytes(packet)

    def build_widget_update(self, widget_id, value, max_val=None):
        header = bytearray([
            (widget_id >> 8) & 0xFF, (widget_id & 0xFF), 
            0x00, 0x00, 0xFF, 0xFF
        ])
        if max_val is None:
            data = bytearray([value & 0xFF])
        else:
            data = bytearray([
                (value >> 8) & 0xFF, value & 0xFF, 
                (max_val >> 8) & 0xFF, max_val & 0xFF
            ])
        return self.build_packet_raw(header + data)

    def connect_serial(self):
        try:
            self.ser = serial.Serial(PORT, BAUD, timeout=0.1)
            self.ser.dtr = True
            self.ser.rts = True
            time.sleep(0.1)
            # Init sequence
            self.ser.write(self.build_packet_raw(b'\xEB\x14\x01'))
            self.ser.write(self.build_packet_raw(b'\xEC\x13\x01'))
            return True
        except:
            return False

    def run(self):
        if not self.connect_nvml(): return
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        count = 0
        while self.running:
            if self.ser is None or not self.ser.is_open:
                if not self.connect_serial():
                    time.sleep(5)
                    continue
            try:
                # 1. Fetch fast NVML stats
                freq = pynvml.nvmlDeviceGetClockInfo(self.handle, pynvml.NVML_CLOCK_GRAPHICS)
                util = pynvml.nvmlDeviceGetUtilizationRates(self.handle).gpu
                try:
                    fan_pct = pynvml.nvmlDeviceGetFanSpeed(self.handle)
                except:
                    fan_pct = 0
                
                # Update history buffers
                self.histories[WIDGET_GPU_FREQ].append(int(min(100, (freq/GPU_FREQ_MAX)*100)))
                self.histories[WIDGET_GPU_LOAD].append(util)
                self.histories[WIDGET_GPU_FAN].append(fan_pct)
                
                # 2. Determine widget values
                cur_val = 0
                max_v = None
                if self.current_widget == WIDGET_GPU_FREQ:
                    cur_val = freq
                    max_v = GPU_FREQ_MAX
                elif self.current_widget == WIDGET_GPU_FAN:
                    cur_val = int((fan_pct / 100.0) * FAN_MAX_RPM)
                    max_v = FAN_MAX_RPM
                else:
                    cur_val = util

                # 3. Cache Optimization: Only rebuild widget packet if data changed
                if cur_val != self.last_val or self.current_widget != self.last_widget:
                    self.cached_widget_packet = self.build_widget_update(self.current_widget, cur_val, max_v)
                    self.last_val = cur_val
                    self.last_widget = self.current_widget
                
                # LCD requires continuous packets to avoid freezing animations
                self.ser.write(self.cached_widget_packet)
                time.sleep(0.05) # Small delay to separate packets on hardware level
                
                # 4. History (Graph) update
                # Since deque changes every tick, we build the byte array directly
                h_data = bytearray([0xED, 0x12]) + bytes(self.histories[self.current_widget])
                self.ser.write(self.build_packet_raw(h_data))
                
                count += 1
                if count >= ROTATION_INTERVAL:
                    self.current_widget = {WIDGET_GPU_FREQ: WIDGET_GPU_LOAD, WIDGET_GPU_LOAD: WIDGET_GPU_FAN, WIDGET_GPU_FAN: WIDGET_GPU_FREQ}[self.current_widget]
                    count = 0
                
                time.sleep(UPDATE_INTERVAL)
            except Exception:
                self.ser = None

        pynvml.nvmlShutdown()
        if self.ser: self.ser.close()

if __name__ == "__main__":
    monitor = VulcanMonitor()
    monitor.run()
