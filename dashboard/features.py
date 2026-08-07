import statistics
import numpy as np
from scipy.signal import find_peaks


class PPGFeatureExtractor:
    """
    Feature extractor for beat-wise and session-level PPG derived biomarkers.
    """

    # Initializes the extractor with sampling frequency.
    def __init__(self, fs=125):
        self.fs = fs

    # Computes robust BPM from peak timestamps using RR-interval filtering.
    @staticmethod
    def extract_heart_rate_from_peaks(peaks, time_buffer, fallback_bpm):
        """
        Recomputes BPM from peak timestamps using the same logic used by MQTT flow.
        """
        bpm = fallback_bpm

        if len(peaks) >= 2:
            peak_times = [time_buffer[idx] for idx in peaks if idx < len(time_buffer)]

            if len(peak_times) >= 2:
                rr_intervals = [peak_times[i] - peak_times[i - 1] for i in range(1, len(peak_times))]
                valid_rr = [rr for rr in rr_intervals if 272000 <= rr <= 1500000]

                if valid_rr:
                    initial_median = statistics.median(valid_rr)
                    clean_rr = [rr for rr in valid_rr if rr <= (1.5 * initial_median)]

                    if len(clean_rr) >= 2:
                        final_median_rr_us = statistics.median(clean_rr)
                        bpm = 60000000.0 / final_median_rr_us
                    else:
                        print("⚠️ Not enough clean RR intervals, falling back to basic processing BPM.")

        return bpm

    # Returns normalized age as a float feature.
    def feature_age(self, age):
        return float(age)

    # Returns PAT feature with a default fallback value.
    def feature_pat(self, pat_ms):
        return float(pat_ms) if pat_ms is not None else 150.0

    # Normalizes a waveform into [0, 1] and handles degenerate inputs.
    def _to_normalized(self, signal):
        raw_signal = np.asarray(signal, dtype=float)
        if raw_signal.size == 0:
            return None
        signal_min = np.min(raw_signal)
        signal_max = np.max(raw_signal)
        signal_range = signal_max - signal_min
        if np.isclose(signal_range, 0.0):
            return None
        return (raw_signal - signal_min) / signal_range

    # Iterates beat windows defined by consecutive systolic peaks.
    def _iter_beats(self, ppg_signal, systolic_peaks, min_len=10):
        for i in range(len(systolic_peaks) - 1):
            sys_idx = int(systolic_peaks[i])
            next_sys_idx = int(systolic_peaks[i + 1])
            beat_signal = ppg_signal[sys_idx:next_sys_idx]
            if len(beat_signal) >= min_len:
                yield sys_idx, next_sys_idx, beat_signal

    # Calculates AGI_mod from second-derivative waveform landmarks.
    def calculate_agi_mod(self, signal):
        norm_signal = self._to_normalized(signal)
        if norm_signal is None or len(norm_signal) < 8:
            return np.nan

        N = len(norm_signal)
        d1 = np.gradient(norm_signal, 1.0 / self.fs)
        d2 = np.gradient(d1, 1.0 / self.fs)
        d3 = np.gradient(d2, 1.0 / self.fs)

        a_window_end = max(1, N // 3)
        a_idx = np.argmax(d2[:a_window_end])
        a_amp = d2[a_idx]

        b_window_end = max(a_idx + 1, N // 2)
        b_segment = d2[a_idx:b_window_end]
        if b_segment.size == 0:
            return np.nan
        b_peaks, _ = find_peaks(-b_segment)
        b_idx = a_idx + (b_peaks[0] if len(b_peaks) > 0 else np.argmin(b_segment))
        b_amp = d2[b_idx]

        e_search_start = b_idx + int(N * 0.10)
        e_search_end = int(N * 0.70)
        if e_search_start >= e_search_end or d2[e_search_start:e_search_end].size == 0:
            return np.nan
        e_idx = e_search_start + np.argmax(d2[e_search_start:e_search_end])

        c_start = b_idx + int(N * 0.05)
        c_end = e_idx - int(N * 0.02)
        if c_start >= c_end or d2[c_start:c_end].size == 0:
            return np.nan
        c_window = d2[c_start:c_end]
        c_peaks, _ = find_peaks(c_window)
        if len(c_peaks) > 0:
            c_idx = c_start + c_peaks[0]
        else:
            d3_slice = d3[c_start:c_end]
            if d3_slice.size == 0:
                return np.nan
            c_idx = c_start + np.argmin(np.abs(d3_slice))
        c_amp = d2[c_idx]

        d_start = c_idx + int(N * 0.02)
        d_end = e_idx - int(N * 0.01)
        if d_start >= d_end or d2[d_start:d_end].size == 0:
            d_amp = c_amp
        else:
            d_window = -d2[d_start:d_end]
            d_peaks, _ = find_peaks(d_window)
            if len(d_peaks) > 0:
                d_idx = d_start + d_peaks[0]
            else:
                d3_slice = d3[d_start:d_end]
                if d3_slice.size > 0:
                    d_idx = d_start + np.argmin(np.abs(d3_slice))
                else:
                    d_idx = min(c_idx + 2, N - 1)
            d_amp = d2[d_idx]

        if np.isclose(a_amp, 0.0):
            return np.nan
        return (b_amp - c_amp - d_amp) / a_amp

    # Calculates reflection index as diastolic-to-systolic amplitude ratio.
    def calculate_ri(self, signal):
        norm_signal = self._to_normalized(signal)
        if norm_signal is None or len(norm_signal) < 6:
            return np.nan

        N = len(norm_signal)
        sys_peak_idx = np.argmax(norm_signal[:max(1, N // 2)])
        d1 = np.gradient(norm_signal)

        search_range = max(1, N // 3)
        inflection_slice = d1[sys_peak_idx:sys_peak_idx + search_range]
        if inflection_slice.size == 0:
            return np.nan
        inflection_rel_idx = np.argmin(inflection_slice)
        inflection_idx = sys_peak_idx + inflection_rel_idx

        start_search = inflection_idx + 1
        end_search = int(N * 0.80)
        if start_search >= end_search:
            start_search = min(sys_peak_idx + max(1, min(10, N - sys_peak_idx - 1)), N - 1)
            end_search = N

        search_window = norm_signal[start_search:end_search]
        d1_window = d1[start_search:end_search]
        if search_window.size == 0:
            return np.nan

        signal_peaks, _ = find_peaks(search_window)
        if len(signal_peaks) > 0:
            dia_peak_idx = start_search + signal_peaks[0]
        else:
            d1_peaks, _ = find_peaks(d1_window)
            if len(d1_peaks) > 0:
                dia_peak_idx = start_search + d1_peaks[0]
            else:
                dia_peak_idx = start_search + (np.argmax(d1_window) if d1_window.size > 0 else 0)

        sys_peak_amp = norm_signal[sys_peak_idx]
        dia_peak_amp = norm_signal[dia_peak_idx] if dia_peak_idx < N else 0.0
        if np.isclose(sys_peak_amp, 0.0):
            return np.nan
        return dia_peak_amp / sys_peak_amp

    # Calculates crest time in milliseconds from foot to systolic peak.
    def calculate_crest_time(self, signal):
        norm_signal = self._to_normalized(signal)
        if norm_signal is None or len(norm_signal) < 3:
            return np.nan

        N = len(norm_signal)
        sys_peak_idx = np.argmax(norm_signal[:max(1, N // 2)])
        foot_idx = np.argmin(norm_signal[:sys_peak_idx + 1]) if sys_peak_idx > 0 else 0
        ct_samples = sys_peak_idx - foot_idx
        return (ct_samples / self.fs) * 1000.0

    # Calculates maximum upstroke slope (dp/dt max) of a beat.
    def calculate_dpdt_max(self, signal):
        norm_signal = self._to_normalized(signal)
        if norm_signal is None or len(norm_signal) < 4:
            return np.nan

        N = len(norm_signal)
        d1 = np.gradient(norm_signal) * self.fs
        sys_peak_idx = np.argmax(norm_signal[:max(1, N // 2)])
        upstroke_window = d1[:sys_peak_idx]
        if upstroke_window.size == 0:
            return np.nan
        return upstroke_window[np.argmax(upstroke_window)]

    # Calculates SEVR and systolic/diastolic waveform areas.
    def calculate_sevr(self, signal, lvet):
        norm_signal = self._to_normalized(signal)
        if norm_signal is None or len(norm_signal) < 4:
            return np.nan, np.nan, np.nan

        N = len(norm_signal)
        lvet_idx = int(np.round(lvet * self.fs))
        if lvet_idx >= N or lvet_idx <= 0:
            lvet_idx = N // 2

        t = np.arange(N) / self.fs
        t_sys = t[:lvet_idx + 1]
        ppg_sys = norm_signal[:lvet_idx + 1]
        t_dia = t[lvet_idx:]
        ppg_dia = norm_signal[lvet_idx:]

        a_sys = np.trapezoid(ppg_sys, t_sys)
        a_dia = np.trapezoid(ppg_dia, t_dia)
        ppg_sevr = a_dia / a_sys if not np.isclose(a_sys, 0.0) else np.nan
        return ppg_sevr, a_sys, a_dia

    # Aggregates mean crest time across valid beats.
    def feature_ct(self, ppg_signal, systolic_peaks):
        values = []
        for _, _, beat_signal in self._iter_beats(ppg_signal, systolic_peaks):
            ct = self.calculate_crest_time(beat_signal)
            if not np.isnan(ct):
                values.append(ct)
        return float(np.mean(values)) if values else 0.0

    # Aggregates mean reflection index across valid beats.
    def feature_ri(self, ppg_signal, systolic_peaks):
        values = []
        for _, _, beat_signal in self._iter_beats(ppg_signal, systolic_peaks):
            ri = self.calculate_ri(beat_signal)
            if not np.isnan(ri):
                values.append(ri)
        return float(np.mean(values)) if values else 0.0

    # Aggregates mean dp/dt max across valid beats.
    def feature_dpdt_max(self, ppg_signal, systolic_peaks):
        values = []
        for _, _, beat_signal in self._iter_beats(ppg_signal, systolic_peaks):
            dpdt = self.calculate_dpdt_max(beat_signal)
            if not np.isnan(dpdt):
                values.append(dpdt)
        return float(np.mean(values)) if values else 0.0

    # Aggregates mean AGI_mod across valid beats.
    def feature_agi_mod(self, ppg_signal, systolic_peaks):
        values = []
        for _, _, beat_signal in self._iter_beats(ppg_signal, systolic_peaks):
            agi = self.calculate_agi_mod(beat_signal)
            if not np.isnan(agi):
                values.append(agi)
        return float(np.mean(values)) if values else 0.0

    # Computes stiffness index and average LVET from peak positions.
    def feature_si_and_lvet(self, systolic_peaks, diastolic_peaks):
        si_values = []
        lvet_values = []

        for i in range(len(systolic_peaks) - 1):
            sys_idx = int(systolic_peaks[i])
            next_sys_idx = int(systolic_peaks[i + 1])
            dias_candidates = diastolic_peaks[(diastolic_peaks > sys_idx) & (diastolic_peaks < next_sys_idx)]

            if len(dias_candidates) > 0:
                dias_idx = int(dias_candidates[0])
                delta_t = (dias_idx - sys_idx) / self.fs
                si = 1.75 / delta_t if delta_t > 0 else np.nan
                if not np.isnan(si):
                    si_values.append(si)
                lvet_values.append(delta_t)

        mean_si = float(np.mean(si_values)) if si_values else 0.0
        avg_lvet = float(np.mean(lvet_values)) if lvet_values else 0.3
        return mean_si, avg_lvet

    # Aggregates mean SEVR, Asys, and Adia across valid beats.
    def feature_ppg_sevr_asys_adia(self, ppg_signal, systolic_peaks, avg_lvet):
        sevr_values = []
        asys_values = []
        adia_values = []

        for _, _, beat_signal in self._iter_beats(ppg_signal, systolic_peaks):
            sevr, a_sys, a_dia = self.calculate_sevr(beat_signal, lvet=avg_lvet)
            if not np.isnan(sevr):
                sevr_values.append(sevr)
            if not np.isnan(a_sys):
                asys_values.append(a_sys)
            if not np.isnan(a_dia):
                adia_values.append(a_dia)

        mean_sevr = float(np.mean(sevr_values)) if sevr_values else 0.0
        mean_asys = float(np.mean(asys_values)) if asys_values else 0.0
        mean_adia = float(np.mean(adia_values)) if adia_values else 0.0
        return mean_sevr, mean_asys, mean_adia

    # Converts LVET from seconds to milliseconds.
    def feature_lvet_ms(self, avg_lvet_seconds):
        return float(avg_lvet_seconds * 1000.0)

    # Builds the full model-ready feature dictionary from PPG inputs.
    def extract_features(self, ppg_signal, systolic_peaks, diastolic_peaks, age=30, pat_ms=None, peak_timestamps_us=None):
        """
        Extracts tabular features for the Risk classifier and BP regression models.
        """
        systolic_peaks = np.asarray(systolic_peaks)
        diastolic_peaks = np.asarray(diastolic_peaks)

        if len(systolic_peaks) < 2:
            return None

        if peak_timestamps_us is not None:
            time_axis_us = peak_timestamps_us
        else:
            time_axis_us = [((idx / self.fs) * 1000000.0) for idx in range(len(ppg_signal))]
        hr = self.extract_heart_rate_from_peaks(systolic_peaks, time_axis_us, fallback_bpm=0.0)

        features = {}
        features['AGE'] = self.feature_age(age)
        features['HR'] = float(hr) if np.isfinite(hr) and hr > 0 else 0.0
        features['CT'] = self.feature_ct(ppg_signal, systolic_peaks)
        features['RI'] = self.feature_ri(ppg_signal, systolic_peaks)
        features['dpdt_max'] = self.feature_dpdt_max(ppg_signal, systolic_peaks)
        features['AGI_mod'] = self.feature_agi_mod(ppg_signal, systolic_peaks)

        mean_si, avg_lvet = self.feature_si_and_lvet(systolic_peaks, diastolic_peaks)
        features['SI'] = mean_si
        features['LVET'] = self.feature_lvet_ms(avg_lvet)

        mean_sevr, mean_asys, mean_adia = self.feature_ppg_sevr_asys_adia(ppg_signal, systolic_peaks, avg_lvet)
        features['PPG_SEVR'] = mean_sevr
        features['PPG_Asys'] = mean_asys
        features['PPG_Adia'] = mean_adia

        features['PAT'] = self.feature_pat(pat_ms)
        return features


 # Backward-compatible wrapper for heart-rate extraction calls.
def extract_heart_rate_from_peaks(peaks, time_buffer, fallback_bpm):
    """
    Backward-compatible module wrapper for existing imports.
    """
    return PPGFeatureExtractor.extract_heart_rate_from_peaks(peaks, time_buffer, fallback_bpm)


