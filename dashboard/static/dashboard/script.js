// ==========================================
// Global State & Render Frame Caches
// ==========================================
let socket = null;
let handshakeTimeout = null;

// Dual Trace Render Frame Caches
let displaySignalArray = [];     // PPG Data
let systolicPeakIndices = [];    // PPG Peaks
let pcgSignalArray = [];         // PCG Data (Sound Envelope)
let s1PeakIndices = [];          // PCG S1 (Lub)
let s2PeakIndices = [];          // PCG S2 (Dub)
let latestLiveBpm = null;        // Latest valid BPM
let latestAiMetrics = {};        // Caches AI features for DB saving
let currentPatientData = null;   // Last searched patient payload
let detailsTabUnlocked = false;  // Controls visibility of Details navbar item

// Canvas Engine References
let ppgCanvas = null;
let ppgCtx = null;
let pcgCanvas = null;
let pcgCtx = null;

// Timer state variables
let timerInterval = null;
let totalSeconds = 0;

// Helper function to format seconds into HH:MM:SS
function formatTime(seconds) {
  const hrs = String(Math.floor(seconds / 3600)).padStart(2, '0');
  const mins = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
  const secs = String(seconds % 60).padStart(2, '0');
  return `${hrs}:${mins}:${secs}`;
}

function startTimer() {
  if (timerInterval !== null) return;
  const timerDisplay = document.getElementById("session-timer");
  timerInterval = setInterval(() => {
    totalSeconds++;
    if (timerDisplay) timerDisplay.textContent = formatTime(totalSeconds);
  }, 1000);
}

