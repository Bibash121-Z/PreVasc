import numpy as np
import pandas as pd
from scipy.signal import find_peaks

class PPGFeatureExtractor:
    def __init__(self, fs=125):
        self.fs = fs

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

    def extract_features(self, ppg_signal, systolic_peaks, diastolic_peaks, age=30, pat_ms=None):
        """
        Extracts tabular features for the Risk classifier and BP regression models.
        """
        if len(systolic_peaks) < 2:
            return None 
            
        features = {}
        features['AGE'] = float(age)
        
        rr_intervals = np.diff(systolic_peaks) / self.fs
        hr = 60.0 / np.mean(rr_intervals)
        features['HR'] = float(hr)
        
        ct_list, ri_list, si_list, lvet_list = [], [], [], []
        dpdt_max_list, agi_mod_list = [], []
        ppg_asys_list, ppg_adia_list = [], []
        
        # Iterate over individual beats
        for i in range(len(systolic_peaks) - 1):
            sys_idx = systolic_peaks[i]
            next_sys_idx = systolic_peaks[i+1]
            beat_signal = ppg_signal[sys_idx:next_sys_idx]
            
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
                    
                # 5. SI (Stiffness Index) and LVET
                dias_candidates = diastolic_peaks[(diastolic_peaks > sys_idx) & (diastolic_peaks < next_sys_idx)]
                if len(dias_candidates) > 0:
                    dias_idx = dias_candidates[0]
                    delta_t = (dias_idx - sys_idx) / self.fs
                    
                    # Assuming height logic, substitute 1.75m default
                    si = 1.75 / delta_t if delta_t > 0 else np.nan
                    if not np.isnan(si):
                        si_list.append(si)
                    
                    # Store LVET in seconds
                    lvet_list.append(delta_t)
            except Exception as e:
                pass 
                
        # Aggregate Beat Features
        features['CT'] = float(np.mean(ct_list)) if ct_list else 0.0
        features['RI'] = float(np.mean(ri_list)) if ri_list else 0.0
        features['SI'] = float(np.mean(si_list)) if si_list else 0.0
        features['dpdt_max'] = float(np.mean(dpdt_max_list)) if dpdt_max_list else 0.0
        
        avg_lvet = np.mean(lvet_list) if lvet_list else 0.3
        
        # We need average LVET for SEVR calculation
        sevr_list, asys_list, adia_list = [], [], []
        for i in range(len(systolic_peaks) - 1):
             sys_idx = systolic_peaks[i]
             next_sys_idx = systolic_peaks[i+1]
             beat_signal = ppg_signal[sys_idx:next_sys_idx]
             
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
                 
        features['AGI_mod'] = float(np.mean(agi_mod_list)) if agi_mod_list else 0.0
        
        # Note: training DB converts LVET to ms for the feature array, so we multiply by 1000
        features['LVET'] = float(avg_lvet * 1000.0) 
        
        features['PPG_SEVR'] = float(np.mean(sevr_list)) if sevr_list else 0.0
        features['PPG_Asys'] = float(np.mean(asys_list)) if asys_list else 0.0
        features['PPG_Adia'] = float(np.mean(adia_list)) if adia_list else 0.0
        
        features['PAT'] = float(pat_ms) if pat_ms is not None else 150.0 
        
        return features

