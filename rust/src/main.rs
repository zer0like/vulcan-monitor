use nvml_wrapper::Nvml;
use nvml_wrapper::enum_wrappers::device::Clock;
use serialport::SerialPort;
use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

// Configuration
const PORT: &str = "/dev/ttyACM0";
const BAUD: u32 = 115200;
const UPDATE_INTERVAL_MS: u64 = 1200;
const ROTATION_INTERVAL: u32 = 10;
const FAN_MAX_RPM: u32 = 3000;
const GPU_FREQ_MAX: u32 = 2500;

// Command IDs
const WIDGET_GPU_FREQ: u16 = 0x44BB;
const WIDGET_GPU_LOAD: u16 = 0x55AA;
const WIDGET_GPU_FAN: u16 = 0x7788;

fn build_packet_raw(payload: &[u8]) -> Vec<u8> {
    let data_len = payload.len() + 2;
    let mut packet = Vec::with_capacity(5 + payload.len() + 2);
    packet.push(0xF6);
    packet.push(0x5A);
    packet.push(0xA9);
    packet.push((data_len >> 8) as u8);
    packet.push((data_len & 0xFF) as u8);
    packet.extend_from_slice(payload);

    let checksum: u32 = packet.iter().map(|&b| b as u32).sum();
    let cs16 = (checksum & 0xFFFF) as u16;
    packet.push((cs16 >> 8) as u8);
    packet.push((cs16 & 0xFF) as u8);
    packet
}

fn build_widget_update(widget_id: u16, value: u32, max_val: Option<u32>) -> Vec<u8> {
    let mut header = vec![
        (widget_id >> 8) as u8,
        (widget_id & 0xFF) as u8,
        0x00, 0x00, 0xFF, 0xFF,
    ];
    if let Some(mv) = max_val {
        header.push((value >> 8) as u8);
        header.push((value & 0xFF) as u8);
        header.push((mv >> 8) as u8);
        header.push((mv & 0xFF) as u8);
    } else {
        header.push((value & 0xFF) as u8);
    }
    build_packet_raw(&header)
}

struct Histories {
    freq: VecDeque<u8>,
    load: VecDeque<u8>,
    fan: VecDeque<u8>,
}

impl Histories {
    fn new() -> Self {
        Self {
            freq: vec![0; 110].into(),
            load: vec![0; 110].into(),
            fan: vec![0; 110].into(),
        }
    }

    fn append(&mut self, f: u8, l: u8, fa: u8) {
        self.freq.pop_front();
        self.freq.push_back(f);
        self.load.pop_front();
        self.load.push_back(l);
        self.fan.pop_front();
        self.fan.push_back(fa);
    }

    fn get_bytes(&self, widget: u16) -> Vec<u8> {
        let mut buf = Vec::with_capacity(112);
        buf.push(0xED);
        buf.push(0x12);
        let q = match widget {
            WIDGET_GPU_FREQ => &self.freq,
            WIDGET_GPU_FAN => &self.fan,
            _ => &self.load,
        };
        let (slice1, slice2) = q.as_slices();
        buf.extend_from_slice(slice1);
        buf.extend_from_slice(slice2);
        buf
    }
}

fn connect_serial() -> Option<Box<dyn SerialPort>> {
    match serialport::new(PORT, BAUD)
        .timeout(Duration::from_millis(100))
        .open()
    {
        Ok(mut port) => {
            let _ = port.write_data_terminal_ready(true);
            let _ = port.write_request_to_send(true);
            thread::sleep(Duration::from_millis(100));

            // Init sequence (SetOP + SetID)
            let _ = port.write_all(&build_packet_raw(&[0xEB, 0x14, 0x01]));
            let _ = port.write_all(&build_packet_raw(&[0xEC, 0x13, 0x01]));
            Some(port)
        }
        Err(_) => None,
    }
}

fn main() {
    println!("[*] Starting Vulcan Monitor (Rust Edition)...");

    let running = Arc::new(AtomicBool::new(true));
    let r = running.clone();
    ctrlc::set_handler(move || {
        r.store(false, Ordering::SeqCst);
    })
    .expect("Error setting Ctrl-C handler");

    let nvml = match Nvml::init() {
        Ok(n) => n,
        Err(e) => {
            eprintln!("[!] NVML Init Error: {:?}", e);
            std::process::exit(1);
        }
    };

    let mut histories = Histories::new();
    let mut current_widget = WIDGET_GPU_FREQ;
    let mut last_val: i64 = -1;
    let mut last_widget = 0;
    let mut cached_packet = Vec::new();
    let mut count = 0;
    
    let mut ser_port = connect_serial();

    while running.load(Ordering::SeqCst) {
        if ser_port.is_none() {
            ser_port = connect_serial();
            if ser_port.is_none() {
                thread::sleep(Duration::from_secs(5));
                continue;
            }
        }

        let device = match nvml.device_by_index(0) {
            Ok(d) => d,
            Err(_) => {
                thread::sleep(Duration::from_secs(1));
                continue;
            }
        };

        // Fetch telemetry
        let freq_raw = device.clock_info(Clock::Graphics).unwrap_or(0);
        let util = device.utilization_rates().map(|u| u.gpu).unwrap_or(0);
        let fan_pct = device.fan_speed(0).unwrap_or(0);

        // Normalize
        let freq_pct = std::cmp::min(100, (freq_raw * 100) / GPU_FREQ_MAX) as u8;
        let load_pct = std::cmp::min(100, util) as u8;
        let fan_pct_u8 = std::cmp::min(100, fan_pct) as u8;
        
        histories.append(freq_pct, load_pct, fan_pct_u8);

        let (cur_val, max_val) = match current_widget {
            WIDGET_GPU_FREQ => (freq_raw as u32, Some(GPU_FREQ_MAX)),
            WIDGET_GPU_FAN => {
                let rpm = ((fan_pct as f32 / 100.0) * FAN_MAX_RPM as f32) as u32;
                (rpm, Some(FAN_MAX_RPM))
            }
            _ => (util as u32, None),
        };

        // Cache hit or miss
        if cur_val as i64 != last_val || current_widget != last_widget {
            cached_packet = build_widget_update(current_widget, cur_val, max_val);
            last_val = cur_val as i64;
            last_widget = current_widget;
        }

        if let Some(ref mut port) = ser_port {
            if port.write_all(&cached_packet).is_err() {
                ser_port = None;
                continue;
            }
            thread::sleep(Duration::from_millis(50));
            
            let h_data = histories.get_bytes(current_widget);
            if port.write_all(&build_packet_raw(&h_data)).is_err() {
                ser_port = None;
                continue;
            }
        }

        count += 1;
        if count >= ROTATION_INTERVAL {
            current_widget = match current_widget {
                WIDGET_GPU_FREQ => WIDGET_GPU_LOAD,
                WIDGET_GPU_LOAD => WIDGET_GPU_FAN,
                _ => WIDGET_GPU_FREQ,
            };
            count = 0;
        }

        thread::sleep(Duration::from_millis(UPDATE_INTERVAL_MS));
    }
}
