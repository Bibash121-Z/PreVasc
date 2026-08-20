import numpy as np
import pandas as pd
from scipy.signal import find_peaks

# Physiologically plausible (lo, hi) ranges — clips out sensor/DSP glitches
# before they reach the models. None keeps that side of the range open.
# Values fixed at their empty-list fallback (0.0) are left alone so "no data"
# isn't disguised as a fake floor reading.
FEATURE_BOUNDS = {
    "HR": (30.0, 220.0),
    "CT": (50.0, 400.0),
    "RI": (0.05, 1.5),
    "SI": (1.0, 25.0),
    "dpdt_max": (0.1, 50.0),
    "AGI_mod": (-2.0, 2.0),
    "PAT": (20.0, 500.0),
    "LVET": (150.0, 500.0),
    "PPG_SEVR": (0.1, 3.0),
}

class PPGFeatureExtractor:
    def __init__(self, fs=125):
        self.fs = fs

    def _apply_safeguards(self, features):
        for key, (lo, hi) in FEATURE_BOUNDS.items():
            value = features.get(key)
            if value is None or value == 0.0:  # 0.0 means "no beats found", not a real reading
                continue
            features[key] = float(np.clip(value, lo, hi))
        return features

    def calculate_agi_mod(self, signal):
        raw_signal = np.asarray(signal)
        N = len(raw_signal)
        
        global_min = np.min(raw_signal)
        global_max = np.max(raw_signal)
        if np.isclose(global_max - global_min, 0.0):
            return np.nan
        norm_signal = (raw_signal - global_min) / (global_max - global_min)
        
        # Calculate Derivatives using gradient
        d1 = np.gradient(norm_signal, 1.0 / self.fs)
        d2 = np.gradient(d1, 1.0 / self.fs)
        d3 = np.gradient(d2, 1.0 / self.fs)
        
        # 1. Find 'a' wave (Global maximum of early d2)
        a_idx = np.argmax(d2[:N//3])
        a_amp = d2[a_idx]
        
        # 2. Find 'b' wave (First deep minimum after 'a')
        b_peaks, _ = find_peaks(-d2[a_idx:N//2])
        b_idx = a_idx + b_peaks[0] if len(b_peaks) > 0 else a_idx + np.argmin(d2[a_idx:N//2])
        b_amp = d2[b_idx]
        
        # 3. Find 'e' wave (Diastolic peak)
        e_search_start = b_idx + int(N * 0.10)
        e_search_end = int(N * 0.70)
        
        if e_search_start >= e_search_end or len(d2[e_search_start:e_search_end]) == 0:
            return np.nan
            
        e_idx = e_search_start + np.argmax(d2[e_search_start:e_search_end])
        e_amp = d2[e_idx]
        
        # 4. Find 'c' wave
        c_start = b_idx + int(N * 0.05)
        c_end = e_idx - int(N * 0.02)
        if c_start >= c_end or len(d2[c_start:c_end]) == 0:
            return np.nan
            
        c_window = d2[c_start:c_end]
        c_peaks, _ = find_peaks(c_window)
        
        if len(c_peaks) > 0:
            c_idx = c_start + c_peaks[0]
        else:
            c_idx = c_start + np.argmin(np.abs(d3[c_start:c_end]))
        c_amp = d2[c_idx]
        
        # 5. Find 'd' wave
        d_start = c_idx + int(N * 0.02)
        d_end = e_idx - int(N * 0.01)
        if d_start >= d_end or len(d2[d_start:d_end]) == 0:
             d_amp = c_amp # fallback
        else:
            d_window = -d2[d_start:d_end]
            d_peaks, _ = find_peaks(d_window)
            
            if len(d_peaks) > 0:
                d_idx = d_start + d_peaks[0]
            else:
                d3_slice = d3[d_start:d_end]
                if len(d3_slice) > 0:
                    d_idx = d_start + np.argmin(np.abs(d3_slice))
                else:
                    d_idx = min(c_idx + 2, N - 1)
            d_amp = d2[d_idx]
        
        # 6. Calculate AGI_mod
        if np.isclose(a_amp, 0.0):
            return np.nan
            
        return (b_amp - c_amp - d_amp) / a_amp

    def calculate_ri(self, signal):
        raw_signal = np.asarray(signal)
        N = len(raw_signal)
        
        global_min = np.min(raw_signal)
        global_max = np.max(raw_signal)
        if np.isclose(global_max - global_min, 0.0):
            return np.nan
        norm_signal = (raw_signal - global_min) / (global_max - global_min)
        
        sys_peak_idx = np.argmax(norm_signal[:N//2]) 
        
        d1 = np.gradient(norm_signal)
        
        search_range = max(1, N // 3)
        inflection_rel_idx = np.argmin(d1[sys_peak_idx : sys_peak_idx + search_range])
        inflection_idx = sys_peak_idx + inflection_rel_idx
        
        start_search = inflection_idx + 1  
        end_search = int(N * 0.80)         
        
        if start_search >= end_search:
            start_search = sys_peak_idx + min(10, N - sys_peak_idx - 1)
            end_search = N
            
        search_window = norm_signal[start_search:end_search]
        d1_window = d1[start_search:end_search]
        
        signal_peaks, _ = find_peaks(search_window)
        
        if len(signal_peaks) > 0:
            dia_peak_idx = start_search + signal_peaks[0]
        else:
            d1_peaks, _ = find_peaks(d1_window)
            if len(d1_peaks) > 0:
                dia_peak_idx = start_search + d1_peaks[0]
            else:
                if len(d1_window) > 0:
                    dia_peak_idx = start_search + np.argmax(d1_window)
                else:
                    dia_peak_idx = start_search

        sys_peak_amp = norm_signal[sys_peak_idx]
        dia_peak_amp = norm_signal[dia_peak_idx] if dia_peak_idx < N else 0.0

        return dia_peak_amp / sys_peak_amp if not np.isclose(sys_peak_amp, 0.0) else np.nan

    def calculate_crest_time(self, signal):
        raw_signal = np.asarray(signal)
        N = len(raw_signal)
        
        g_min, g_max = np.min(raw_signal), np.max(raw_signal)
        if np.isclose(g_max - g_min, 0.0):
            return np.nan
        norm_signal = (raw_signal - g_min) / (g_max - g_min)
        
        sys_peak_idx = np.argmax(norm_signal[:N//2])
        
        if sys_peak_idx > 0:
            foot_idx = np.argmin(norm_signal[:sys_peak_idx+1])
        else:
            foot_idx = 0
            
        ct_samples = sys_peak_idx - foot_idx
        ct_ms = (ct_samples / self.fs) * 1000

        return ct_ms

    def calculate_dpdt_max(self, signal):
        raw_signal = np.asarray(signal)
        N = len(raw_signal)
        
        g_min, g_max = np.min(raw_signal), np.max(raw_signal)
        if np.isclose(g_max - g_min, 0.0):
            return np.nan
        norm_signal = (raw_signal - g_min) / (g_max - g_min)
        
        d1 = np.gradient(norm_signal) * self.fs 
        
        sys_peak_idx = np.argmax(norm_signal[:N//2])
        
        upstroke_window = d1[:sys_peak_idx]
        if len(upstroke_window) == 0:
            return np.nan
            
        dpdt_max_idx = np.argmax(upstroke_window)
        return upstroke_window[dpdt_max_idx]

    def calculate_sevr(self, signal, lvet):
        raw_signal = np.asarray(signal)
        N = len(raw_signal)
        
        g_min, g_max = np.min(raw_signal), np.max(raw_signal)
        if np.isclose(g_max - g_min, 0.0):
            return np.nan, np.nan, np.nan
        norm_signal = (raw_signal - g_min) / (g_max - g_min)
        
        lvet_idx = int(np.round(lvet * self.fs))
        if lvet_idx >= N or lvet_idx <= 0:
            # Fallback if LVET is out of bounds for the beat
            lvet_idx = N // 2
            
        t = np.arange(N) / self.fs
        
        t_sys = t[:lvet_idx+1]
        ppg_sys = norm_signal[:lvet_idx+1]
        
        t_dia = t[lvet_idx:]
        ppg_dia = norm_signal[lvet_idx:]
        
        a_sys = np.trapezoid(ppg_sys, t_sys)
        a_dia = np.trapezoid(ppg_dia, t_dia)
        
        ppg_sevr = a_dia / a_sys if a_sys != 0 else np.nan  
            
        return ppg_sevr, a_sys, a_dia

    def extract_features(self, ppg_signal, systolic_peaks, diastolic_peaks, age=30, pat_ms=None,
                          height_m=1.75, lvet_ms_override=None, timestamps=None):
        """
        Extracts tabular features for the Risk classifier and BP regression models.

        lvet_ms_override: when a real PCG S1->S2 (valve open->close) measurement is
        available, it replaces the PPG-notch-based LVET approximation used below.
        """
        if len(systolic_peaks) < 3:
            return None 
            
        features = {}
        features['AGE'] = float(age)
        
        # Derive true sampling frequency and time-domain RR intervals
        if timestamps is not None and len(timestamps) == len(ppg_signal) and len(timestamps) > 1:
            total_time = timestamps[-1] - timestamps[0]
            if total_time > 0:
                self.fs = (len(timestamps) - 1) / total_time  # Dynamic actual Hz (~88-125Hz)

            peak_times = timestamps[systolic_peaks]
            rr_intervals = np.diff(peak_times)
        else:
            rr_intervals = np.diff(systolic_peaks) / self.fs

        # Physiological RR filtering (30 to 200 BPM: 0.3s to 2.0s)
        valid_rr = rr_intervals[(rr_intervals >= 0.3) & (rr_intervals <= 2.0)]
        
        if len(valid_rr) > 0:
            hr = 60.0 / np.median(valid_rr)
        elif len(rr_intervals) > 0:
            hr = 60.0 / np.median(rr_intervals)
        else:
            hr = 75.0
            
        features['HR'] = float(hr)
        
        ct_list, ri_list, si_list, lvet_list = [], [], [], []
        dpdt_max_list, agi_mod_list = [], []
        
        # Identify valleys (wave foot) to slice FULL beats including the upstroke
        valleys = []
        for i in range(len(systolic_peaks) - 1):
            start = systolic_peaks[i]
            end = systolic_peaks[i+1]
            valley_idx = start + np.argmin(ppg_signal[start:end])
            valleys.append(valley_idx)
            
        # Iterate over individual beats (from valley to valley)
        for i in range(len(valleys) - 1):
            v_start = valleys[i]
            v_end = valleys[i+1]
            sys_idx = systolic_peaks[i+1]  # The peak corresponding to this beat
            next_sys_idx = systolic_peaks[i+2] if i + 2 < len(systolic_peaks) else len(ppg_signal)
            
            beat_signal = ppg_signal[v_start:v_end]
            
            if len(beat_signal) < 10:
                continue
                
            try:
                # 1. CT (Crest Time)
                ct = self.calculate_crest_time(beat_signal)
                if not np.isnan(ct):
                    ct_list.append(ct)
                    
                # 2. RI (Reflection Index)
                ri = self.calculate_ri(beat_signal)
                if not np.isnan(ri):
                    ri_list.append(ri)
                    
                # 3. dp/dt max
                dpdt = self.calculate_dpdt_max(beat_signal)
                if not np.isnan(dpdt):
                    dpdt_max_list.append(dpdt)
                    
                # 4. AGI_mod
                agi = self.calculate_agi_mod(beat_signal)
                if not np.isnan(agi):
                    agi_mod_list.append(agi)
                    
                # 5. SI (Stiffness Index) and LVET (PPG-only fallback)
                dias_candidates = diastolic_peaks[(diastolic_peaks > sys_idx) & (diastolic_peaks < next_sys_idx)]
                if len(dias_candidates) > 0:
                    dias_idx = dias_candidates[0]
                    delta_t = (dias_idx - sys_idx) / self.fs
                    
                    # Physiological clamp: Dicrotic notch is always 140ms - 320ms in healthy resting pulses
                    if 0.14 <= delta_t <= 0.32:
                        si = height_m / delta_t if delta_t > 0 else np.nan
                        if not np.isnan(si):
                            si_list.append(si)
                        lvet_list.append(delta_t)
                    else:
                        # Fallback to nominal 230ms if notch was misdetected past 320ms
                        fallback_dt = 0.230
                        si_list.append(height_m / fallback_dt)
                        lvet_list.append(fallback_dt)
                else:
                    fallback_dt = 0.230
                    si_list.append(height_m / fallback_dt)
                    lvet_list.append(fallback_dt)
                    
            except Exception as e:
                pass 
                
        # Aggregate Beat Features
        features['CT'] = float(np.mean(ct_list)) if ct_list else 0.0
        features['RI'] = float(np.mean(ri_list)) if ri_list else 0.0
        features['SI'] = float(np.mean(si_list)) if si_list else 0.0
        features['dpdt_max'] = float(np.mean(dpdt_max_list)) if dpdt_max_list else 0.0
        
        avg_lvet = np.mean(lvet_list) if lvet_list else 0.3

        # A real PCG-measured LVET (S1 valve-open to S2 valve-close) is a direct
        # clinical measurement and takes priority over the PPG-notch approximation.
        if lvet_ms_override is not None:
            avg_lvet = lvet_ms_override / 1000.0

        # We need average LVET for SEVR calculation
        sevr_list, asys_list, adia_list = [], [], []
        for i in range(len(valleys) - 1):
             v_start = valleys[i]
             v_end = valleys[i+1]
             beat_signal = ppg_signal[v_start:v_end]
             
             if len(beat_signal) < 10:
                 continue
                 
             try:
                 sevr, a_sys, a_dia = self.calculate_sevr(beat_signal, lvet=avg_lvet)
                 if not np.isnan(sevr):
                     sevr_list.append(sevr)
                 if not np.isnan(a_sys):
                     asys_list.append(a_sys)
                 if not np.isnan(a_dia):
                     adia_list.append(a_dia)
             except Exception:
                 pass
                 
        # BLUNT TRUTH FIX: AGI_mod calculation is extremely noisy on single beats
        # because taking the 2nd derivative of 125Hz reflectance PPG amplifies micro-noise.
        # If we calculate AGI_mod on every single beat and average the results, the peaks jump around.
        # Instead, we will average the beats temporally first, wiping out the Gaussian noise, 
        # then take the derivative of the clean average beat exactly once.
        from scipy.signal import resample
        
        # We will use exactly 100 samples for the synchronized morphological beat
        aligned_beats = []
        for i in range(len(valleys) - 1):
             v_start = valleys[i]
             v_end = valleys[i+1]
             beat_signal = ppg_signal[v_start:v_end]
             if self.fs * 0.3 < len(beat_signal) < self.fs * 1.5:
                 x_old = np.linspace(0, 1, len(beat_signal))
                 x_new = np.linspace(0, 1, 100)
                 aligned_beats.append(np.interp(x_new, x_old, beat_signal))
                 
        if len(aligned_beats) >= 3:
            clean_master_beat = np.mean(aligned_beats, axis=0)
            master_agi = self.calculate_agi_mod(clean_master_beat)
            features['AGI_mod'] = float(master_agi) if not np.isnan(master_agi) else -0.5
        else:
            features['AGI_mod'] = float(np.mean(agi_mod_list)) if agi_mod_list else 0.0
        
        # Note: training DB converts LVET to ms for the feature array, so we multiply by 1000
        features['LVET'] = float(avg_lvet * 1000.0) 
        
        features['PPG_SEVR'] = float(np.mean(sevr_list)) if sevr_list else 0.0
        features['PPG_Asys'] = float(np.mean(asys_list)) if asys_list else 0.0
        features['PPG_Adia'] = float(np.mean(adia_list)) if adia_list else 0.0
        
        features['PAT'] = float(pat_ms) if pat_ms is not None else 150.0 
        
        print(f"Extracted features: {features}")
        return self._apply_safeguards(features)