function stopTimer() {
  if (timerInterval !== null) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

function resetTimer() {
  stopTimer();
  totalSeconds = 0;
  const timerDisplay = document.getElementById("session-timer");
  if (timerDisplay) timerDisplay.textContent = "00:00:00";
}

function switchMainNavPage(pageName) {
  const dashboardWrapper = document.getElementById("dashboard-wrapper");
  const homeSection = document.getElementById("home-dashboard-section");
  const patientDataPage = document.getElementById("patient-data-page");
  const homeNavBtn = document.getElementById("nav-home");
  const patientNavBtn = document.getElementById("nav-patient-data");
  const detailsNavBtn = document.getElementById("nav-details");

  const showDetails = pageName === "details";
  const showSearchPanel = pageName === "patient-search";

  if (detailsNavBtn) {
    detailsNavBtn.classList.toggle("hidden", !detailsTabUnlocked);
  }

  if (dashboardWrapper) {
    dashboardWrapper.classList.toggle("show-patient-panel", showSearchPanel);
  }
  if (homeSection) homeSection.classList.toggle("hidden", showDetails);
  if (patientDataPage) patientDataPage.classList.toggle("hidden", !showDetails);
  if (homeNavBtn) homeNavBtn.classList.toggle("active", pageName === "home");
  if (patientNavBtn) patientNavBtn.classList.toggle("active", pageName === "patient-search");
  if (detailsNavBtn) detailsNavBtn.classList.toggle("active", showDetails);
}

function renderPatientHistoryTable(patient) {
  const historyTableBody = document.getElementById("table-history-body");
  if (!historyTableBody) return;

  const followups = Array.isArray(patient?.followups) ? patient.followups : [];
  
  if (followups.length === 0) {
    historyTableBody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align: center; color: #64748b; font-style: italic;">
          No historical diagnostic sessions recorded yet.
        </td>
      </tr>
    `;
    return;
  }

  historyTableBody.innerHTML = followups.map((row) => {
    const bpmDisplay = row.hr !== "--" ? `${row.hr} BPM` : "-- BPM";
    const cardioRisk = row.cvd_risk || "--";
    const isHigh = cardioRisk.includes("HIGH");
    const riskBadge = cardioRisk !== "--" 
        ? `<span class="badge" style="background: ${isHigh ? '#fee2e2' : '#dcfce7'}; color: ${isHigh ? '#b91c1c' : '#15803d'}; padding: 4px 8px; border-radius: 4px; font-weight: 600;">${cardioRisk}</span>`
        : `--`;

    const bpDisplay = (row.sbp !== "--" && row.dbp !== "--" && row.sbp !== null) 
        ? `${row.sbp}/${row.dbp}` 
        : "--/--";

    return `
      <tr>
        <td><strong>${patient.id || "--"}</strong> <small style="color: #64748b; display: block;">${row.date}</small></td>
        <td style="color: #0284c7; font-weight: bold;">${bpmDisplay}</td>
        <td>${riskBadge}</td>
        <td>${bpDisplay}</td>
      </tr>
    `;
  }).join("");
}

function renderPatientDataReport(patient) {
  const idEl = document.getElementById("report-id");
  const nameEl = document.getElementById("report-name");
  const phoneEl = document.getElementById("report-phone");
  const ageEl = document.getElementById("report-age");
  const heightEl = document.getElementById("report-height");
  const registeredEl = document.getElementById("report-registered");
  const featureBody = document.getElementById("table-feature-body");

  if (idEl) idEl.innerText = patient?.id || "--";
  if (nameEl) nameEl.innerText = patient?.name || "--";
  if (phoneEl) phoneEl.innerText = patient?.phone_no || "--";
  if (ageEl) ageEl.innerText = patient?.age ?? "--";
  if (heightEl) heightEl.innerText = patient?.height ? `${patient.height} cm` : "--";
  if (registeredEl) registeredEl.innerText = patient?.registered_at || "--";

  if (!featureBody) return;
  const rows = Array.isArray(patient?.followups) ? patient.followups : [];
  if (!rows.length) {
    featureBody.innerHTML = `
      <tr>
        <td colspan="17" style="text-align: center; color: #64748b; font-style: italic;">
          No follow-up records yet. Save a session to add the first feature row.
        </td>
      </tr>
    `;
    return;
  }

  featureBody.innerHTML = rows.map((row) => `
    <tr>
      <td>${row.date || "--"}</td>
      <td class="feature-main">${row.hr ?? "--"}</td>
      <td class="feature-main">${row.sbp ?? "--"}</td>
      <td class="feature-main">${row.dbp ?? "--"}</td>
      <td class="feature-main">${row.si ?? "--"}</td>
      <td class="feature-main">${row.cvd_risk ?? "--"}</td>
      <td class="feature-main">${row.cvd_age ?? "--"}</td>
      <td class="feature-main">${row.pwv ?? "--"}</td>
      <td>${row.ct ?? "--"}</td>
      <td>${row.ri ?? "--"}</td>
      <td>${row.dpdt_max ?? "--"}</td>
      <td>${row.agi_mod ?? "--"}</td>
      <td>${row.lvet ?? "--"}</td>
      <td>${row.ppg_sevr ?? "--"}</td>
      <td>${row.ppg_asys ?? "--"}</td>
      <td>${row.ppg_adia ?? "--"}</td>
      <td>${row.pat ?? "--"}</td>
    </tr>
  `).join("");
}

async function loadNextPatientId() {
  try {
    const response = await fetch("/api/next-patient-id/");
    if (!response.ok) throw new Error("API Route Missing");
    const data = await response.json();
    const pidInput = document.getElementById("p-id");
    if (pidInput) pidInput.value = `PT-${data.next_id}`;
  } catch (err) {
    const pidInput = document.getElementById("p-id");
    if (pidInput) pidInput.value = "PT-1";
  }
}

// ==========================================
// Canvas Auto-Resizer & Engine Setup
// ==========================================
function resizeCanvases() {
  [
    { cvs: ppgCanvas, ctx: ppgCtx },
    { cvs: pcgCanvas, ctx: pcgCtx }
  ].forEach(({ cvs, ctx }) => {
    if (!cvs || !ctx) return;
    const rect = cvs.parentElement.getBoundingClientRect();
    cvs.width = rect.width * window.devicePixelRatio;
    cvs.height = rect.height * window.devicePixelRatio;
    cvs.style.width = "100%";
    cvs.style.height = "100%";
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  });
}

// ==========================================
// Fixed Time-Window Rendering Engine
// ==========================================
function renderChannel(canvasObj, contextObj, signalData, traceColor, maxWindowPoints, drawPeaks = false, primaryPeaks = [], secondaryPeaks = []) {
  if (!canvasObj || !contextObj) return;

  const width = canvasObj.width / window.devicePixelRatio;
  const height = canvasObj.height / window.devicePixelRatio;
  contextObj.clearRect(0, 0, width, height);

  // Subtle Grid
  contextObj.strokeStyle = "rgba(100, 116, 139, 0.15)";
  contextObj.lineWidth = 1;
  contextObj.beginPath();
  for (let x = 0; x < width; x += 40) { contextObj.moveTo(x, 0); contextObj.lineTo(x, height); }
  for (let y = 0; y < height; y += 40) { contextObj.moveTo(0, y); contextObj.lineTo(width, y); }
  contextObj.stroke();

  const pointsCount = signalData ? signalData.length : 0;
  if (pointsCount < 2) return;

  // Extract valid finite numbers
  let min = Infinity;
  let max = -Infinity;
  const valid = [];

  for (let i = 0; i < pointsCount; i++) {
    const v = Number(signalData[i]);
    if (Number.isFinite(v)) {
      if (v < min) min = v;
      if (v > max) max = v;
      valid.push({ idx: i, val: v });
    }
  }

  if (valid.length < 2) return;
  if (min === max) { min -= 1.0; max += 1.0; }
  const range = max - min;

  // Fixed 4.0s Camera: locks horizontal scaling across screen
  const safeWindow = Math.max(maxWindowPoints, pointsCount);
  const xScale = width / (safeWindow - 1);
  const yScale = (height - 40) / range;
  const yOffset = height - 20;

  // Draw Waveform Trace
  contextObj.beginPath();
  contextObj.lineWidth = 2.2;
  contextObj.strokeStyle = traceColor;
  contextObj.lineJoin = "round";

  let first = true;
  for (let p of valid) {
    const px = p.idx * xScale;
    const py = yOffset - ((p.val - min) * yScale);
    if (first) {
      contextObj.moveTo(px, py);
      first = false;
    } else {
      contextObj.lineTo(px, py);
    }
  }
  contextObj.stroke();

  // Draw Peak Markers with White Border
  const drawDots = (indices, color) => {
    if (!indices || indices.length === 0) return;
    for (let k = 0; k < indices.length; k++) {
      const pIdx = Number(indices[k]);
      if (Number.isFinite(pIdx) && pIdx >= 0 && pIdx < pointsCount) {
        const val = Number(signalData[pIdx]);
        if (Number.isFinite(val)) {
          const px = pIdx * xScale;
          const py = yOffset - ((val - min) * yScale);
          contextObj.beginPath();
          contextObj.arc(px, py, 5.0, 0, 6.2831853);
          contextObj.fillStyle = color;
          contextObj.fill();
          contextObj.lineWidth = 1.5;
          contextObj.strokeStyle = "#ffffff";
          contextObj.stroke();
        }
      }
    }
  };

  if (drawPeaks) {
    const primaryColor = traceColor === "#ef4444" ? "#22c55e" : "#f43f5e";
    drawDots(primaryPeaks, primaryColor);
    drawDots(secondaryPeaks, "#a855f7");
  }
}

function drawWaveforms() {
  requestAnimationFrame(drawWaveforms);

  if (ppgCanvas && ppgCtx) {
    // 500 points = exactly 4.0s @ 125Hz (Blue PPG with Pink Systolic dots)
    renderChannel(ppgCanvas, ppgCtx, displaySignalArray, "#38bdf8", 500, true, systolicPeakIndices, []);
  }

  if (pcgCanvas && pcgCtx) {
    // 2000 points = exactly 4.0s @ 500Hz (Red PCG Envelope with Green S1 and Purple S2 dots)
    renderChannel(pcgCanvas, pcgCtx, pcgSignalArray, "#ef4444", 2000, true, s1PeakIndices, s2PeakIndices);
  }
}

// ==========================================
// Master DOMContentLoaded Initializer
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  console.log("⚙️ PreVasc Master UI Initializing...");

  // 1. Initialize Navbar Navigation
  const homeNavBtn = document.getElementById("nav-home");
  const patientNavBtn = document.getElementById("nav-patient-data");
  const detailsNavBtn = document.getElementById("nav-details");

  switchMainNavPage("home");

  if (patientNavBtn) {
    patientNavBtn.onclick = (e) => {
      e.preventDefault();
      switchMainNavPage("patient-search");
    };
  }

  if (detailsNavBtn) {
    detailsNavBtn.onclick = (e) => {
      e.preventDefault();
      if (!detailsTabUnlocked || !currentPatientData) {
        alert("Search a patient and click Show Patient Data to open Details.");
        return;
      }
      renderPatientDataReport(currentPatientData);
      switchMainNavPage("details");
    };
  }

  if (homeNavBtn) {
    homeNavBtn.onclick = (e) => {
      e.preventDefault();
      switchMainNavPage("home");
    };
  }

  // 2. Patient Data Reports Sub-Navigation
  const showDataBtn = document.getElementById("btn-show-patient-data");
  const exitDetailsBtn = document.getElementById("btn-exit-details");

  if (showDataBtn) {
    showDataBtn.onclick = () => {
      if (!currentPatientData) {
        alert("Search a patient first, then click Show Patient Data.");
        return;
      }
      detailsTabUnlocked = true;
      renderPatientDataReport(currentPatientData);
      switchMainNavPage("details");
    };
  }

  if (exitDetailsBtn) {
    exitDetailsBtn.onclick = () => {
      detailsTabUnlocked = false;
      switchMainNavPage("home");
      const patientDataPage = document.getElementById("patient-data-page");
      if (patientDataPage) patientDataPage.classList.add("hidden");
    };
  }

  // 3. WebSocket Setup
  const connectBtn = document.getElementById("hardware-connect-btn");
  const wsScheme = window.location.protocol === "https:" ? "wss://" : "ws://";
  socket = new WebSocket(wsScheme + window.location.host + "/ws/sensor_data/");

  socket.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);

      const updateBtnText = (text) => {
        if (!connectBtn) return;
        const textEl = connectBtn.querySelector(".btn-text") || connectBtn;
        textEl.innerText = text;
      };

      if (data.type === "broadcast_handshake_success") {
        clearTimeout(handshakeTimeout);
        if (connectBtn) {
          connectBtn.className = "connect-btn status-connected";
          updateBtnText("ESP32 Connected");
        }
        return;
      }

      if (data.type === "sensor_stream" || data.type === "send_sensor_data") {
        if (connectBtn && !connectBtn.classList.contains("status-connected")) {
          clearTimeout(handshakeTimeout);
          connectBtn.className = "connect-btn status-connected";
          updateBtnText("ESP32 Connected");
        }

        const bufferIndicator = document.getElementById("ppg-buffer-indicator");
        if (bufferIndicator) bufferIndicator.style.display = "none";

        // Update Heart Rate
        const currentBpm = data.bpm || 0.0;
        const bpmText = document.getElementById("hr-val");
        if (bpmText) bpmText.innerText = currentBpm > 0 ? Math.round(currentBpm) : "--";
        if (Number.isFinite(Number(currentBpm)) && Number(currentBpm) > 0) {
          latestLiveBpm = Number(currentBpm);
        }

        // Cache waveform buffers for canvas rendering
        displaySignalArray = data.display || [];
        systolicPeakIndices = data.systolic_peaks || [];
        pcgSignalArray = data.pcg || [];
        s1PeakIndices = data.s1_peaks || [];
        s2PeakIndices = data.s2_peaks || [];
        
        // Update Clinical Status Badge
        const statusBadge = document.getElementById("clinical-status-badge");
        let isNoise = false;
        
        if (statusBadge && data.clinical_status) {
            statusBadge.innerText = data.clinical_status;
            if (data.clinical_status.includes("DUAL")) {
                statusBadge.style.backgroundColor = "#15803d"; // Green (Both sensors active)
            } else if (data.clinical_status.includes("PPG ACTIVE")) {
                statusBadge.style.backgroundColor = "#0284c7"; // Blue (Finger pulse active)
            } else {
                statusBadge.style.backgroundColor = "#f59e0b"; // Orange (Attach sensor)
                isNoise = true; 
            }
        }

        // Update Diagnostic Metrics
        if (data.ai_metrics && Object.keys(data.ai_metrics).length > 0) {
          latestAiMetrics = data.ai_metrics;

          const bpText = document.getElementById("bp-val");
          if (bpText && latestAiMetrics.sbp && latestAiMetrics.dbp) {
            bpText.innerText = `${Math.round(latestAiMetrics.sbp)}/${Math.round(latestAiMetrics.dbp)}`;
          }

          const vascAgeText = document.getElementById("vasc-age-val");
          if (vascAgeText && latestAiMetrics.cvd_age) {
            vascAgeText.innerText = latestAiMetrics.cvd_age.toFixed(1);
          }

          const pwvText = document.getElementById("pwv-val");
          if (pwvText && latestAiMetrics.pwv) {
            pwvText.innerText = latestAiMetrics.pwv.toFixed(2);
          }

          const riskBadge = document.getElementById("cvd-risk-val");
          if (riskBadge && latestAiMetrics.cvd_risk !== undefined) {
            const isHigh = latestAiMetrics.cvd_risk === 1;
            riskBadge.innerText = isHigh ? "HIGH RISK" : "LOW RISK";
            riskBadge.style.backgroundColor = isHigh ? "#fee2e2" : "#dcfce7";
            riskBadge.style.color = isHigh ? "#b91c1c" : "#15803d";
          }
          
        } else if (isNoise) {
          const bpText = document.getElementById("bp-val");
          if (bpText) bpText.innerText = "--/--";
          const vascAgeText = document.getElementById("vasc-age-val");
          if (vascAgeText) vascAgeText.innerText = "--";
          const pwvText = document.getElementById("pwv-val");
          if (pwvText) pwvText.innerText = "--";
          const riskBadge = document.getElementById("cvd-risk-val");
          if (riskBadge) {
              riskBadge.innerText = "--";
              riskBadge.style.backgroundColor = "transparent";
              riskBadge.style.color = "#1e293b";
          }
        }
      }
    } catch (err) {
      console.error("WS Parse Error:", err);
    }
  };

  if (connectBtn) {
    connectBtn.onclick = () => {
      const btnTextEl = connectBtn.querySelector(".btn-text") || connectBtn;
      if (connectBtn.classList.contains("status-disconnected") || (!connectBtn.classList.contains("status-searching") && !connectBtn.classList.contains("status-connected"))) {
        connectBtn.className = "connect-btn status-searching";
        btnTextEl.innerText = "Searching Device...";

        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ action: "connect_device" }));
        }

        handshakeTimeout = setTimeout(() => {
          if (connectBtn.classList.contains("status-searching")) {
            connectBtn.className = "connect-btn status-disconnected";
            btnTextEl.innerText = "Device Not Found";
            setTimeout(() => {
              if (connectBtn.classList.contains("status-disconnected") && btnTextEl.innerText === "Device Not Found") {
                btnTextEl.innerText = "Connect Device";
              }
            }, 2500);
          }
        }, 10000);
      } else {
        clearTimeout(handshakeTimeout);
        connectBtn.className = "connect-btn status-disconnected";
        btnTextEl.innerText = "Connect Device";
      }
    };
  }

  // 4. Capture Controls
  const startBtn = document.getElementById("start-btn");
  const stopBtn = document.getElementById("stop-btn");
  const resetBtn = document.getElementById("reset-btn");
  const saveBtn = document.getElementById("save-btn");

  if (startBtn) {
    startBtn.addEventListener("click", () => {
      let ageText = document.getElementById("p-age")?.value?.trim() || "";
      let heightText = document.getElementById("p-height")?.value?.trim() || "";

      if (!ageText) {
        const valAgeSex = document.getElementById("val-age-sex")?.innerText?.trim();
        if (valAgeSex) ageText = valAgeSex.split("/")[0].trim();
      }
      if (!heightText) {
        const valHeight = document.getElementById("val-height")?.innerText?.trim();
        if (valHeight) heightText = valHeight.replace(/\D/g, "");
      }

      const ageVal = parseFloat(ageText);
      const heightVal = parseFloat(heightText);

      if (isNaN(ageVal) || ageVal <= 0 || isNaN(heightVal) || heightVal <= 0) {
        alert("⚠️ Action Required:\nPlease enter a valid Patient Age and Height before starting capture!");
        const ageInput = document.getElementById("p-age");
        if (ageInput) ageInput.focus();
        return;
      }

      if (socket && socket.readyState === WebSocket.OPEN) {
        const height_m = heightVal > 3.0 ? heightVal / 100.0 : heightVal;
        const enablePpg = document.getElementById("toggle-ppg")?.checked ?? true;
        const enablePcg = document.getElementById("toggle-pcg")?.checked ?? true;

        console.log(`📡 Transmitting Session Configuration: Age=${ageVal}, Height=${height_m}m`);

        socket.send(JSON.stringify({ 
            action: 'start_capture',
            age: ageVal,
            height_m: height_m,
            enable_ppg: enablePpg,
            enable_pcg: enablePcg
        }));
        startTimer();
      } else {
        alert("WebSocket is not connected. Check server connection.");
      }
    });
  }

  if (stopBtn) {
    stopBtn.addEventListener("click", () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: 'stop_capture' }));
        stopTimer();
      }
    });
  }

  if (resetBtn) {
    resetBtn.addEventListener("click", () => resetTimer());
  }

  if (saveBtn) {
    saveBtn.addEventListener("click", () => {
      const patientId = document.getElementById("val-id")?.textContent?.trim() || document.getElementById("p-id")?.value?.trim() || "";
      if (!/\d+/.test(patientId)) {
        alert("Register or search a valid patient before saving.");
        return;
      }

      const liveHeartRate = Number(latestLiveBpm);
      if (!Number.isFinite(liveHeartRate) || liveHeartRate <= 0) {
        alert("No valid live heart rate available yet. Start capture and wait for BPM.");
        return;
      }

      fetch('/api/save-heart-rate/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
        },
        body: JSON.stringify({
          patient_id: patientId,
          heart_rate: liveHeartRate,
          features: latestAiMetrics
        })
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          alert(`✅ Saved Successfully!\n${data.message}`);
          const searchBtn = document.getElementById("btn-search-submit");
          if (searchBtn) searchBtn.click();
        } else {
          alert(`❌ Database error: ${data.error}`);
        }
      })
      .catch(err => console.error("Save Error:", err));
    });
  }

  // 5. Patient Registration Form
  const patientForm = document.getElementById("patient-registration-form");
  if (patientForm) {
    patientForm.onsubmit = async (e) => {
      e.preventDefault();
      try {
        const age = Number(document.getElementById("p-age")?.value);
        const height = Number(document.getElementById("p-height")?.value);

        if (isNaN(age) || age <= 0 || isNaN(height) || height <= 0) {
          alert("Please enter valid positive numbers for Age and Height.");
          return;
        }

        const res = await fetch("/api/save-patient/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: document.getElementById("p-name")?.value || "",
            phone_no: document.getElementById("p-phone")?.value || "",
            age: age,
            gender: document.getElementById("p-gender")?.value || "",
            height: height
          })
        });
        const result = await res.json();

        if (result.success) {
          ["p-name", "p-phone", "p-age", "p-gender", "p-height"].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.disabled = true;
          });
          const submitBtn = patientForm.querySelector('button[type="submit"]');
          if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerText = "Registered & Locked";
            submitBtn.style.backgroundColor = "#64748b";
          }
        } else {
          alert("Registration Error: " + result.error);
        }
      } catch (err) {
        console.error("Registration Error:", err);
      }
    };
  }

  // 6. Search Engine
  const searchBtn = document.getElementById("btn-search-submit");
  const searchInput = document.getElementById("txt-search-id");
  const profileCard = document.getElementById("patient-profile-card");

  if (searchBtn && searchInput) {
    searchBtn.onclick = async () => {
      const query = searchInput.value.trim();
      if (!query) return;

      try {
        const res = await fetch(`/api/search-patient/?id=${encodeURIComponent(query)}`);
        const result = await res.json();

        if (result.success && profileCard) {
          const patient = result.data;
          currentPatientData = patient;
          document.getElementById("val-id").innerText = patient.id;
          document.getElementById("val-name").innerText = patient.name;
          document.getElementById("val-phone").innerText = patient.phone_no || "--";
          document.getElementById("val-age-sex").innerText = `${patient.age} / ${patient.gender}`;
          document.getElementById("val-height").innerText = patient.height;
          document.getElementById("val-heart-rate").innerText = patient.heart_rate || "--";
          profileCard.style.display = "block";
          renderPatientHistoryTable(patient);
        } else {
          alert(result.error || "Patient not found.");
        }
      } catch (err) {
        console.error("Search Error:", err);
      }
    };
  }

  // 7. Delete Profile
  const deleteBtn = document.getElementById("btn-delete-profile");
  if (deleteBtn) {
    deleteBtn.onclick = async () => {
      const pId = document.getElementById("val-id")?.innerText;
      if (!pId) return;

      if (!confirm(`Are you sure you want to permanently delete ${pId}?`)) return;

      try {
        const res = await fetch("/api/delete-patient/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: pId })
        });
        const result = await res.json();
        if (result.success) {
          alert(result.message);
          location.reload();
        } else {
          alert("Error: " + result.error);
        }
      } catch (err) {
        console.error("Delete Error:", err);
      }
    };
  }

  // 8. Follow-up Button Override
  const followupBtn = document.getElementById("btn-followup-profile");
  if (followupBtn) {
    followupBtn.onclick = () => {
      const pId = document.getElementById("val-id").innerText.trim();
      const name = document.getElementById("val-name").innerText.trim();
      const phone = document.getElementById("val-phone")?.innerText.trim() || "";
      const ageSex = document.getElementById("val-age-sex").innerText.trim().split("/");
      const height = document.getElementById("val-height").innerText.trim();

      const inputId = document.getElementById("p-id");
      const inputName = document.getElementById("p-name");
      const inputPhone = document.getElementById("p-phone");
      const inputAge = document.getElementById("p-age");
      const selectGender = document.getElementById("p-gender");
      const inputHeight = document.getElementById("p-height");

      if (inputId) inputId.value = pId;
      if (inputName) { inputName.value = name; inputName.disabled = true; }
      if (inputPhone) { inputPhone.value = phone; inputPhone.disabled = true; }
      if (inputAge) { inputAge.value = ageSex[0]?.trim() || ""; inputAge.disabled = true; }
      if (selectGender) { selectGender.value = ageSex[1]?.trim().toLowerCase() || ""; selectGender.disabled = true; }
      if (inputHeight) { inputHeight.value = height.replace(/\D/g, ""); inputHeight.disabled = true; }

      const submitBtn = document.querySelector("#patient-registration-form button[type='submit']");
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = "Loaded for Follow-up";
        submitBtn.style.backgroundColor = "#64748b";
      }
    };
  }

  // 9. Initialize Canvases
  ppgCanvas = document.getElementById("ppgChart");
  pcgCanvas = document.getElementById("pcgChart");
  if (ppgCanvas) ppgCtx = ppgCanvas.getContext("2d");
  if (pcgCanvas) pcgCtx = pcgCanvas.getContext("2d");

  if (ppgCanvas || pcgCanvas) {
    window.addEventListener("resize", resizeCanvases);
    resizeCanvases();
    requestAnimationFrame(drawWaveforms);
  }

  // 10. Fetch Next Auto ID
  loadNextPatientId();
});