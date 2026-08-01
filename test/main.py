# ==========================================================
# main.py
# v4 — systolic + diastolic only (no notch tracking)
# ==========================================================

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from test.serial_reader import SerialReader
from dashboard.peak import PPGProcessor
from feature_extractor import PPGFeatureExtractor
import time

last_print = 0
last_extraction_time = 0

# --------------------------------------------------
# Configuration
# --------------------------------------------------

PORT = "COM8"
BAUDRATE = 115200
BUFFER_SIZE = 1250
FS = 125

# --------------------------------------------------
# Initialize
# --------------------------------------------------

reader = SerialReader(
    port=PORT,
    baudrate=BAUDRATE,
    buffer_size=BUFFER_SIZE
)

processor = PPGProcessor(
    fs=FS
)

if not reader.connect():
    print("Failed to connect.")
    exit()

reader.start()

print("Receiving filtered PPG waveform...")

# --------------------------------------------------
# Figure
# --------------------------------------------------

plt.style.use("ggplot")

fig, ax = plt.subplots(figsize=(12, 5))

filtered_line, = ax.plot([], [], color="royalblue", linewidth=2, label="Fully filtered", zorder=3)

light_line, = ax.plot([], [], color="gray", linewidth=1, alpha=0.6, label="Lightly filtered (raw-ish)", zorder=1)

peak_points, = ax.plot(
    [], [], "ro", markersize=6, label="Systolic Peaks"
)

diastolic_points, = ax.plot(
    [], [], "go", markersize=7, label="Diastolic Peaks"
)

ax.set_title("Filtered PPG Signal")
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

# --------------------------------------------------
# Animation
# --------------------------------------------------

def update(frame):

    timestamps, signal = reader.get_all_data()

    if len(signal) < 100:
        return filtered_line,

    results = processor.preprocess_signal(signal)

    filtered = results["display"]
    light = results["light_display"]
    peaks = results["systolic_peaks"]
    diastolic = results["diastolic_peaks"]
    frequency = results["frequency"]
    bpm = results["bpm"]
    fft_bpm = results.get("fft_bpm", 0.0)
    stats = results["statistics"]

    x = np.arange(len(filtered)) / FS

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

    WINDOW_SECONDS = 4

    ax.set_xlim(x[-1] - WINDOW_SECONDS, x[-1])

    global last_print, last_extraction_time

    # Evaluate signal quality for machine learning
    is_valid, reason = processor.assess_signal_quality(results)

    # Extract features if signal is valid (throttled to once every 3 seconds to avoid spamming)
    if is_valid and (time.time() - last_extraction_time > 3.0):
        extractor = PPGFeatureExtractor(fs=FS)
        features = extractor.extract_features(
            ppg_signal=results["display"],
            systolic_peaks=results["systolic_peaks"],
            diastolic_peaks=results["diastolic_peaks"],
            age=30, # Replace with actual patient age input later
            pat_ms=150.0 # Replace with actual PCG-to-PPG PAT later
        )
        
        if features is not None:
            print("\n" + "*" * 50)
            print("🟢 KEEPING 10s CLEAN SIGNAL 🟢")
            print("Extracted ML Features:")
            for k, v in features.items():
                print(f"   {k}: {v:.3f}")
            print("*" * 50 + "\n")
            last_extraction_time = time.time()

    stats_text.set_text(
        f"Status     : {reason}\n"
        f"BPM (Time) : {bpm:5.1f} BPM\n"
        f"BPM (FFT)  : {fft_bpm:5.1f} BPM\n"
        f"Frequency  : {frequency:4.2f} Hz\n"
        f"Systolic   : {len(peaks)}\n"
        f"Diastolic  : {len(diastolic)}\n"
        f"Mean       : {stats['mean']:.3f}"
    )

    if time.time() - last_print > 1:
        print("=" * 45)
        print(f"Status     : {reason}")
        print(f"Frequency  : {frequency:.2f} Hz")
        print(f"BPM (Time) : {bpm:.1f}")
        print(f"BPM (FFT)  : {fft_bpm:.1f}")
        print(f"Systolic   : {len(peaks)}")
        print(f"Diastolic  : {len(diastolic)}")
        last_print = time.time()

    return (
        filtered_line,
        light_line,
        peak_points,
        diastolic_points
    )

# --------------------------------------------------
# Animation Object
# --------------------------------------------------

ani = animation.FuncAnimation(
    fig,
    update,
    interval=50,
    blit=False,
    cache_frame_data=False
)

# --------------------------------------------------
# Run
# --------------------------------------------------

try:
    plt.tight_layout()
    plt.show()
finally:
    reader.stop()
    print("Serial connection closed.")