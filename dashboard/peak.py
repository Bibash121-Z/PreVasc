# ==============================================================================
# dashboard/peaks.py
# ==============================================================================
import numpy as np
from scipy.signal import (
    butter,
    filtfilt,
    medfilt,
    find_peaks,
    savgol_filter
)

class PPGProcessor:
    def __init__(
        self,
        fs=100,
        lowcut=0.5,
        highcut=20.0,
        butter_order=5,
        median_kernel=3,
        moving_average_window=3
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
            current = (
                self.alpha * current +
                (1 - self.alpha) * sample
            )
            baseline[i] = current

        self.baseline = current
        return signal - baseline

    def median_filter(self, signal):
        return medfilt(
            signal,
            kernel_size=self.median_kernel
        )

    def butterworth_filter(self, signal):
        if len(signal) < 3 * max(len(self.a), len(self.b)):
            return signal
        return filtfilt(
            self.b,
            self.a,
            signal
        )

    def moving_average(self, signal):
        if self.ma_window <= 1:
            return signal
        kernel = np.ones(self.ma_window)
        kernel /= self.ma_window
        return np.convolve(
            signal,
            kernel,
            mode="same"
        )

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
        frequency = np.fft.rfftfreq(
            n,
            d=1 / self.fs
        )
        return frequency, magnitude

    def dominant_frequency(self, signal):
        frequency, magnitude = self.compute_fft(signal)
        mask = (
            (frequency >= 0.5) &
            (frequency <= 3.0)
        )
        frequency = frequency[mask]
        magnitude = magnitude[mask]

        if len(frequency) == 0:
            return 0.0

        index = np.argmax(magnitude)
        return frequency[index]

    def estimate_bpm(self, signal):
        n_samples = len(signal)
        refractory_samples = int(0.3 * self.fs)

        sig_max = np.max(signal)
        sig_min = np.min(signal)
        adaptive_threshold = sig_min + 0.6 + (sig_max - sig_max)

        systolic_peaks = []
        last_peak_idx = -refractory_samples

        for i in range(1, n_samples - 1):
            if signal[i] > signal[i - 1] and signal[i] > signal[i + 1]:
                if signal[i] > adaptive_threshold:
                    if (i - last_peak_idx) > refractory_samples:
                        systolic_peaks.append(i)
                        last_peak_idx = i

        if len(systolic_peaks) < 2:
            return 0

        # Calculate sliding threshold on recent peaks
        recent_peaks = systolic_peaks[-3:]
        adaptive_threshold = np.mean(signal[recent_peaks])

        peak_intervals = np.diff(systolic_peaks)
        mean_interval_samples = np.mean(peak_intervals)

        bpm = (self.fs * 60) / mean_interval_samples
        self.previous_bpm = (
            0.5 * self.previous_bpm +
            0.5 * bpm
        )
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

    def first_derivative(self, signal):
        return np.gradient(signal)

    def second_derivative(self, signal):
        return np.gradient(np.gradient(signal))

    def third_derivative(self, signal):
        return np.gradient(np.gradient(np.gradient(signal)))

    def detect_systolic_peaks(self, signal):
        signal = np.asarray(signal)
        if len(signal) < self.fs * 2:
            return np.array([], dtype=int)

        mean = np.mean(signal)
        std = np.std(signal)
        threshold = mean + 0.35 * std

        prominence = max(
            0.10 * (np.max(signal) - np.min(signal)),
            0.02
        )
        min_distance = int(0.33 * self.fs)

        peaks, properties = find_peaks(
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
            left = signal[p - 1]
            center = signal[p]
            right = signal[p + 1]
            if center > left and center > right:
                valid.append(p)

        return np.array(valid, dtype=int)

    def detect_diastolic(self, signal, systolic_peaks):
        signal = np.asarray(signal, dtype=float)
        diastolic = []
        n = len(signal)

        for i in range(len(systolic_peaks)):
            p_start = systolic_peaks[i]
            p_end = (
                systolic_peaks[i + 1]
                if i + 1 < len(systolic_peaks)
                else n
            )
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

            minima, _ = find_peaks(
                -window,
                prominence=min_prominence,
                distance=min_distance
            )

            diastolic_idx = None
            margin = max(int(0.10 * wlen), 4)

            for cand in minima:
                remaining = window[cand:]
                if len(remaining) - margin < 5:
                    continue

                search_zone = remaining[: len(remaining) - margin]
                bump_prominence = max(0.08 * local_range, 1e-6)

                maxima, _ = find_peaks(
                    search_zone,
                    prominence=bump_prominence,
                    distance=min_distance
                )

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

        if len(signal) < 200:
            return {
                "raw": signal,
                "baseline_removed": signal,
                "filtered": signal,
                "display": signal,
                "light_display": signal,
                "dppg": signal,
                "apg": signal,
                "sdppg": signal,
                "frequency": 0.0,
                "bpm": 0.0,
                "statistics": {},
                "systolic_peaks": np.array([], dtype=int),
                "diastolic_peaks": np.array([], dtype=int)
            }

        baseline_removed = self.remove_baseline(signal)
        median = self.median_filter(baseline_removed)
        light_display = self.normalize_display(median)

        filtered = self.butterworth_filter(median)
        filtered = self.savgol_smooth(filtered, window_length=7, polyorder=3)

        frequency = self.dominant_frequency(filtered)
        bpm = self.estimate_bpm(filtered)
        statistics = self.signal_statistics(filtered)

        dppg = self.first_derivative(filtered)
        apg = self.second_derivative(filtered)
        sdppg = self.third_derivative(filtered)

        systolic_peaks = self.detect_systolic_peaks(filtered)
        diastolic_peaks = self.detect_diastolic(filtered, systolic_peaks)
        display = self.normalize_display(filtered)

        return {
            "raw": signal,
            "baseline_removed": baseline_removed,
            "filtered": filtered,
            "display": display,
            "light_display": light_display,
            "dppg": dppg,
            "apg": apg,
            "sdppg": sdppg,
            "frequency": frequency,
            "bpm": bpm,
            "statistics": statistics,
            "systolic_peaks": systolic_peaks,
            "diastolic_peaks": diastolic_peaks
        }