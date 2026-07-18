// ==========================================
// Global State & Render Frame Caches
// ==========================================
let socket = null;
let handshakeTimeout = null;

// Dual Trace Render Frame Caches
let displaySignalArray = [];     // PPG Data
let systolicPeakIndices = [];    // PPG Peaks
let pcgSignalArray = [];         // PCG Data (Sound)

// Canvas Engine References
let ppgCanvas = null;
let ppgCtx = null;
let pcgCanvas = null;
let pcgCtx = null;

// ==========================================
// Main Execution Engine - Defensively Guarded
// ==========================================
window.onload = function () {
  console.log("⚙️ PreVasc UI Init Engine Fired Successfully.");

  // ------------------------------------------
  // 1. Dashboard View Swapping (Navbar Logic)
  // ------------------------------------------
  (function initNavbar() {
    try {
      const homeNavBtn = document.getElementById("nav-home");
      const patientNavBtn = document.getElementById("nav-patient-data");
      const dashboardWrapper = document.getElementById("dashboard-wrapper");

      if (patientNavBtn && dashboardWrapper) {
        patientNavBtn.onclick = function (e) {
          e.preventDefault();
          dashboardWrapper.classList.add("show-patient-panel");
          if (homeNavBtn) homeNavBtn.classList.remove("active");
          patientNavBtn.classList.add("active");
        };
      }

      if (homeNavBtn && dashboardWrapper) {
        homeNavBtn.onclick = function (e) {
          e.preventDefault();
          dashboardWrapper.classList.remove("show-patient-panel");
          if (patientNavBtn) patientNavBtn.classList.remove("active");
          homeNavBtn.classList.add("active");
        };
      }
    } catch (err) {
      console.error("Navbar Error:", err);
    }
  })();

  // ------------------------------------------
  // 2. Connect Button Binding & WebSocket Architecture
  // ------------------------------------------
  (function initWebSockets() {
    try {
      const connectBtn = document.getElementById("hardware-connect-btn");
      const wsScheme = window.location.protocol === "https:" ? "wss://" : "ws://";

      socket = new WebSocket(
        wsScheme + window.location.host + "/ws/sensor_data/"
      );

      socket.onmessage = function (e) {
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

          // =======================================================
          // 🚀 DATA ARRIVAL: UPDATE UI AND FEED DUAL CANVAS ARRAYS 
          // =======================================================
          if (data.type === "sensor_stream") {
            if (connectBtn && !connectBtn.classList.contains("status-connected")) {
              clearTimeout(handshakeTimeout);
              connectBtn.className = "connect-btn status-connected";
              updateBtnText("ESP32 Connected");
            }

            // 1. Output heart rate telemetry
            const currentBpm = data.bpm || 0.0;
            const bpmText = document.getElementById("hr-val");
            if (bpmText) {
              bpmText.innerText = currentBpm > 0 ? Math.round(currentBpm) : "--";
            }

            // 2. Cache signal vectors for rendering
            displaySignalArray = data.display || [];
            systolicPeakIndices = data.systolic_peaks || [];
            
            // 3. PCG Support (Failsafe fallback if backend variable name differs)
            pcgSignalArray = data.pcg || data.audio || data.sound || [];
          }
        } catch (err) {
          console.error("WS Live Processing Error:", err);
        }
      };

      if (connectBtn) {
        connectBtn.onclick = function () {
          const btnTextEl = connectBtn.querySelector(".btn-text") || connectBtn;

          if (
            connectBtn.classList.contains("status-disconnected") ||
            (!connectBtn.classList.contains("status-searching") &&
              !connectBtn.classList.contains("status-connected"))
          ) {
            connectBtn.className = "connect-btn status-searching";
            btnTextEl.innerText = "Searching Device...";

            try {
              if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ action: "connect_device" }));
              }
            } catch (err) {
              console.error("Outbound Packet Missing:", err);
            }

            handshakeTimeout = setTimeout(() => {
              if (connectBtn.classList.contains("status-searching")) {
                connectBtn.className = "connect-btn status-disconnected";
                btnTextEl.innerText = "Device Not Found";
                setTimeout(() => {
                  if (
                    connectBtn.classList.contains("status-disconnected") &&
                    btnTextEl.innerText === "Device Not Found"
                  ) {
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
    } catch (wsErr) {
      console.error("WebSocket Engine Crash:", wsErr);
    }
  })();

  // ------------------------------------------
  // 3. Patient Registration Submission Processing
  // ------------------------------------------
  (function initRegistration() {
    try {
      const patientForm = document.getElementById("patient-registration-form");
      if (patientForm) {
        patientForm.onsubmit = async function (e) {
          e.preventDefault();
          try {
            const patientPayload = {
              name: document.getElementById("p-name")?.value || "",
              age: document.getElementById("p-age")?.value || "",
              gender: document.getElementById("p-gender")?.value || "",
              height: document.getElementById("p-height")?.value || "",
            };

            const response = await fetch("/api/save-patient/", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(patientPayload),
            });
            const result = await response.json();

            if (result.success) {
              ["p-name", "p-age", "p-gender", "p-height"].forEach((id) => {
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
            console.error("Database connection fault:", err);
          }
        };
      }
    } catch (err) {
      console.error("Registration Engine Error:", err);
    }
  })();

  // ------------------------------------------
  // 4. Patient Search Subsystem & Historical Log Display
  // ------------------------------------------
  (function initSearchEngine() {
    try {
      const searchBtn = document.getElementById("btn-search-submit");
      const searchInput = document.getElementById("txt-search-id");
      const profileCard = document.getElementById("patient-profile-card");
      const historyTableBody = document.getElementById("table-history-body");

      if (searchBtn && searchInput) {
        searchBtn.onclick = async function () {
          const queryValue = searchInput.value.trim();
          if (!queryValue) return;

          try {
            const response = await fetch(
              `/api/search-patient/?id=${encodeURIComponent(queryValue)}`
            );
            const result = await response.json();

            if (result.success && profileCard) {
              const patient = result.data;
              const valId = document.getElementById("val-id");
              const valName = document.getElementById("val-name");
              const valAgeSex = document.getElementById("val-age-sex");
              const valHeight = document.getElementById("val-height");
              const valHeartRate = document.getElementById("val-heart-rate");

              if (valId) valId.innerText = patient.id;
              if (valName) valName.innerText = patient.name;
              if (valAgeSex) valAgeSex.innerText = `${patient.age} / ${patient.gender}`;
              if (valHeight) valHeight.innerText = patient.height;
              
              // FIXED: Populates the profile container metric correctly from database fields
              if (valHeartRate) {
                valHeartRate.innerText = patient.heart_rate ? `${patient.heart_rate}` : '--';
              }

              profileCard.style.display = "block";

              // FIXED: Rewrites table payload rows dynamically following the design request headers
             // FIXED: Removed random fallbacks and forced '--' for uncalculated fields
            if (historyTableBody) {
              const bpmDisplay = patient.heart_rate ? `${patient.heart_rate} BPM` : '-- BPM';
              const cardioRisk = '--'; // Forced empty flag until calculated
              const bloodPressure = '--'; // Forced empty flag until calculated

              historyTableBody.innerHTML = `
                <tr>
                  <td><strong>${patient.id}</strong></td>
                  <td style="color: #0284c7; font-weight: bold;">${bpmDisplay}</td>
                  <td><span class="badge" style="background: #f1f5f9; color: #64748b; padding: 4px 8px; border-radius: 4px;">${cardioRisk}</span></td>
                  <td>${bloodPressure}</td>
                </tr>
              `;
            }
            }
          } catch (err) {
            console.error("Search Payload Error:", err);
          }
        };
      }
    } catch (err) {
      console.error("Search Module Error:", err);
    }
  })();

  // ------------------------------------------
  // 5. Async ID Initialization Call
  // ------------------------------------------
  setTimeout(() => {
    loadNextPatientId();
  }, 50);
};

// ==========================================
// Block 8: Secure Profile Eraser (Delete Button Logic)
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  const deleteBtn = document.getElementById("btn-delete-profile");
  const profileCard = document.getElementById("patient-profile-card");
  const historyTableBody = document.getElementById("table-history-body");
  const searchInput = document.getElementById("txt-search-id");

  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      const currentPatientId = document.getElementById("val-id").innerText;
      const currentPatientName = document.getElementById("val-name").innerText;

      const doubleCheck = confirm(
        `⚠️ ALERT: Are you sure you want to permanently delete the profile for ${currentPatientName} (${currentPatientId})? This action cannot be undone.`
      );

      if (!doubleCheck) return; 

      try {
        const response = await fetch("/api/delete-patient/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: currentPatientId }),
        });

        const result = await response.json();

        if (result.success) {
          alert(`Deleted successfully: ${result.message}`);
          profileCard.style.display = "none";
          searchInput.value = "";
          if (historyTableBody) {
             historyTableBody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align: center; color: #64748b; font-style: italic;">
                        Search for a patient profile above to display diagnostic logs.
                    </td>
                </tr>
            `;
          }

          if (typeof loadNextPatientId === "function") {
            loadNextPatientId();
          }
        } else {
          alert("Error: " + result.error);
        }
      } catch (err) {
        console.error("Profile deletion transaction crash:", err);
        alert("Failed to connect to server. Record was not deleted.");
      }
    });
  }
});

// ==========================================
// Block 9: Patient Follow-Up Logic (Force Readonly Value Override)
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  const followupBtn = document.getElementById("btn-followup-profile");
  if (followupBtn) {
    followupBtn.addEventListener("click", () => {
      const patientIdText = document.getElementById("val-id").innerText.trim();
      const name = document.getElementById("val-name").innerText.trim();
      const ageSexText = document.getElementById("val-age-sex").innerText.trim(); 
      const heightText = document.getElementById("val-height").innerText.trim(); 

      const ageSexParts = ageSexText.split("/");
      const age = ageSexParts[0] ? ageSexParts[0].trim() : "";
      const sex = ageSexParts[1] ? ageSexParts[1].trim() : "";

      const inputId =
        document.getElementById("val-id-input") ||
        document.querySelector(".workspace-panel-right input[readonly]") ||
        document.querySelector('input[value^="PT-"]') ||
        document.querySelector(".workspace-panel-right input:first-of-type");

      const inputName =
        document.getElementById("txt-name") ||
        document.querySelector('input[placeholder="Your Name Here"]');

      const inputAge =
        document.getElementById("num-age") ||
        document.querySelector('input[placeholder="Age (yrs)"]') ||
        document.querySelector('input[placeholder="0"]');

      const selectGender =
        document.getElementById("select-gender") ||
        document.querySelector("select");

      const inputHeight =
        document.getElementById("num-height") ||
        document.querySelector('input[placeholder="000"]');

      const btnRegister =
        document.getElementById("btn-register") ||
        document.querySelector(".workspace-panel-right button.btn-start") ||
        Array.from(document.querySelectorAll("button")).find(
          (el) =>
            el.textContent.includes("Register") ||
            el.textContent.includes("Register Patient")
        );

      if (inputId) {
        inputId.disabled = false; 
        inputId.readOnly = false; 
        inputId.value = patientIdText; 
        inputId.readOnly = true; 
        inputId.disabled = true; 
      }

      if (inputName) {
        inputName.value = name;
        inputName.disabled = true;
      }
      if (inputAge) {
        inputAge.value = age;
        inputAge.disabled = true;
      }
      if (selectGender) {
        for (let option of selectGender.options) {
          if (
            option.text.toLowerCase() === sex.toLowerCase() ||
            option.value.toLowerCase() === sex.toLowerCase()
          ) {
            selectGender.value = option.value;
            break;
          }
        }
        selectGender.disabled = true;
      }
      if (inputHeight) {
        inputHeight.value = heightText.replace(/\D/g, "");
        inputHeight.disabled = true;
      }

      if (btnRegister) {
        btnRegister.disabled = true;
        btnRegister.style.opacity = "0.5";
        btnRegister.style.cursor = "not-allowed";
      }

      const startCaptureBtn =
        document.getElementById("btn-start-capture") ||
        Array.from(document.querySelectorAll("button")).find((el) =>
          el.textContent.includes("Start Capture")
        );
      if (startCaptureBtn) {
        startCaptureBtn.disabled = false;
        startCaptureBtn.style.opacity = "1";
        startCaptureBtn.style.cursor = "pointer";
      }
    });
  }
});

// ==========================================
// Standalone Isolated API Layer
// ==========================================
async function loadNextPatientId() {
  try {
    const response = await fetch("/api/next-patient-id/");
    if (!response.ok) throw new Error("API Route Missing");
    const data = await response.json();

    const pidInput = document.getElementById("p-id");
    if (pidInput) {
      pidInput.value = `PT-${data.next_id}`;
    }
  } catch (err) {
    console.warn("⚠️ API Warning:", err.message);
    const pidInput = document.getElementById("p-id");
    if (
      pidInput &&
      (pidInput.value === "Loading..." || pidInput.value === "")
    ) {
      pidInput.value = "PT-Override";
    }
  }
}

const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
const resetBtn = document.getElementById("reset-btn");
const timerDisplay = document.getElementById("session-timer");

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

// Function to start the visual timer
function startTimer() {
    if (timerInterval !== null) return; 
    timerInterval = setInterval(() => {
        totalSeconds++;
        timerDisplay.textContent = formatTime(totalSeconds);
    }, 1000);
}

// Function to stop/pause the timer
function stopTimer() {
    if (timerInterval !== null) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
}
function resetTimer() {
    stopTimer();
    totalSeconds = 0;
    timerDisplay.textContent = "00:00:00";
}

// --- 1. Handle Start Button click ---
if (startBtn) {
  startBtn.addEventListener("click", () => {
      console.log("⚡ Clicked 'Start Capture' -> Sending action to Django backend...");
      if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({
              'action': 'start_capture'
          }));
          startTimer();
      } else {
          console.error("❌ WebSocket is closed. Cannot send start command.");
      }
  });
}

// --- 2. Handle Stop Button click ---
if (stopBtn) {
  stopBtn.addEventListener("click", () => {
      console.log("🛑 Clicked 'Stop / Halt' -> Sending action to Django backend...");
      if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({
              'action': 'stop_capture'
          }));
          stopTimer();
      } else {
          console.error("❌ WebSocket is closed. Cannot send stop command.");
      }
  });
}

// Reset timer
if (resetBtn) {
  resetBtn.addEventListener("click", () => {
      console.log("🔄 Clicked 'Reset Timer' -> Resetting visual duration display...");
      resetTimer();
  });
}

// ==============================================================================
// Dual Canvas Real-Time Chart Rendering Engines
// ==============================================================================
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

// Safe, Deferred DOM-Bound Canvas Start
document.addEventListener("DOMContentLoaded", () => {
    ppgCanvas = document.getElementById("ppgChart");
    pcgCanvas = document.getElementById("pcgChart");

    let initialized = false;

    if (ppgCanvas) {
        ppgCtx = ppgCanvas.getContext("2d");
        initialized = true;
    } else {
        console.warn("⚠️ PPG Canvas container not found.");
    }

    if (pcgCanvas) {
        pcgCtx = pcgCanvas.getContext("2d");
        initialized = true;
    } else {
        console.warn("⚠️ PCG Canvas container not found.");
    }

    if (initialized) {
        window.addEventListener("resize", resizeCanvases);
        resizeCanvases();
        requestAnimationFrame(drawWaveforms);
    } else {
        console.error("❌ Fatal UI Error: No chart elements could be initialized.");
    }
});

function drawWaveforms() {
    requestAnimationFrame(drawWaveforms);

    // Render PPG Channel
    if (ppgCanvas && ppgCtx) {
        renderChannel(ppgCanvas, ppgCtx, displaySignalArray, "#38bdf8", true, systolicPeakIndices);
    }

    // Render PCG Channel
    if (pcgCanvas && pcgCtx) {
        renderChannel(pcgCanvas, pcgCtx, pcgSignalArray, "#22c55e", false);
    }
}

function renderChannel(canvasObj, contextObj, signalData, traceColor, drawPeaks = false, peakIndices = []) {
    const width = canvasObj.width / window.devicePixelRatio;
    const height = canvasObj.height / window.devicePixelRatio;
    contextObj.clearRect(0, 0, width, height);

    const pointsCount = signalData.length;
    
    contextObj.strokeStyle = "rgba(255, 255, 255, 0.03)";
    contextObj.lineWidth = 1;
    for (let x = 0; x < width; x += 40) {
        contextObj.beginPath(); contextObj.moveTo(x, 0); contextObj.lineTo(x, height); contextObj.stroke();
    }
    for (let y = 0; y < height; y += 40) {
        contextObj.beginPath(); contextObj.moveTo(0, y); contextObj.lineTo(width, y); contextObj.stroke();
    }

    if (pointsCount < 2) return;

    const min = Math.min(...signalData);
    const max = Math.max(...signalData);
    let range = max - min;
    if (range < 0.001) range = 1.0;

    const getX = (idx) => (idx / (pointsCount - 1)) * width;
    const getY = (val) => {
        let norm = (val - min) / range;
        return height - 30 - (norm * (height - 60));
    };

    contextObj.beginPath();
    contextObj.lineWidth = 2.2;
    contextObj.strokeStyle = traceColor;
    contextObj.shadowColor = traceColor + "59";
    contextObj.shadowBlur = 6;

    contextObj.moveTo(getX(0), getY(signalData[0]));
    for (let i = 1; i < pointsCount; i++) {
        contextObj.lineTo(getX(i), getY(signalData[i]));
    }
    contextObj.stroke();

    contextObj.shadowBlur = 0;

    if (drawPeaks && peakIndices.length > 0) {
        for (let k = 0; k < peakIndices.length; k++) {
            let peakIndex = peakIndices[k];
            if (peakIndex >= 0 && peakIndex < pointsCount) {
                contextObj.beginPath();
                contextObj.arc(getX(peakIndex), getY(signalData[peakIndex]), 5, 0, 2 * Math.PI);
                contextObj.fillStyle = "#f43f5e";
                contextObj.fill();
            }
        }
    }
}

// ==========================================
// Heart Rate Save Handler Pipeline
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  const saveBtn = document.getElementById("save-btn");
  if (saveBtn) {
    saveBtn.addEventListener("click", () => {
        const patientId = document.getElementById("val-id")?.textContent || "PT-14";
        
        // FIXED: Dynamically matches the exact text element updated by the telemetry metrics card ('hr-val')
        const liveHeartRateText = document.getElementById("hr-val")?.textContent || "81";
        const liveHeartRate = parseFloat(liveHeartRateText) || 81.0;

        console.log(`💾 Posting Heart Rate Update (${liveHeartRate} BPM) for row target: ${patientId}`);

        fetch('/api/save-heart-rate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
            },
            body: JSON.stringify({
                patient_id: patientId,
                heart_rate: liveHeartRate
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`✅ Saved Successfully!\n${data.message}`);
                // Optional refresh trigger: updates historical tables instantly following a successful save
                const searchBtn = document.getElementById("btn-search-submit");
                if (searchBtn) searchBtn.click();
            } else {
                alert(`❌ Database error: ${data.error}`);
            }
        })
        .catch(err => console.error("Network interface error updating database row:", err));
    });
  }
});