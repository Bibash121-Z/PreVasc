import json
import collections
import threading
import time
import numpy as np
import websocket  # pip install websocket-client
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# Filtering libraries
from scipy.signal import (
    butter,
    filtfilt,
    medfilt,
    find_peaks,
    savgol_filter
)

# --------------------------------------------------
# Configuration
# --------------------------------------------------
WS_URL = "ws://127.0.0.1:8000/ws/sensor_data/"
BUFFER_SIZE = 2000  # Max history of raw points to keep in memory (10s of data)
FS = 200            # Expected sampling rate (Hz) of MAX30102
WINDOW_SECONDS = 5  # Rolling plot time window

# --------------------------------------------------
# 1. Embedded PPG Processor Class[cite: 1]
# --------------------------------------------------
class PPGProcessor:
    def __init__(
        self,
        fs=200,
        lowcut=0.5,
        highcut=12.0,
        butter_order=3,
        median_kernel=5,
        moving_average_window=5
    ):
        self.fs = fs
        self.lowcut = lowcut
        self.highcut = highcut
        self.butter_order = butter_order
        self.median_kernel = median_kernel
        self.ma_window = moving_average_window

        nyquist = fs / 2
        low = lowcut / nyquist
        high = min(highcut / nyquist, 0.99)

        self.b, self.a = butter(
            butter_order,
            [low, high],
            btype="bandpass"
        )

        self.baseline = None
        self.alpha = 0.995
        self.previous_bpm = 0.0

    def remove_baseline(self, signal):
        signal = np.asarray(signal, dtype=float)
        if self.baseline is None:
            self.baseline = signal[0]
        baseline = np.zeros_like(signal)
        current = self.baseline
        for i, sample in enumerate(signal):
            current = (self.alpha * current + (1 - self.alpha) * sample)
            baseline[i] = current
        self.baseline = current
        return signal - baseline

    def median_filter(self, signal):
        return medfilt(signal, kernel_size=self.median_kernel)

    def butterworth_filter(self, signal):
        if len(signal) < 3 * max(len(self.a), len(self.b)):
            return signal
        return filtfilt(self.b, self.a, signal)

    def savgol_smooth(self, signal, window_length=7, polyorder=3):
        n = len(signal)
        wl = window_length
        if wl >= n:
            wl = n - 1 if (n - 1) % 2 == 1 else n - 2
        if wl <= polyorder:
            return signal
        if wl % 2 == 0:
            wl -= 1
        if wl < 5:
            return signal
        return savgol_filter(signal, window_length=wl, polyorder=polyorder)

    def normalize_display(self, signal):
        maximum = np.max(np.abs(signal))
        if maximum < 1e-8:
            return signal
        return signal / maximum

    def compute_fft(self, signal):
        signal = np.asarray(signal)
        n = len(signal)
        fft = np.fft.rfft(signal)
        magnitude = np.abs(fft)
        frequency = np.fft.rfftfreq(n, d=1 / self.fs)
        return frequency, magnitude

    def dominant_frequency(self, signal):
        frequency, magnitude = self.compute_fft(signal)
        mask = ((frequency >= 0.5) & (frequency <= 3.0))
        frequency = frequency[mask]
        magnitude = magnitude[mask]
        if len(frequency) == 0:
            return 0.0
        index = np.argmax(magnitude)
        return frequency[index]

    def estimate_bpm(self, signal):
        bpm = self.dominant_frequency(signal) * 60
        if self.previous_bpm == 0:
            self.previous_bpm = bpm
        else:
            self.previous_bpm = 0.85 * self.previous_bpm + 0.15 * bpm
        return self.previous_bpm

    def signal_statistics(self, signal):
        return {
            "mean": np.mean(signal),
            "rms": np.sqrt(np.mean(signal ** 2)),
            "std": np.std(signal),
            "max": np.max(signal),
            "min": np.min(signal),
            "energy": np.sum(signal ** 2)
        }

    def detect_systolic_peaks(self, signal):
        signal = np.asarray(signal)
        if len(signal) < self.fs * 2:
            return np.array([], dtype=int)
        mean = np.mean(signal)
        std = np.std(signal)
        threshold = mean + 0.35 * std
        prominence = max(0.10 * (np.max(signal) - np.min(signal)), 0.02)
        min_distance = int(0.33 * self.fs)

        peaks, _ = find_peaks(
            signal,
            height=threshold,
            distance=min_distance,
            prominence=prominence,
            width=2
        )

        valid = []
        for p in peaks:
            if p < 3 or p > len(signal) - 4:
                continue
            if signal[p] > signal[p - 1] and signal[p] > signal[p + 1]:
                valid.append(p)
        return np.array(valid, dtype=int)

    def detect_diastolic(self, signal, systolic_peaks):
        signal = np.asarray(signal, dtype=float)
        diastolic = []
        n = len(signal)
        for i in range(len(systolic_peaks)):
            p_start = systolic_peaks[i]
            p_end = systolic_peaks[i + 1] if i + 1 < len(systolic_peaks) else n
            segment = signal[p_start:p_end]
            m = len(segment)
            if m < 15:
                continue
            lo = max(int(0.06 * m), 2)
            window = segment[lo:]
            wlen = len(window)
            if wlen < 10:
                continue
            local_range = np.max(window) - np.min(window)
            if local_range < 1e-9:
                continue

            min_prominence = max(0.05 * local_range, 1e-6)
            min_distance = max(int(0.05 * self.fs), 2)
            minima, _ = find_peaks(-window, prominence=min_prominence, distance=min_distance)

            diastolic_idx = None
            margin = max(int(0.10 * wlen), 4)

            for cand in minima:
                remaining = window[cand:]
                if len(remaining) - margin < 5:
                    continue
                search_zone = remaining[: len(remaining) - margin]
                bump_prominence = max(0.08 * local_range, 1e-6)
                maxima, _ = find_peaks(search_zone, prominence=bump_prominence, distance=min_distance)
                if len(maxima) == 0:
                    continue
                rise = search_zone[maxima[0]] - window[cand]
                if rise < 0.10 * local_range:
                    continue
                diastolic_idx = cand + maxima[0]
                break

            if diastolic_idx is not None:
                diastolic.append(p_start + lo + diastolic_idx)
        return np.array(diastolic, dtype=int)

    def preprocess_signal(self, signal):
        signal = np.asarray(signal, dtype=float)
        if len(signal) < 400:
            return {
                "raw": signal,
                "baseline_removed": signal,
                "filtered": signal,
                "display": signal,
                "light_display": signal,
                "frequency": 0.0,
                "bpm": 0.0,
                "statistics": {"mean": 0, "std": 0, "rms": 0},
                "systolic_peaks": np.array([], dtype=int),
                "diastolic_peaks": np.array([], dtype=int)
            }

        baseline_removed = self.remove_baseline(signal)
        median = self.median_filter(baseline_removed)
        light_display = self.normalize_display(median)
        filtered = self.butterworth_filter(median)
        filtered = self.savgol_smooth(filtered, window_length=11, polyorder=3)

        frequency = self.dominant_frequency(filtered)
        bpm = self.estimate_bpm(filtered)
        statistics = self.signal_statistics(filtered)
        systolic_peaks = self.detect_systolic_peaks(filtered)
        diastolic_peaks = self.detect_diastolic(filtered, systolic_peaks)
        display = self.normalize_display(filtered)

        return {
            "raw": signal,
            "baseline_removed": baseline_removed,
            "filtered": filtered,
            "display": display,
            "light_display": light_display,
            "frequency": frequency,
            "bpm": bpm,
            "statistics": statistics,
            "systolic_peaks": systolic_peaks,
            "diastolic_peaks": diastolic_peaks
        }

