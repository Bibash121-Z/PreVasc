import collections
import threading
import numpy as np
import paho.mqtt.client as mqtt
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from paho.mqtt.enums import CallbackAPIVersion
from scipy.signal import butter, filtfilt, medfilt, find_peaks, savgol_filter

# --------------------------------------------------
# Configuration
# --------------------------------------------------
BROKER = "192.168.43.252"
PORT = 1883
TOPIC = "sensor/vascular"

FS = 200            # Matches ESP32 200Hz
BUFFER_SIZE = 1200  # 6 seconds of history
WINDOW_SECONDS = 4  # Time window shown on screen

# --------------------------------------------------
# Optimized PPG Processor with Wave Inversion
# --------------------------------------------------
class PPGProcessor:
    def __init__(self, fs=200):
        self.fs = fs
        nyquist = fs / 2
        self.b, self.a = butter(3, [0.5 / nyquist, 8.0 / nyquist], btype="bandpass")
        self.baseline = None
        self.alpha = 0.995
        self.previous_bpm = 0.0

    def process(self, raw_signal):
        sig = np.asarray(raw_signal, dtype=float)
        n = len(sig)
        
        if n < 200:
            return None

        # 1. Fast Baseline Drift Removal
        if self.baseline is None:
            self.baseline = sig[0]
        baseline = np.zeros_like(sig)
        current = self.baseline
        for i in range(n):
            current = (self.alpha * current + (1 - self.alpha) * sig[i])
            baseline[i] = current
        self.baseline = current
        ac_signal = sig - baseline

        # 2. Median Filter
        filtered = medfilt(ac_signal, kernel_size=5)

        # 3. Fast Zero-phase Butterworth Bandpass
        filtered = filtfilt(self.b, self.a, filtered)

        # 4. Smooth out jitter
        filtered = savgol_filter(filtered, window_length=11, polyorder=3)

        # 5. --- INVERT THE SIGNAL ---
        # Multiplying by -1 flips it so blood volume pulse waves point UPWARD.
        filtered = -filtered

        # 6. Normalize for analysis
        max_val = np.max(np.abs(filtered))
        display_signal = filtered / max_val if max_val > 1e-6 else filtered

        # 7. Systolic Peak Detection (Now on the tall upward crests!)
        mean = np.mean(display_signal)
        std = np.std(display_signal)
        threshold = mean + 0.15 * std
        prominence = max(0.15 * (np.max(display_signal) - np.min(display_signal)), 0.02)
        min_distance = int(0.35 * self.fs)
        
        systolic_peaks, _ = find_peaks(
            display_signal,
            height=threshold,
            distance=min_distance,
            prominence=prominence
        )

        # 8. Diastolic Peak Detection (On the falling/dicrotic shoulder)
        diastolic_peaks = []
        for i in range(len(systolic_peaks)):
            p_start = systolic_peaks[i]
            p_end = systolic_peaks[i + 1] if i + 1 < len(systolic_peaks) else n
            segment = display_signal[p_start:p_end]
            m = len(segment)
            if m < 25:
                continue
            
            # Search the mid-descent region of the wave
            start_idx = int(0.20 * m)
            end_idx = int(0.75 * m)
            window = segment[start_idx:end_idx]
            
            if len(window) < 5:
                continue

            # Detect the inflection point on the downward slope
            dy = np.diff(window)
            d2y = np.diff(dy)
            
            # Find the peak of the second derivative (maximum rate of curvature change)
            if len(d2y) > 0:
                inflection_idx = np.argmax(d2y)
                diastolic_peaks.append(p_start + start_idx + inflection_idx)
            else:
                # Fallback to 45% of the downward slope
                diastolic_peaks.append(p_start + int(0.45 * m))

        # 9. Fast BPM estimation
        fft_m = np.abs(np.fft.rfft(display_signal))
        fft_f = np.fft.rfftfreq(n, d=1 / self.fs)
        mask = (fft_f >= 0.6) & (fft_f <= 2.8)
        
        bpm = 75.0
        if np.any(mask):
            dominant_idx = np.argmax(fft_m[mask])
            dominant_freq = fft_f[mask][dominant_idx]
            calculated_bpm = dominant_freq * 60
            if self.previous_bpm == 0:
                self.previous_bpm = calculated_bpm
            else:
                self.previous_bpm = 0.9 * self.previous_bpm + 0.1 * calculated_bpm
            bpm = self.previous_bpm

        return {
            "display": display_signal,
            "systolic": systolic_peaks,
            "diastolic": np.array(diastolic_peaks, dtype=int),
            "bpm": bpm
        }

