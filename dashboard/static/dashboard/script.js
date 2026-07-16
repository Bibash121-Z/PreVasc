let socket = null;
let handshakeTimeout = null;

// ==========================================
// Main Execution Engine - Defensively Guarded
// ==========================================
window.onload = function () {
  console.log("⚙️ PreVasc UI Init Engine Fired Successfully (Charts Removed).");

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
      const wsScheme =
        window.location.protocol === "https:" ? "wss://" : "ws://";

      socket = new WebSocket(
        wsScheme + window.location.host + "/ws/sensor_data/",
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

          if (data.type === "sensor_stream") {
            if (
              connectBtn &&
              !connectBtn.classList.contains("status-connected")
            ) {
              clearTimeout(handshakeTimeout);
              connectBtn.className = "connect-btn status-connected";
              updateBtnText("ESP32 Connected");
            }

            const currentBpm = data.bpm || 0.0;
            const bpmText = document.getElementById("hr-val"); // Matches HTML target element
            if (bpmText) bpmText.innerText = Number(currentBpm).toFixed(1);
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
              const submitBtn = patientForm.querySelector(
                'button[type="submit"]',
              );
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
  // 4. Patient Search Subsystem
  // ------------------------------------------
  (function initSearchEngine() {
    try {
      const searchBtn = document.getElementById("btn-search-submit");
      const searchInput = document.getElementById("txt-search-id");
      const profileCard = document.getElementById("patient-profile-card");

      if (searchBtn && searchInput) {
        searchBtn.onclick = async function () {
          const queryValue = searchInput.value.trim();
          if (!queryValue) return;

          try {
            const response = await fetch(
              `/api/search-patient/?id=${encodeURIComponent(queryValue)}`,
            );
            const result = await response.json();

            if (result.success && profileCard) {
              const patient = result.data;
              const valId = document.getElementById("val-id");
              const valName = document.getElementById("val-name");
              const valAgeSex = document.getElementById("val-age-sex");
              const valHeight = document.getElementById("val-height");

              if (valId) valId.innerText = patient.id;
              if (valName) valName.innerText = patient.name;
              if (valAgeSex)
                valAgeSex.innerText = `${patient.age} / ${patient.gender}`;
              if (valHeight) valHeight.innerText = patient.height;

              profileCard.style.display = "block";
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
//======================================================================

// ==========================================

/// Block 8: Secure Profile Eraser (Delete Button Logic)

// ==========================================

document.addEventListener("DOMContentLoaded", () => {
  const deleteBtn = document.getElementById("btn-delete-profile");
  const profileCard = document.getElementById("patient-profile-card");
  const historyTableBody = document.getElementById("table-history-body");
  const searchInput = document.getElementById("txt-search-id");

  if (deleteBtn) {
    // NOTE: Hover effects removed from here so your CSS stylesheet takes full control!

    deleteBtn.addEventListener("click", async () => {
      const currentPatientId = document.getElementById("val-id").innerText;
      const currentPatientName = document.getElementById("val-name").innerText;

      // Confirm twice to prevent accidental misclicks
      const doubleCheck = confirm(
        `⚠️ ALERT: Are you sure you want to permanently delete the profile for ${currentPatientName} (${currentPatientId})? This action cannot be undone.`,
      );

      if (!doubleCheck) return; // Cancel operation

      try {
        const response = await fetch("/api/delete-patient/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },

          body: JSON.stringify({ id: currentPatientId }),
        });

        const result = await response.json();

        if (result.success) {
          alert(`Deleted successfully: ${result.message}`);
          // Reset and clean up the UI
          profileCard.style.display = "none";
          searchInput.value = "";
          historyTableBody.innerHTML = `
                        <tr>
                            <td colspan="4" style="text-align: center; color: #64748b; font-style: italic;">
                                Search for a patient profile above to display diagnostic logs.
                            </td>
                        </tr>
                    `;

          // Call the next ID loader to update the registration page forms as well
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

// Block 9: Patient Follow-Up Logic (Force Readonly Value Override)

// ==========================================

document.addEventListener("DOMContentLoaded", () => {
  const followupBtn = document.getElementById("btn-followup-profile");
  if (followupBtn) {
    followupBtn.addEventListener("click", () => {
      // 1. Read existing patient data from the Active Clinical Profile card
      const patientIdText = document.getElementById("val-id").innerText.trim(); // e.g., "PT-7"
      const name = document.getElementById("val-name").innerText.trim();
      const ageSexText = document
        .getElementById("val-age-sex")
        .innerText.trim(); // e.g., "21 / Male"
      const heightText = document.getElementById("val-height").innerText.trim(); // e.g., "163"

      // Parse Age and Sex

      const ageSexParts = ageSexText.split("/");
      const age = ageSexParts[0] ? ageSexParts[0].trim() : "";
      const sex = ageSexParts[1] ? ageSexParts[1].trim() : "";

      // 2. Target the Patient ID input on the right (trying multiple fallback matches)

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
            el.textContent.includes("Register Patient"),
        );

      // 3. FORCE write the Patient ID even if locked by Django/HTML template

      if (inputId) {
        inputId.disabled = false; // Temporarily unlock to allow value overwrite
        inputId.readOnly = false; // Temporarily unlock
        inputId.value = patientIdText; // Overwrite value to PT-7!
        inputId.readOnly = true; // Re-lock
        inputId.disabled = true; // Re-lock
      }

      // 4. Fill and lock remaining fields

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

      // 5. Disable registration submission to protect database
      if (btnRegister) {
        btnRegister.disabled = true;
        btnRegister.style.opacity = "0.5";
        btnRegister.style.cursor = "not-allowed";
      }

      // 6. Unlock hardware activation
      const startCaptureBtn =
        document.getElementById("btn-start-capture") ||
        Array.from(document.querySelectorAll("button")).find((el) =>
          el.textContent.includes("Start Capture"),
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
