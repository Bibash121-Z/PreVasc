# ==========================================================
# pcg_processor.py
# Clean Acoustic PCG Engine (Zero-Baseline + 75 BPM Lock)
# ==========================================================

import numpy as np
from scipy.signal import butter, iirnotch, sosfiltfilt, filtfilt, find_peaks, hilbert, savgol_filter


class PCGProcessor:

    def __init__(self, fs=500, pad_sec=0.5):
        self.fs = fs

        # 1. Acoustic bandpass (25-140Hz) isolates S1/S2 acoustic frequencies
        self.sos_bandpass = butter(4, [25.0, 140.0], btype="bandpass", fs=fs, output="sos")

        # 2. Dual mains-hum rejection (50Hz + 100Hz harmonic)
        self.b50, self.a50 = iirnotch(50.0, 20.0, fs)
        self.b100, self.a100 = iirnotch(100.0, 20.0, fs)

        # 3. Clean Envelope Low-Pass (15.0 Hz): Merges acoustic bursts into smooth hills
        self.sos_envelope = butter(4, 15.0, btype="low", fs=fs, output="sos")

        self.pad_samples = int(pad_sec * fs)
        self.previous_bpm = 0.0

    def preprocess_signal(self, signal):
        signal = np.asarray(signal, dtype=float)
        pad = self.pad_samples

        if len(signal) < (self.fs * 2) + (2 * pad):
            return {
                "raw": signal,
                "filtered": signal,
                "envelope": signal,
                "s1_peaks": np.array([], dtype=int),
                "s2_peaks": np.array([], dtype=int),
                "bpm": self.previous_bpm,
                "pad_samples": pad
            }

        centered = signal - np.mean(signal)

        # Dual 50Hz notch + 100Hz harmonic
        notched = filtfilt(self.b50, self.a50, centered)
        notched = filtfilt(self.b50, self.a50, notched)
        notched = filtfilt(self.b100, self.a100, notched)

        filtered_full = sosfiltfilt(self.sos_bandpass, notched) * 10.0

        # --- HILBERT ANALYTIC ENVELOPE (Smooth Natural Peaks, No Square Table-Tops) ---
        analytic_signal = hilbert(filtered_full)
        envelope_raw = np.abs(analytic_signal)

        # Smooth envelope with Savitzky-Golay (60ms window @ 500Hz)
        wl = min(31, len(envelope_raw) - 1 if (len(envelope_raw) - 1) % 2 == 1 else len(envelope_raw) - 2)
        envelope_full = savgol_filter(envelope_raw, window_length=wl, polyorder=2)

        # Scale for UI visibility [0 to 10]
        max_env_full = np.max(envelope_full)
        if max_env_full > 1e-6:
            envelope_full = (envelope_full / max_env_full) * 10.0

        # Slice off edge ringing transients
        filtered = filtered_full[pad:-pad] if pad > 0 else filtered_full
        envelope = envelope_full[pad:-pad] if pad > 0 else envelope_full

        s1_peaks, s2_peaks = self.detect_s1_s2(envelope)
        bpm = self.estimate_bpm(s1_peaks)

        return {
            "raw": signal,
            "filtered": filtered,
            "envelope": envelope,
            "s1_peaks": s1_peaks,
            "s2_peaks": s2_peaks,
            "bpm": bpm,
            "pad_samples": pad
        }

    def detect_s1_s2(self, envelope):
        if len(envelope) == 0:
            return np.array([], dtype=int), np.array([], dtype=int)

        max_env = np.max(envelope)
        if max_env < 0.5:
            return np.array([], dtype=int), np.array([], dtype=int)

        # S1: Dominant peaks spaced >= 0.45s apart
        min_s1_dist = int(0.45 * self.fs)
        s1_candidates, _ = find_peaks(
            envelope,
            distance=min_s1_dist,
            prominence=max(0.3, max_env * 0.18)
        )

        all_peaks, _ = find_peaks(
            envelope,
            distance=int(0.08 * self.fs),
            prominence=max(0.1, max_env * 0.05)
        )

        s1_peaks = []
        s2_peaks = []

        # Systolic window: S2 occurs 160ms to 360ms after S1
        min_sys = int(0.16 * self.fs)
        max_sys = int(0.36 * self.fs)

        for s1 in s1_candidates:
            s1_peaks.append(s1)
            valid_s2 = [p for p in all_peaks if (s1 + min_sys) <= p <= (s1 + max_sys)]
            if valid_s2:
                best_s2 = max(valid_s2, key=lambda p: envelope[p])
                s2_peaks.append(best_s2)

        return np.array(s1_peaks, dtype=int), np.array(s2_peaks, dtype=int)

    def estimate_bpm(self, s1_peaks):
        if len(s1_peaks) < 2:
            return self.previous_bpm

        raw_rr = np.diff(s1_peaks) / self.fs
        if len(raw_rr) == 0:
            return self.previous_bpm

        # Harmonic Dropout Correction: Split intervals > 1.4s where a faint S1 was skipped
        corrected_rr = []
        for rr in raw_rr:
            if 0.40 <= rr <= 1.40:
                corrected_rr.append(rr)
            elif 1.40 < rr <= 2.20:
                corrected_rr.append(rr / 2.0)
                corrected_rr.append(rr / 2.0)

        clean_rr = [r for r in corrected_rr if 0.44 <= r <= 1.33]
        if len(clean_rr) == 0:
            clean_rr = corrected_rr if len(corrected_rr) > 0 else raw_rr

        instant_bpm = 60.0 / np.median(clean_rr)

        if self.previous_bpm == 0:
            self.previous_bpm = instant_bpm
        else:
            self.previous_bpm = 0.80 * self.previous_bpm + 0.20 * instant_bpm

        return self.previous_bpm

    def assess_signal_quality(self, results):
        s1_peaks = results.get("s1_peaks", [])
        envelope = results.get("envelope", [])

        if len(envelope) == 0:
            return False, "No PCG data"

        max_env = np.max(envelope)
        if max_env < 1.0:
            return False, f"Weak PCG signal (env: {max_env:.1f})"

        if len(s1_peaks) < 3:
            return False, "Too few S1 beats"

        rr_intervals = np.diff(s1_peaks) / self.fs
        if len(rr_intervals) > 0 and np.std(rr_intervals) > 0.25:
            return False, f"Unstable PCG rhythm (Std: {np.std(rr_intervals):.3f}s)"

        print("PCG BPM: ", self.previous_bpm)
        return True, "PCG Clean"