# --------------------------------------------------
# 2. Thread-Safe Global Data Buffers
# --------------------------------------------------
raw_ir_buffer = collections.deque(maxlen=BUFFER_SIZE)
data_lock = threading.Lock()
processor = PPGProcessor(fs=FS)
last_print = 0

# --------------------------------------------------
# 3. WebSocket Connection Callback Handlers
# --------------------------------------------------
def on_message(ws, message):
    try:
        data = json.loads(message)
        ir_values = data.get("ir", [])
        
        with data_lock:
            # Append new batch items directly to our rolling raw buffer
            for ir in ir_values:
                raw_ir_buffer.append(ir)
                
    except Exception as e:
        print(f"🔴 WebSocket Decoding Error: {e}")

def on_error(ws, error):
    print(f"🔴 WebSocket Connection Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("🔌 Local Django WebSocket Connection Closed.")

def on_open(ws):
    print("🟢 Connected to Django WebSocket! Listening for sensor pipeline...")

def run_ws():
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()

# --------------------------------------------------
# 4. Matplotlib Animation Loop[cite: 1]
# --------------------------------------------------
def update_plot(frame, filtered_line, light_line, peak_points, diastolic_points, stats_text, ax):
    global last_print
    
    # Safely copy raw buffer values to array
    with data_lock:
        signal_copy = list(raw_ir_buffer)
        
    if len(signal_copy) < 100:
        return filtered_line, light_line, peak_points, diastolic_points

    # Run the raw data through our processing pipeline[cite: 1]
    results = processor.preprocess_signal(signal_copy)
    
    filtered = results["display"]
    light = results["light_display"]
    peaks = results["systolic_peaks"]
    diastolic = results["diastolic_peaks"]
    frequency = results["frequency"]
    bpm = results["bpm"]
    stats = results["statistics"]

    # Calculate current relative time representation
    x = np.arange(len(filtered)) / FS

    # Assign datasets to plot markers
    filtered_line.set_data(x, filtered)
    light_line.set_data(x, light)

    if len(peaks):
        peak_points.set_data(x[peaks], filtered[peaks])
    else:
        peak_points.set_data([], [])

    if len(diastolic):
        diastolic_points.set_data(x[diastolic], filtered[diastolic])
    else:
        diastolic_points.set_data([], [])

    # Keep visualization sliding forward
    ax.set_xlim(x[-1] - WINDOW_SECONDS, x[-1])

    # Update GUI statistics window
    stats_text.set_text(
        f"Heart Rate : {bpm:5.1f} BPM\n"
        f"Frequency  : {frequency:4.2f} Hz\n"
        f"Systolic   : {len(peaks)}\n"
        f"Diastolic  : {len(diastolic)}\n"
        f"Mean       : {stats['mean']:.3f}\n"
        f"Std Dev    : {stats['std']:.3f}\n"
        f"RMS        : {stats['rms']:.3f}"
    )

    # Print log to Python terminal exactly every 1 second[cite: 1]
    if time.time() - last_print > 1:
        print("=" * 45)
        print(f"Frequency : {frequency:.2f} Hz")
        print(f"BPM       : {bpm:.1f}")
        print(f"Systolic  : {len(peaks)}")
        print(f"Diastolic : {len(diastolic)}")
        last_print = time.time()

    return filtered_line, light_line, peak_points, diastolic_points

# --------------------------------------------------
# 5. Main Execution Thread Configuration[cite: 1]
# --------------------------------------------------
def main():
    # Start WebSocket reader thread
    ws_thread = threading.Thread(target=run_ws)
    ws_thread.daemon = True
    ws_thread.start()

    print("Receiving filtered Django WebSocket stream...")

    # Configure Matplotlib window style[cite: 1]
    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.canvas.manager.set_window_title("Integrated Real-time PPG Filter (Django Source)")

    filtered_line, = ax.plot([], [], color="royalblue", linewidth=2, label="Fully filtered", zorder=3)
    light_line, = ax.plot([], [], color="gray", linewidth=1, alpha=0.6, label="Lightly filtered (raw-ish)", zorder=1)
    
    peak_points, = ax.plot([], [], "ro", markersize=6, label="Systolic Peaks")
    diastolic_points, = ax.plot([], [], "go", markersize=7, label="Diastolic Peaks")

    ax.set_title("Live Filtered PPG Signal Pipeline")
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Normalized Amplitude")
    ax.set_xlim(0, BUFFER_SIZE / FS)
    ax.set_ylim(-1.2, 1.2)
    ax.grid(True)

    stats_text = ax.text(
        0.02, 0.98, "",
        transform=ax.transAxes,
        fontsize=11,
        verticalalignment="top",
        bbox=dict(facecolor="white", alpha=0.8)
    )

    ax.legend(loc="upper right")

    # Run animation loop (updates every 50ms to match original configuration)[cite: 1]
    ani = animation.FuncAnimation(
        fig,
        update_plot,
        fargs=(filtered_line, light_line, peak_points, diastolic_points, stats_text, ax),
        interval=50,
        blit=False,
        cache_frame_data=False
    )

    try:
        plt.tight_layout()
        plt.show()
    finally:
        print("Visualizer application terminated.")

if __name__ == "__main__":
    main()