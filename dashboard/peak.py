# ==========================================================
# peaks.py
#===========================================================

import numpy as np
from scipy.stats import skew
from scipy.signal import (
    butter,
    filtfilt,
    medfilt,
    find_peaks,
    savgol_filter
)


class PPGProcessor:

    # --------------------------------------------------
    # Constructor
    # --------------------------------------------------

    def __init__(
        self,
        fs=125,
        lowcut=0.5,
        highcut=8.0,  # Lowered from 25.0 to 8.0 to strongly smooth baseline noise
        butter_order=4,
        median_kernel=5, # Increased from 3 to 5 for better impulse noise rejection
        moving_average_window=5 # Increased from 3 to 5 for smoother raw-ish line
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
        self.previous_fft_bpm = 0.0

    # ==================================================
    # BASELINE REMOVAL
    # ==================================================

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

    # ==================================================
    # MEDIAN FILTER
    # ==================================================

    def median_filter(self, signal):

        return medfilt(
            signal,
            kernel_size=self.median_kernel
        )

    # ==================================================
    # BUTTERWORTH FILTER
    # ==================================================

    def butterworth_filter(self, signal):

        if len(signal) < 3 * max(len(self.a), len(self.b)):
            return signal

        return filtfilt(
            self.b,
            self.a,
            signal
        )

    # ==================================================
    # MOVING AVERAGE
    # ==================================================

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

    # ==================================================
    # SAVITZKY-GOLAY SMOOTHING
    # ==================================================
   

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

    # ==================================================
    # DISPLAY NORMALIZATION
    # ==================================================

    def normalize_display(self, signal):

        maximum = np.max(np.abs(signal))

        if maximum < 1e-8:
            return signal

        return signal / maximum

    # ==================================================
    # FFT
    # ==================================================

    def compute_fft(self, signal):

        signal = np.asarray(signal)

        n = len(signal)
        n_pad = n * 10  # Zero-padding for 10x higher frequency interpolation resolution

        fft = np.fft.rfft(signal, n=n_pad)

        magnitude = np.abs(fft)

        frequency = np.fft.rfftfreq(
            n_pad,
            d=1 / self.fs
        )

        return frequency, magnitude

    # ==================================================
    # DOMINANT FREQUENCY
    # ==================================================

    def dominant_frequency(self, signal):

        frequency, magnitude = self.compute_fft(signal)

        # Let's open up the heart rate mask!
        # 0.5 Hz = 30 BPM
        # 4.0 Hz = 240 BPM (plenty of room for running)
        mask = (
            (frequency >= 0.5) &
            (frequency <= 4.0)
        )

        frequency = frequency[mask]
        magnitude = magnitude[mask]

        if len(frequency) == 0:
            return 0.0

        index = np.argmax(magnitude)

        return frequency[index]

    # ==================================================
    # STABLE BPM (TIME-DOMAIN HRV)
    # ==================================================

    def estimate_bpm(self, peaks):

        if len(peaks) < 2:
            return self.previous_bpm
            
        # Calculate RR intervals (Peak-to-Peak time distances)
        rr_intervals = np.diff(peaks) / self.fs
        
        # Valid intervals only (filter out extreme glitches)
        valid_rr = rr_intervals[rr_intervals > 0.2]
        
        if len(valid_rr) == 0:
            return self.previous_bpm
            
        # Compute exact BPM from time-domain peaks
        bpm = 60.0 / np.mean(valid_rr)

        if self.previous_bpm == 0:

            self.previous_bpm = bpm

        else:
            # Replaced the extreme 80% lock with a much faster response
            self.previous_bpm = (
                0.3 * self.previous_bpm +
                0.7 * bpm
            )

        return self.previous_bpm

    # ==================================================
    # SIGNAL STATISTICS
    # ==================================================

    def signal_statistics(self, signal):

        return {

            "mean": np.mean(signal),
            "rms": np.sqrt(np.mean(signal ** 2)),
            "std": np.std(signal),
            "max": np.max(signal),
            "min": np.min(signal),
            "energy": np.sum(signal ** 2)

        }

    # ==================================================
    # DERIVATIVES
    # ==================================================

    def first_derivative(self, signal):
        return np.gradient(signal)

    def second_derivative(self, signal):
        return np.gradient(np.gradient(signal))

    def third_derivative(self, signal):
        return np.gradient(np.gradient(np.gradient(signal)))

    # ==================================================
    # ROBUST SYSTOLIC PEAK DETECTION
    # ==================================================

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

            if p < 3:
                continue
            if p > len(signal) - 4:
                continue

            left = signal[p - 1]
            center = signal[p]
            right = signal[p + 1]

            if center > left and center > right:
                valid.append(p)

        return np.array(valid, dtype=int)

    # ==================================================
    # DIASTOLIC PEAK DETECTION — V4
    # Systolic + diastolic only. No notch tracking/output.
    # ==================================================

    def detect_diastolic(self, signal, systolic_peaks):

        signal = np.asarray(signal, dtype=float)
        grad = np.gradient(signal)  # First derivative
        
        diastolic = []
        n = len(signal)

        for i in range(len(systolic_peaks)):

            p_start = systolic_peaks[i]

            p_end = (
                systolic_peaks[i + 1]
                if i + 1 < len(systolic_peaks)
                else n
            )

            m = p_end - p_start

            if m < 15:
                continue

            # 1. Find the wave foot (minimum) between this systolic peak and the next.
            # Start search slightly after the systolic peak to avoid its immediate peak curvature.
            filter_ripple_margin = max(int(0.10 * m), 3)
            search_start = p_start + filter_ripple_margin
            
            foot_rel_idx = np.argmin(signal[search_start : p_end])
            foot_idx = search_start + foot_rel_idx

            search_end = foot_idx
            
            if search_start >= search_end or (search_end - search_start) < 3:
                continue

            search_window = signal[search_start:search_end]
            search_grad = grad[search_start:search_end]
            
            # Step A: Is there a true upward bump in the raw signal? (Healthy / Class 1)
            bump_peaks, _ = find_peaks(search_window)
            
            if len(bump_peaks) > 0:
                # Select the FIRST bump on the downslope (Diastolic Peak)
                diastolic.append(search_start + bump_peaks[0])
            else:
                # Step B: Look for an inflection point/shoulder (Stiff / Class 2 or 3)
                # This is a local MAXIMUM in the first derivative (slope getting less negative)
                local_grad_range = np.max(grad[p_start:p_end]) - np.min(grad[p_start:p_end])
                
                # LOWERED prominence requirement significantly to catch subtle shoulders at high HR
                prominence = max(0.005 * local_grad_range, 1e-6) 
                
                grad_peaks, props = find_peaks(search_grad, prominence=prominence)
                
                if len(grad_peaks) > 0:
                    # Select the FIRST inflection on the downslope
                    diastolic.append(search_start + grad_peaks[0])
                else:
                    # Fallback: Absolute flattest point in this downslope region
                    diastolic.append(search_start + np.argmax(search_grad))

        return np.array(diastolic, dtype=int)

    # ==================================================
    # COMPLETE PIPELINE
    # ==================================================

    def preprocess_signal(self, signal):

        signal = np.asarray(signal, dtype=float)

        # INVERSION FIX FOR REFLECTANCE PPG
        # The MAX30105 raw ADC drops during systole (blood absorbs light).
        # We invert it here immediately so that all downstream functions, CNNs, 
        # and database equations correctly process systole as a rapid UPWARD peak.
        signal = -signal

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
                "fft_bpm": 0.0,
                "statistics": {},
                "systolic_peaks": np.array([], dtype=int),
                "diastolic_peaks": np.array([], dtype=int)
            }

        baseline_removed = self.remove_baseline(signal)

        median = self.median_filter(baseline_removed)

        # --------------------------------------------
        # Lightly-filtered comparison signal.
        # Only baseline removal + median (impulse-noise removal).
        # Skips butterworth + moving-average so you can see whether
        # a feature that's missing in "filtered" was ever present
        # before those two smoothing stages ran.
        # --------------------------------------------

        light_display = self.normalize_display(median)

        filtered = self.butterworth_filter(median)

        filtered = self.savgol_smooth(filtered, window_length=7, polyorder=3)

        frequency = self.dominant_frequency(filtered)

        statistics = self.signal_statistics(filtered)

        dppg = self.first_derivative(filtered)

        apg = self.second_derivative(filtered)

        sdppg = self.third_derivative(filtered)

        systolic_peaks = self.detect_systolic_peaks(filtered)
        
        bpm = self.estimate_bpm(systolic_peaks)
        raw_fft_bpm = frequency * 60.0
        if self.previous_fft_bpm == 0:
            self.previous_fft_bpm = raw_fft_bpm
        else:
            self.previous_fft_bpm = 0.3 * self.previous_fft_bpm + 0.7 * raw_fft_bpm

        diastolic_peaks = self.detect_diastolic(
            filtered,
            systolic_peaks
        )

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
            "fft_bpm": self.previous_fft_bpm,
            "statistics": statistics,
            "systolic_peaks": systolic_peaks,
            "diastolic_peaks": diastolic_peaks
        }

    # ==================================================
    # SIGNAL QUALITY ASSESSMENT
    # ==================================================

    def assess_signal_quality(self, results):
        """
        Evaluates a processed 10-second signal to determine if it is clean
        using Perfusion Index (PI), Skewness, and RR Interval Standard Deviation.
        Returns: (is_valid: bool, reason: str)
        """
        peaks = results.get("systolic_peaks", [])
        raw_signal = results.get("raw", [])
        filtered_signal = results.get("filtered", [])
        
        # 1. We need a minimum number of peaks to perform math (e.g. at least 4 peaks for ~10 seconds)
        if len(peaks) < 4:
            return False, "Too few peaks"

        # --------------------------------------------------
        # A. RR Interval Standard Deviation (Stability)
        # --------------------------------------------------
        rr_intervals = np.diff(peaks) / self.fs
        rr_std = np.std(rr_intervals)
        
        # In a 10s window, healthy resting RR std dev should typically be under 0.15s. 
        # High std dev implies motion artifacts displacing peaks, or ectopic beats.
        if rr_std > 0.15: 
            return False, f"RR variability too high (Std: {rr_std:.3f}s)"

        # --------------------------------------------------
        # B. Skewness Quality Metric (Template Matching Proxy)
        # --------------------------------------------------
        # A healthy, clean PPG pulse is asymmetric (sharp systolic rise, slow diastolic fall with a notch)
        # Clean signals usually have positive skewness (e.g., > 0.1). 
        # Noise or sinusoidal motion artifacts tend to drop skewness towards 0 or below.
        sig_skew = skew(filtered_signal)
        
        if sig_skew < 0.1:
            return False, f"Skewness too low (Skew: {sig_skew:.2f})"

        # --------------------------------------------------
        # C. Perfusion Index (PI) Proxy
        # --------------------------------------------------
        # PI = (AC component / DC component) * 100
        # In raw reflectance PPG (where signal dropped down initially and was inverted), 
        # the true DC is the baseline light level, and AC is the pulse amplitude.
        
        # Approximate DC: Mean of the un-normalized, absolute raw sensor readings (before inversion)
        dc_component = np.mean(np.abs(raw_signal))
        
        # Approximate AC: RMS of the baseline-removed signal (or Mean peak-to-peak amplitude)
        # We'll use the peak-to-peak range of the filtered signal as the AC proxy.
        ac_component = np.max(filtered_signal) - np.min(filtered_signal)
        
        # Prevent division by zero
        pi = 0.0
        if dc_component > 1e-6:
            pi = (ac_component / dc_component) * 100.0
            
        # A PI below 0.1% usually indicates very poor blood flow or the sensor is not on a finger.
        if pi < 0.1:
            return False, f"Weak Perfusion Index (PI: {pi:.2f}%)"

        # If it passes all 3 advanced checks:
        return True, "Signal Clean"
    