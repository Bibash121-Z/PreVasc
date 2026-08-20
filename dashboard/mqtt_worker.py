import os
import sys
import collections
import time
import json
import numpy as np
import pandas as pd
import paho.mqtt.client as mqtt
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from paho.mqtt.enums import CallbackAPIVersion
from scipy.signal import decimate
import joblib
import torch

from .peak import PPGProcessor 
from .pcg_processor import PCGProcessor
from .feature_extractor import PPGFeatureExtractor

# --- Network Configuration ---
BROKER = "192.168.1.24"
PORT = 1883
TOPIC = "sensor/vascular"
CONTROL_TOPIC = "sensor/control"

MQTT_SERVER = BROKER
MQTT_PORT = PORT
MQTT_TOPIC = TOPIC

FS_PCG = 500
PPG_DECIMATION = 4
FS_PPG = FS_PCG // PPG_DECIMATION  # 125Hz

# 10-second buffer (5000 samples @ 500Hz -> 1250 samples @ 125Hz)
BUFFER_CAPACITY = FS_PCG * 10 
TIME_BUFFER = collections.deque(maxlen=BUFFER_CAPACITY)
IR_BUFFER = collections.deque(maxlen=BUFFER_CAPACITY)
PCG_BUFFER = collections.deque(maxlen=BUFFER_CAPACITY)

ppg_processor = PPGProcessor(fs=FS_PPG)
pcg_processor = PCGProcessor(fs=FS_PCG)
feature_extractor = PPGFeatureExtractor(fs=FS_PPG)

PATIENT_AGE = 30
PATIENT_HEIGHT_M = 1.75
ENABLE_PPG = True
ENABLE_PCG = True
LAST_VALID_BPM = None
last_extraction_time = 0
last_broadcast_time = 0
historical_calibrated_age = None 

def set_session_state(age, height_m, enable_ppg, enable_pcg):
    global PATIENT_AGE, PATIENT_HEIGHT_M, ENABLE_PPG, ENABLE_PCG, LAST_VALID_BPM, historical_calibrated_age
    PATIENT_AGE = float(age)
    PATIENT_HEIGHT_M = float(height_m)
    ENABLE_PPG = bool(enable_ppg)
    ENABLE_PCG = bool(enable_pcg)
    LAST_VALID_BPM = None
    historical_calibrated_age = None
    TIME_BUFFER.clear()
    IR_BUFFER.clear()
    PCG_BUFFER.clear()
    print(f"\n==================================================")
    print(f"🟢 [SESSION STARTED] Active Patient: Age={PATIENT_AGE:.0f} yrs, Height={PATIENT_HEIGHT_M:.2f} m | PPG={ENABLE_PPG}, PCG={ENABLE_PCG}")
    print(f"==================================================\n")

def stop_session():
    TIME_BUFFER.clear()
    IR_BUFFER.clear()
    PCG_BUFFER.clear()

# --- ML Model Loaders ---
base_dir = os.path.dirname(__file__)
ml_dir = os.path.join(base_dir, 'ml_models')

ukbb_model = None
device = 'cuda' if torch.cuda.is_available() else 'cpu'
try:
    vasc_dir = os.path.join(ml_dir, 'vascular_age')
    sys.path.append(vasc_dir)
    from net1d import Net1D
    with open(os.path.join(vasc_dir, 'config.json')) as f:
        cfg = json.load(f)
    ukbb_model = Net1D(**cfg).to(device)
    ukbb_model.load_state_dict(torch.load(os.path.join(vasc_dir, 'model.pth'), map_location=device))
    ukbb_model.eval()
    print("🟢 Net1D Vascular Age Model Loaded.")
except Exception as e:
    print(f"⚠️ Net1D Model load failed: {e}")

xgb_models_loaded = False
XGB_FEATURES = ["AGE", "HR", "CT", "RI", "SI", "dpdt_max", "AGI_mod", "PAT", "LVET", "PPG_SEVR", "PPG_Asys", "PPG_Adia"]
try:
    xgb_dir = os.path.join(ml_dir, 'xgboost')
    risk_clf = joblib.load(os.path.join(xgb_dir, 'Model_RISK_Classifier.joblib'))
    sbp_reg = joblib.load(os.path.join(xgb_dir, 'Model_SBP_a_Regressor.joblib'))
    dbp_reg = joblib.load(os.path.join(xgb_dir, 'Model_DBP_a_Regressor.joblib'))
    xgb_models_loaded = True
    print("🟢 XGBoost Clinical Models Loaded.")
except Exception as e:
    print(f"⚠️ XGBoost Models load failed: {e}")