# --------------------------------------------------
# Thread-Safe Storage & MQTT Client
# --------------------------------------------------
raw_ir_buffer = collections.deque(maxlen=BUFFER_SIZE)
data_lock = threading.Lock()
processor = PPGProcessor(fs=FS)

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print("🟢 Connected to local broker. Real-time inverted pipeline running...")
        client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode('utf-8').strip()
        if "," in payload_str:
            _, ir_val_str = payload_str.split(",")
            ir_val = float(ir_val_str.strip())
            
            with data_lock:
                raw_ir_buffer.append(ir_val)
    except:
        pass

def run_mqtt():
    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.loop_forever()

# --------------------------------------------------
# Blitted Minimalist Animation Loop
# --------------------------------------------------
def update_plot(frame, raw_line, filtered_line, systolic_points, diastolic_points, stats_text, ax_raw, ax_filt):
    with data_lock:
        signal_copy = list(raw_ir_buffer)

    if len(signal_copy) < (FS * 2):
        return raw_line, filtered_line, systolic_points, diastolic_points, stats_text

    raw_signal = np.array(signal_copy)
    x = np.arange(len(raw_signal)) / FS
    last_x = x[-1]

    # --- 1. Update Raw Axis Line ---
    raw_line.set_data(x, raw_signal)
    ax_raw.set_xlim(last_x - WINDOW_SECONDS, last_x)
    
    recent_raw = raw_signal[-int(FS * WINDOW_SECONDS):]
    ymin, ymax = np.min(recent_raw), np.max(recent_raw)
    margin = max((ymax - ymin) * 0.1, 50)
    ax_raw.set_ylim(ymin - margin, ymax + margin)

    # --- 2. Run Pipeline & Update Filtered Line ---
    results = processor.process(signal_copy)
    if results is not None:
        filtered = results["display"]
        systolic = results["systolic"]
        diastolic = results["diastolic"]
        bpm = results["bpm"]

        filtered_line.set_data(x, filtered)
        ax_filt.set_xlim(last_x - WINDOW_SECONDS, last_x)

        # Plot Systolic (On the new upright peaks)
        if len(systolic):
            systolic_points.set_data(x[systolic], filtered[systolic])
        else:
            systolic_points.set_data([], [])

        # Plot Diastolic (On the dicrotic notch falling slope)
        if len(diastolic):
            diastolic_points.set_data(x[diastolic], filtered[diastolic])
        else:
            diastolic_points.set_data([], [])

        stats_text.set_text(f"HR: {bpm:5.1f} BPM")

    return raw_line, filtered_line, systolic_points, diastolic_points, stats_text

# --------------------------------------------------
# Main UI Setup
# --------------------------------------------------
def main():
    mqtt_thread = threading.Thread(target=run_mqtt, daemon=True)
    mqtt_thread.start()

    plt.style.use("dark_background")
    fig, (ax_raw, ax_filt) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    fig.canvas.manager.set_window_title("Clean Real-Time PPG Dual-Peak Analyzer")

    for ax in [ax_raw, ax_filt]:
        ax.set_axis_off()
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)
        ax.grid(False)

    raw_line, = ax_raw.plot([], [], color="#ff4d4d", linewidth=1.5, label="Raw")
    filtered_line, = ax_filt.plot([], [], color="#00ffcc", linewidth=2.5, label="Filtered")
    
    # Updated: Systolic is Pink, Diastolic is Neon Green
    systolic_points, = ax_filt.plot([], [], "o", color="#ff007f", markersize=8, label="Systole")
    diastolic_points, = ax_filt.plot([], [], "o", color="#39ff14", markersize=8, label="Diastole")

    stats_text = ax_filt.text(
        0.02, 0.90, "",
        transform=ax_filt.transAxes,
        fontsize=16,
        fontweight="bold",
        color="#00ffcc",
        verticalalignment="top",
    )

    ax_filt.set_ylim(-1.1, 1.1)

    ani = animation.FuncAnimation(
        fig,
        update_plot,
        fargs=(raw_line, filtered_line, systolic_points, diastolic_points, stats_text, ax_raw, ax_filt),
        interval=33, 
        blit=True, 
        cache_frame_data=False
    )

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()