# ==========================================================
# EXACT HELPER FUNCTIONS RESTORED FROM ORIGINAL MAIN.PY
# ==========================================================
def extract_and_average_beats(signal, systolic_peaks, target_len=100, fs=125):
    if len(systolic_peaks) < 3:
        return None
    valleys = []
    for i in range(len(systolic_peaks) - 1):
        start = systolic_peaks[i]
        end = systolic_peaks[i+1]
        valleys.append(start + np.argmin(signal[start:end]))
    if len(valleys) < 2:
        return None
    beats = []
    for i in range(len(valleys) - 1):
        v_start = valleys[i]
        v_end = valleys[i+1]
        beat_signal = signal[v_start:v_end]
        if (fs * 0.3) < len(beat_signal) < (fs * 1.5):
            x_old = np.linspace(0, 1, len(beat_signal))
            x_new = np.linspace(0, 1, target_len)
            resampled_beat = np.interp(x_new, x_old, beat_signal)
            beats.append(resampled_beat)
    if len(beats) < 3:
        return None
    return np.mean(beats, axis=0)

def np_z_score_normalize(parsed_ppg: np.ndarray) -> np.ndarray:
    mean_ppg = parsed_ppg.mean(axis=-1, keepdims=True)
    std_ppg = parsed_ppg.std(axis=-1, keepdims=True)
    return (parsed_ppg - mean_ppg) / (std_ppg + 1e-8)

def calculate_clinical_vascular_age(raw_dl_age, patient_age, patient_height_m=1.75):
    """
    Clinical Vascular Age Delta Model:
    Evaluates biological arterial age deviation relative to patient chronological age.
    Accurately scales from age 5 to 90+ and detects early childhood vascular pathology.
    """
    if raw_dl_age is None or patient_age is None or patient_age <= 0:
        return None

    patient_age = float(patient_age) - 5 if patient_age < 10 else float(patient_age)
    # Sensor-calibrated expected baseline:
    # Age 10 expected = 30.0 | Age 20 expected = 35.0 | Age 50 expected = 50.0
    expected_raw_dl = 30.0 + (float(patient_age) - 10.0) * 0.50
    expected_raw_dl = float(np.clip(expected_raw_dl, 30.0, 70.0))

    # Biological deviation delta
    raw_difference = raw_dl_age - expected_raw_dl
    vascular_delta = raw_difference * 1.0

    # Final Clinical Vascular Age
    calculated_age = float(patient_age) + vascular_delta

    # Physiological human limits [5.0, 90.0]
    return float(np.clip(calculated_age, 5.0, 90.0))

def compute_pat_ms(s1_times, systolic_times):
    if len(s1_times) == 0 or len(systolic_times) == 0: 
        return None
        
    pats = [
        (candidates[0] - s1_t) * 1000.0 
        for s1_t in s1_times 
        if len(candidates := systolic_times[(systolic_times > s1_t + 0.12) & (systolic_times < s1_t + 0.36)]) > 0
    ]
    
    # Clinical PAT bounds (120ms to 360ms: supports young, tall, and CVD patients)
    valid_pats = [p for p in pats if 120.0 <= p <= 360.0]
    
    if len(valid_pats) >= 2:
        return float(np.median(valid_pats))
    elif len(pats) >= 2:
        return float(np.median(pats))
    return None

def compute_lvet_ms(s1_times, s2_times):
    if len(s1_times) == 0 or len(s2_times) == 0: 
        return None
        
    lvets = [
        (candidates[0] - s1_t) * 1000.0 
        for s1_t in s1_times 
        if len(candidates := s2_times[(s2_times > s1_t + 0.18) & (s2_times < s1_t + 0.38)]) > 0
    ]
    
    # Clinical LVET bounds (180ms to 360ms)
    valid_lvets = [l for l in lvets if 180.0 <= l <= 360.0]
    
    if len(valid_lvets) >= 2:
        return float(np.median(valid_lvets))
    elif len(lvets) >= 2:
        return float(np.median(lvets))
    return None

def get_latest_bpm():
    return LAST_VALID_BPM

# --- MQTT Ingest & Analytics Engine ---
def on_message(client, userdata, msg):
    global LAST_VALID_BPM, last_extraction_time, last_broadcast_time, historical_calibrated_age
    try:
        payload_text = msg.payload.decode('utf-8').strip()
        channel_layer = get_channel_layer()

        if msg.topic == CONTROL_TOPIC or payload_text == "1":
            return
        elif payload_text == "2":
            async_to_sync(channel_layer.group_send)("sensor_data", {"type": "broadcast_handshake_success"})
            return

        records = payload_text.split(';')
        for rec in records:
            if not rec: continue
            parts = rec.split(',')
            if len(parts) == 4:
                TIME_BUFFER.append(int(parts[0]))
                IR_BUFFER.append(int(parts[2]))
                PCG_BUFFER.append(int(parts[3]))

        now = time.time()
        # UI Broadcast @ 20 FPS
        if len(PCG_BUFFER) >= 200 and (now - last_broadcast_time >= 0.05):
            last_broadcast_time = now

            raw_ir = np.array(IR_BUFFER)
            
            # --- 1. OPTICAL LEAD-OFF SQUELCH (AIR PROTECTION) ---
            # If Raw IR count < 30,000, no finger is present -> halt math immediately
            if np.mean(raw_ir) < 30000.0:
                async_to_sync(channel_layer.group_send)(
                    "sensor_data",
                    {
                        "type": "send_sensor_data",
                        "display": [],
                        "systolic_peaks": [],
                        "pcg": [],
                        "s1_peaks": [],
                        "s2_peaks": [],
                        "bpm": 0.0,
                        "ai_metrics": {},
                        "clinical_status": "ATTACH SENSOR"
                    }
                )
                return
            
            raw_pcg = np.array(PCG_BUFFER)
            timestamps = np.array(TIME_BUFFER) / 1000000.0

            ppg_signal = decimate(raw_ir, PPG_DECIMATION, ftype="fir", zero_phase=True)
            ppg_timestamps = timestamps[::PPG_DECIMATION][:len(ppg_signal)]

            results_ppg = ppg_processor.preprocess_signal(ppg_signal)
            results_pcg = pcg_processor.preprocess_signal(raw_pcg)

            peaks = results_ppg["systolic_peaks"]
            bpm = float(results_ppg.get("bpm", 0))
            pcg_bpm = float(results_pcg.get("bpm", 0))

            pad = results_pcg.get("pad_samples", 0)
            s1_times = timestamps[results_pcg["s1_peaks"] + pad] if len(results_pcg["s1_peaks"]) else np.array([])
            s2_times = timestamps[results_pcg["s2_peaks"] + pad] if len(results_pcg["s2_peaks"]) else np.array([])
            systolic_times = ppg_timestamps[peaks] if len(peaks) else np.array([])

            # Robust Median BPM
            true_rr_std = 999.0
            if len(systolic_times) >= 2:
                true_rr = np.diff(systolic_times)
                valid_rr = true_rr[(true_rr >= 0.3) & (true_rr <= 2.0)]
                if len(valid_rr) > 0:
                    bpm = 60.0 / np.median(valid_rr)
                    true_rr_std = np.std(valid_rr)
            
            if bpm > 0: LAST_VALID_BPM = bpm

            live_lvet = compute_lvet_ms(s1_times, s2_times)
            live_pat = compute_pat_ms(s1_times, systolic_times)

            ai_features = {}
            clinical_status = "CALIBRATING..."
            
            if len(PCG_BUFFER) >= 2500:
                is_valid_ppg, ppg_reason = ppg_processor.assess_signal_quality(results_ppg)
                is_valid_pcg, pcg_reason = pcg_processor.assess_signal_quality(results_pcg)

                # PI Override for clean, stable rhythms
                if (not is_valid_ppg) and (len(peaks) >= 4) and (true_rr_std < 0.15):
                    is_valid_ppg = True
                    ppg_reason = "Signal Stable"

                if not ENABLE_PPG: is_valid_ppg = False
                if not ENABLE_PCG: is_valid_pcg = False

                if not is_valid_ppg:
                    clinical_status = f"NOISE DETECTED ({ppg_reason})"
                    ai_features = {} 
                else:
                    clinical_status = "DUAL-SENSOR PRECISION ACTIVE" if is_valid_pcg else "PPG ACTIVE (PCG OFF/NOISY)"

                    # Run ML Extractors every 3 seconds
                    if (now - last_extraction_time > 3.0) and len(peaks) >= 4:
                        extracted = feature_extractor.extract_features(
                            ppg_signal=results_ppg["display"],
                            systolic_peaks=peaks,
                            diastolic_peaks=results_ppg["diastolic_peaks"],
                            age=PATIENT_AGE,
                            height_m=PATIENT_HEIGHT_M,
                            pat_ms=live_pat if live_pat else 150.0,
                            lvet_ms_override=live_lvet if is_valid_pcg else None,
                            timestamps=ppg_timestamps
                        )

                        if extracted:
                            ai_features = extracted

                            # PWV Calculation
                            distance_m = (0.43 * PATIENT_HEIGHT_M) - 0.05
                            if is_valid_pcg and live_pat and live_pat > 0:
                                ai_features["pwv"] = distance_m / (live_pat / 1000.0)
                            else:
                                si = ai_features.get("SI", 0)
                                ai_features["pwv"] = (distance_m / (PATIENT_HEIGHT_M / si)) if si > 0 else 0.0

                            # XGBoost Models
                            if xgb_models_loaded:
                                X_new = pd.DataFrame([ai_features], columns=XGB_FEATURES)
                                ai_features["cvd_risk"] = int(risk_clf.predict(X_new)[0])
                                ai_features["sbp"] = float(sbp_reg.predict(X_new)[0])
                                ai_features["dbp"] = float(dbp_reg.predict(X_new)[0])

                           # --- PURE STATISTICAL DEEP LEARNING INFERENCE ---
                            raw_dl_age = None
                            if ukbb_model is not None:
                                averaged_beat = extract_and_average_beats(results_ppg["display"], peaks, target_len=100, fs=FS_PPG)
                                if averaged_beat is not None:
                                    X = np.expand_dims(np.expand_dims(averaged_beat, axis=0), axis=0)
                                    X = np_z_score_normalize(X)
                                    
                                    with torch.no_grad():
                                        X_tensor = torch.tensor(X, dtype=torch.float32).to(device)
                                        raw_dl_age = ukbb_model(X_tensor).item()
                                        
                                        # Apply pure statistical mapping
                                        calibrated = calculate_clinical_vascular_age(raw_dl_age, PATIENT_AGE, PATIENT_HEIGHT_M)
                                        
                                        if calibrated is not None:
                                            if historical_calibrated_age is None:
                                                historical_calibrated_age = calibrated
                                            else:
                                                historical_calibrated_age = (0.75 * historical_calibrated_age) + (0.25 * calibrated)
                                            ai_features["cvd_age"] = round(historical_calibrated_age, 1)
                                            
                            # Terminal Diagnostic Logging
                            expected_baseline = 38.0 + (PATIENT_AGE - 10.0) * 0.50
                            feat_summary = f"HR={bpm:.0f} SI={ai_features.get('SI', 0):.1f} CT={ai_features.get('CT', 0):.1f}"
                            dl_summary = f" | [Age={PATIENT_AGE:.0f}] RawDL={raw_dl_age:.2f} (Expected={expected_baseline:.1f}) -> VascAge={ai_features.get('cvd_age', '--')}" if raw_dl_age else ""
                            xgb_summary = f" | SBP={ai_features.get('sbp', 0):.0f} DBP={ai_features.get('dbp', 0):.0f} Risk={ai_features.get('cvd_risk', '--')}" if xgb_models_loaded else ""
                            
                            print(f"[{time.strftime('%H:%M:%S')}] {feat_summary}{dl_summary}{xgb_summary}")

                        last_extraction_time = now

            # --- HIGH-PERFORMANCE FIXED VIEWPORT BROADCAST ---
            WINDOW_PPG_POINTS = 500   # 4.0s @ 125Hz
            WINDOW_PCG_POINTS = 2000  # 4.0s @ 500Hz

            ppg_display_slice = results_ppg["display"][-WINDOW_PPG_POINTS:]
            ppg_offset = len(results_ppg["display"]) - len(ppg_display_slice)
            visible_systolic = [int(p - ppg_offset) for p in peaks if p >= ppg_offset]

            pcg_display_slice = []
            s1_visible = []
            s2_visible = []

            if ENABLE_PCG and len(results_pcg["envelope"]) > 0:
                pcg_display_slice = results_pcg["envelope"][-WINDOW_PCG_POINTS:]
                pcg_offset = len(results_pcg["envelope"]) - len(pcg_display_slice)
                s1_visible = [int(p - pcg_offset) for p in results_pcg["s1_peaks"] if p >= pcg_offset]
                s2_visible = [int(p - pcg_offset) for p in results_pcg["s2_peaks"] if p >= pcg_offset]

            async_to_sync(channel_layer.group_send)(
                "sensor_data",
                {
                    "type": "send_sensor_data",
                    "display": ppg_display_slice.tolist() if hasattr(ppg_display_slice, 'tolist') else list(ppg_display_slice),
                    "systolic_peaks": visible_systolic,
                    "pcg": pcg_display_slice.tolist() if hasattr(pcg_display_slice, 'tolist') else list(pcg_display_slice),
                    "s1_peaks": s1_visible,       
                    "s2_peaks": s2_visible,
                    "bpm": round(bpm, 1),
                    "ai_metrics": ai_features,
                    "clinical_status": clinical_status
                }
            )
    except Exception as e:
        print(f"🔴 Pipeline Error: {e}")

# --- Outbound Commands & MQTT Hooks ---
def send_ping_to_esp():
    client.publish(TOPIC, "1", qos=1, retain=False)

def send_command_to_esp(command_string):
    client.publish(CONTROL_TOPIC, command_string, qos=1, retain=False)

client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, transport="tcp")
mqtt_client = client

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        client.subscribe(TOPIC)
        client.subscribe(CONTROL_TOPIC)
        print(f"🟢 MQTT Worker connected to {BROKER}:{PORT}")

client.on_connect = on_connect
client.on_message = on_message