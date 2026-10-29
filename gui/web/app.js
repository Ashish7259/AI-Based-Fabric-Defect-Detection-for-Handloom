/**
 * Handloom AI Fabric Defect Detection System - Interactive Web Dashboard Engine
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const canvas = document.getElementById("inspectionCanvas");
    const ctx = canvas.getContext("2d");
    
    const emptyState = document.getElementById("emptyState");
    const fileInput = document.getElementById("fileInput");
    const selectUploadBtn = document.getElementById("selectUploadBtn");
    const toggleWebcamBtn = document.getElementById("toggleWebcamBtn");
    const toggleOpencvCamBtn = document.getElementById("toggleOpencvCamBtn");
    const simStopBtn = document.getElementById("simStopBtn");
    const samplesContainer = document.getElementById("samplesContainer");
    
    // Status Elements
    const aiStatusBadge = document.getElementById("aiStatusBadge");
    const aiStatusText = document.getElementById("aiStatusText");
    const simModeBadge = document.getElementById("simModeBadge");
    const simModeText = document.getElementById("simModeText");
    const motorStatusBadge = document.getElementById("motorStatusBadge");
    const motorStatusText = document.getElementById("motorStatusText");
    const motorSpinner = document.getElementById("motorSpinner");
    
    // Defect Alert Elements
    const defectAlertOverlay = document.getElementById("defectAlertOverlay");
    const alertDesc = document.getElementById("alertDesc");
    const stopCountdown = document.getElementById("stopCountdown");

    // Telemetry & Stats Elements
    const statusCnn = document.getElementById("statusCnn");
    const statusResnet = document.getElementById("statusResnet");
    const statusEnsemble = document.getElementById("statusEnsemble");
    const statusEsp32 = document.getElementById("statusEsp32");
    const statusMode = document.getElementById("statusMode");
    const statusDevice = document.getElementById("statusDevice");
    
    const statTotal = document.getElementById("statTotal");
    const statNormal = document.getElementById("statNormal");
    const statHoles = document.getElementById("statHoles");
    const statStains = document.getElementById("statStains");
    const statWeaving = document.getElementById("statWeaving");
    
    const historyTableBody = document.getElementById("historyTableBody");
    const activeClassBadge = document.getElementById("activeClassBadge");

    // Defect Checklist Panel Elements
    const defectChecklistContainer = document.getElementById("defectChecklistContainer");
    const defectChecklistCount = document.getElementById("defectChecklistCount");
    const defectChecklistBadge = document.getElementById("defectChecklistBadge");

    // Probabilities Elements
    const pctNormal = document.getElementById("pctNormal");
    const pctHole = document.getElementById("pctHole");
    const pctStain = document.getElementById("pctStain");
    const pctWeaving = document.getElementById("pctWeaving");

    const barCnnNormal = document.getElementById("barCnnNormal");
    const barResnetNormal = document.getElementById("barResnetNormal");
    const barEnsembleNormal = document.getElementById("barEnsembleNormal");

    const barCnnHole = document.getElementById("barCnnHole");
    const barResnetHole = document.getElementById("barResnetHole");
    const barEnsembleHole = document.getElementById("barEnsembleHole");

    const barCnnStain = document.getElementById("barCnnStain");
    const barResnetStain = document.getElementById("barResnetStain");
    const barEnsembleStain = document.getElementById("barEnsembleStain");

    const barCnnWeaving = document.getElementById("barCnnWeaving");
    const barResnetWeaving = document.getElementById("barResnetWeaving");
    const barEnsembleWeaving = document.getElementById("barEnsembleWeaving");

    // Settings Modal Elements
    const settingsBtn = document.getElementById("settingsBtn");
    const settingsModal = document.getElementById("settingsModal");
    const closeSettingsBtn = document.getElementById("closeSettingsBtn");
    const saveSettingsBtn = document.getElementById("saveSettingsBtn");
    const confSlider = document.getElementById("confSlider");
    const confVal = document.getElementById("confVal");
    const motorTimeSlider = document.getElementById("motorTimeSlider");
    const motorTimeVal = document.getElementById("motorTimeVal");
    const simToggle = document.getElementById("simToggle");
    const audioToggle = document.getElementById("audioToggle");

    // State Variables
    let currentImage = null;
    let currentDetections = [];
    let isWebcamActive = false;
    let webcamStream = null;
    let videoElement = null;
    let webcamInterval = null;
    let isOpencvCamActive = false;
    let opencvCamInterval = null;
    let audioContext = null;

    // Upgraded GUI State Variables
    let activeDefectIndex = -1;
    let viewMode = "after"; // "before" or "after"
    let currentHistory = [];
    let currentStats = null;

    // Audio event deduplication — tracks the last defect class for which we
    // played a sound so we don't re-fire on every poll while motor is stopped.
    let lastPlayedAudioAlert = null;

    // Frame In-flight Lock & Monotonic Frame ID Sequencing
    let isProcessingWebcamFrame = false;
    let lastRenderedFrameId = 0;
    let localFrameCounter = 0;

    // Web Audio Synthesizer for Defect Sounds
    function initAudioContext() {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
    }

    function playDefectSound(defectType) {
        if (!audioToggle.checked) return;
        try {
            initAudioContext();
            const osc = audioContext.createOscillator();
            const gain = audioContext.createGain();

            osc.connect(gain);
            gain.connect(audioContext.destination);

            const now = audioContext.currentTime;

            if (defectType === "hole") {
                // High alert double beep
                osc.type = "sine";
                osc.frequency.setValueAtTime(880, now); // A5
                gain.gain.setValueAtTime(0.3, now);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
                osc.start(now);
                osc.stop(now + 0.3);
            } else if (defectType === "stain") {
                // Mid-tone alert
                osc.type = "triangle";
                osc.frequency.setValueAtTime(587.33, now); // D5
                gain.gain.setValueAtTime(0.3, now);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
                osc.start(now);
                osc.stop(now + 0.4);
            } else if (defectType === "weaving_error") {
                // Sawtooth structural warning sound
                osc.type = "sawtooth";
                osc.frequency.setValueAtTime(440, now); // A4
                gain.gain.setValueAtTime(0.3, now);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.5);
                osc.start(now);
                osc.stop(now + 0.5);
            }
        } catch (e) {
            console.log("Audio play error:", e);
        }
    }

    // Canvas Drawing Helper
    function renderInspectionCanvas(img, detections = []) {
        if (!img) return;

        canvas.width = img.width;
        canvas.height = img.height;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);

        emptyState.classList.add("hidden");

        // Color definitions per defect type
        const colors = {
            "hole": "#f43f5e",        // Crimson Red
            "stain": "#f59e0b",       // Amber Gold
            "weaving_error": "#a855f7", // Vibrant Purple
            "normal": "#10b981"       // Emerald
        };

        // Draw Bounding Boxes for checked/visible defects
        const visibleDetections = detections.filter(det => det.visible !== false);
        visibleDetections.forEach((det) => {
            const [x1, y1, x2, y2] = det.box;
            const cls = det.class;
            const conf = Math.round(det.confidence * 100);
            const color = colors[cls] || "#38bdf8";

            // Check if this detection is currently selected/highlighted
            const isSelected = (detections.indexOf(det) === activeDefectIndex);

            ctx.shadowBlur = 0; // Reset shadow

            if (isSelected) {
                // Neon glow highlighted box
                ctx.shadowColor = color;
                ctx.shadowBlur = 20;
                ctx.strokeStyle = "#ffffff";
                ctx.lineWidth = 6;
            } else {
                ctx.strokeStyle = color;
                ctx.lineWidth = 4;
            }

            // Draw Box Border
            ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
            ctx.shadowBlur = 0; // reset

            // Draw Box Corner Accents
            const cornerLen = 16;
            ctx.fillStyle = isSelected ? "#ffffff" : color;
            ctx.fillRect(x1, y1, cornerLen, ctx.lineWidth);
            ctx.fillRect(x1, y1, ctx.lineWidth, cornerLen);

        });
    }

    // Interactive Defect Checklist UI Helper
    function updateDefectChecklist(detections) {
        if (!defectChecklistContainer) return;
        
        defectChecklistCount.textContent = detections.length;

        // Clear details panel by default if no defects
        if (detections.length === 0) {
            defectChecklistBadge.textContent = "NO DEFECTS";
            defectChecklistBadge.style.color = "var(--accent-cyan)";
            defectChecklistBadge.style.borderColor = "rgba(56, 189, 248, 0.3)";
            defectChecklistContainer.innerHTML = '<div class="checklist-empty"><i class="fa-solid fa-shield-cat"></i> No defects detected in current frame.</div>';
            activeDefectIndex = -1;
            updateDefectDetails(null);
            return;
        }

        defectChecklistBadge.textContent = `${detections.length} DEFECTS FOUND`;
        defectChecklistBadge.style.color = "#f43f5e";
        defectChecklistBadge.style.borderColor = "rgba(244, 63, 94, 0.4)";
        defectChecklistContainer.innerHTML = "";
        
        // Auto-select the first defect if current active index is invalid
        if (activeDefectIndex < 0 || activeDefectIndex >= detections.length) {
            activeDefectIndex = 0;
        }

        detections.forEach((det, idx) => {
            if (det.visible === undefined) det.visible = true;

            const item = document.createElement("div");
            item.className = `defect-item-checkbox ${det.class}`;
            if (idx === activeDefectIndex) {
                item.classList.add("active-highlight");
            }
            
            const confPct = Math.round(det.confidence * 100);
            const boxStr = `[${det.box[0]}, ${det.box[1]}, ${det.box[2]}, ${det.box[3]}]`;
            const temporalBadge = det.temporal_status ? `<span class="badge ${det.temporal_status === 'NEW' ? 'warning-badge' : 'info-badge'}" style="margin-left: 8px; font-size: 10px; padding: 2px 6px;">ID #${det.temporal_id} (${det.temporal_status})</span>` : '';

            item.innerHTML = `
                <label style="flex: 1; display: flex; align-items: center; gap: 10px; cursor: pointer;">
                    <input type="checkbox" id="chk_defect_${idx}" ${det.visible ? "checked" : ""}>
                    <span><strong>Defect #${idx + 1}:</strong> ${det.class.toUpperCase()} (${confPct}%) ${temporalBadge}</span>
                </label>
                <span class="defect-meta-tag">Box: ${boxStr}</span>
            `;

            // Row click highlights defect and zooms
            item.addEventListener("click", (e) => {
                if (e.target.type === "checkbox") return;

                activeDefectIndex = idx;
                
                // Toggle active-highlight classes in list
                const allItems = defectChecklistContainer.querySelectorAll(".defect-item-checkbox");
                allItems.forEach((el, i) => {
                    if (i === idx) el.classList.add("active-highlight");
                    else el.classList.remove("active-highlight");
                });

                updateDefectDetails(det, idx);
                renderInspectionCanvas(currentImage, viewMode === "after" ? currentDetections : []);
            });

            const chk = item.querySelector(`#chk_defect_${idx}`);
            chk.addEventListener("change", (e) => {
                det.visible = e.target.checked;
                renderInspectionCanvas(currentImage, viewMode === "after" ? currentDetections : []);
            });

            defectChecklistContainer.appendChild(item);
        });

        // Initialize details panel for selected active index
        updateDefectDetails(detections[activeDefectIndex], activeDefectIndex);
    }

    // Zoom and Details Card Update Functions
    function updateDefectDetails(det, idx) {
        const detailsCard = document.getElementById("defectDetailsCard");
        if (!det) {
            if (detailsCard) detailsCard.classList.add("hidden");
            return;
        }

        if (detailsCard) detailsCard.classList.remove("hidden");

        const activeBadge = document.getElementById("detailsActiveBadge");
        const detailsType = document.getElementById("detailsType");
        const detailsConfidence = document.getElementById("detailsConfidence");
        const detailsPosition = document.getElementById("detailsPosition");
        const detailsSize = document.getElementById("detailsSize");
        const detailsAction = document.getElementById("detailsAction");

        const [x1, y1, x2, y2] = det.box;
        const w = x2 - x1;
        const h = y2 - y1;

        if (activeBadge) activeBadge.textContent = `Defect #${idx + 1}`;
        if (detailsType) {
            detailsType.textContent = det.class.toUpperCase();
            detailsType.style.color = `var(--color-${det.class.toLowerCase()})`;
        }
        if (detailsConfidence) detailsConfidence.textContent = `${Math.round(det.confidence * 100)}%`;
        if (detailsPosition) detailsPosition.textContent = `X: ${x1}, Y: ${y1}`;
        if (detailsSize) detailsSize.textContent = `${w} × ${h} px`;
        
        const stopSeconds = parseFloat(document.getElementById("motorTimeSlider")?.value || 1.5);
        if (detailsAction) detailsAction.textContent = `Halt Motor (${stopSeconds}s)`;

        drawDefectZoom(det.box);
    }

    function drawDefectZoom(box) {
        const zoomCanvas = document.getElementById("defectZoomCanvas");
        if (!zoomCanvas || !currentImage) return;

        const zctx = zoomCanvas.getContext("2d");
        const [x1, y1, x2, y2] = box;
        const w = x2 - x1;
        const h = y2 - y1;

        zoomCanvas.width = 140;
        zoomCanvas.height = 140;
        zctx.clearRect(0, 0, 140, 140);

        const scale = Math.min(140 / w, 140 / h);
        const dw = w * scale;
        const dh = h * scale;
        const dx = (140 - dw) / 2;
        const dy = (140 - dh) / 2;

        try {
            zctx.drawImage(currentImage, x1, y1, w, h, dx, dy, dw, dh);
        } catch (err) {
            console.error("Zoom canvas error:", err);
        }
    }

    // Toggle overlay for AI analysis progress
    function setAnalysisState(loading) {
        const indicator = document.getElementById("analysisIndicator");
        if (indicator) {
            if (loading) {
                indicator.classList.remove("hidden");
            } else {
                indicator.classList.add("hidden");
            }
        }
    }

    // Update Telemetry & Probability Dashboard
    function updateDashboardUI(data) {
        if (!data) return;

        // Probabilities
        if (data.probabilities && data.probabilities.ensemble) {
            const ens = data.probabilities.ensemble;
            const cnn = data.probabilities.cnn || ens;
            const res = data.probabilities.resnet || ens;

            // Normal
            const pNorm = Math.round((ens.normal || 0) * 100);
            pctNormal.textContent = `${pNorm}%`;
            barCnnNormal.style.width = `${Math.round((cnn.normal || 0) * 100)}%`;
            barResnetNormal.style.width = `${Math.round((res.normal || 0) * 100)}%`;
            barEnsembleNormal.style.width = `${pNorm}%`;

            // Hole
            const pHole = Math.round((ens.hole || 0) * 100);
            pctHole.textContent = `${pHole}%`;
            barCnnHole.style.width = `${Math.round((cnn.hole || 0) * 100)}%`;
            barResnetHole.style.width = `${Math.round((res.hole || 0) * 100)}%`;
            barEnsembleHole.style.width = `${pHole}%`;

            // Stain
            const pStain = Math.round((ens.stain || 0) * 100);
            pctStain.textContent = `${pStain}%`;
            barCnnStain.style.width = `${Math.round((cnn.stain || 0) * 100)}%`;
            barResnetStain.style.width = `${Math.round((res.stain || 0) * 100)}%`;
            barEnsembleStain.style.width = `${pStain}%`;

            // Weaving
            const pWeave = Math.round((ens.weaving_error || 0) * 100);
            pctWeaving.textContent = `${pWeave}%`;
            barCnnWeaving.style.width = `${Math.round((cnn.weaving_error || 0) * 100)}%`;
            barResnetWeaving.style.width = `${Math.round((res.weaving_error || 0) * 100)}%`;
            barEnsembleWeaving.style.width = `${pWeave}%`;
        }

        // Active Class Badge
        if (data.verified_prediction) {
            const dispClass = data.verified_prediction.toUpperCase();
            const confStr = (dispClass !== "NORMAL" && dispClass !== "UNCERTAIN" && data.detections && data.detections.length > 0) 
                ? ` (${Math.round(data.detections[0].confidence * 100)}%)` 
                : "";
            activeClassBadge.textContent = `Verified: ${dispClass}${confStr}`;
            
            if (dispClass === "UNCERTAIN") {
                activeClassBadge.style.color = "var(--accent-amber)";
            } else if (dispClass === "NORMAL") {
                activeClassBadge.style.color = "var(--accent-emerald)";
            } else {
                activeClassBadge.style.color = "var(--accent-rose)";
            }
        } else if (data.global_prediction) {
            activeClassBadge.textContent = `Global: ${data.global_prediction.toUpperCase()} (${data.global_confidence}%)`;
        }

        // Statistics
        if (data.stats) {
            currentStats = data.stats;
            statTotal.textContent = data.stats.total_inspected || 0;
            statNormal.textContent = data.stats.normal || 0;
            
            const statSessionDefects = document.getElementById("statSessionDefects");
            if (statSessionDefects) {
                statSessionDefects.textContent = data.stats.defects || 0;
            }
            
            const statCurrentDefects = document.getElementById("statCurrentDefects");
            if (statCurrentDefects) {
                statCurrentDefects.textContent = currentDetections.length;
            }

            statHoles.textContent = data.stats.holes || 0;
            statStains.textContent = data.stats.stains || 0;
            statWeaving.textContent = data.stats.weaving_errors || 0;
        }

        // Motor State
        if (data.motor_state === "STOPPED" || data.motor_stop_remaining > 0) {
            motorStatusBadge.classList.add("motor-stopped-badge");
            motorStatusText.textContent = `MOTOR STOPPED (${data.motor_stop_remaining}s)`;
            motorSpinner.style.animationPlayState = "paused";

            // Play audio only on NEW defect events
            if (data.audio_alert && data.debug && data.debug.event_state === "NEW") {
                playDefectSound(data.audio_alert);
            }
        } else {
            motorStatusBadge.classList.remove("motor-stopped-badge");
            motorStatusText.textContent = "CONVEYOR RUNNING";
            motorSpinner.style.animationPlayState = "running";

            // Reset audio tracker when motor is running and no defect is active
            if (!data.defect_detected) {
                lastPlayedAudioAlert = null;
            }
        }
    }

    // Update the Live Inference Debug Panel
    function updateDebugPanel(data) {
        if (!data || !data.debug) return;

        const d = data.debug;
        const dbgFrameId = document.getElementById("dbgFrameId");
        const dbgLatency = document.getElementById("dbgLatency");
        const dbgCnnTop = document.getElementById("dbgCnnTop");
        const dbgResnetTop = document.getElementById("dbgResnetTop");
        const dbgEnsembleTop = document.getElementById("dbgEnsembleTop");
        const dbgRaw = document.getElementById("dbgRawRegions");
        const dbgRej = document.getElementById("dbgLocRejected");
        const dbgPred = document.getElementById("dbgGlobalPred");
        const dbgLoc = document.getElementById("dbgLocState");
        const dbgBadge = document.getElementById("debugEventBadge");

        if (dbgFrameId) dbgFrameId.textContent = `${data.frame_id || "—"} (${data.timestamp || ""})`;
        if (dbgLatency) dbgLatency.textContent = data.processing_time_ms ? `${data.processing_time_ms} ms` : "—";
        if (dbgCnnTop) dbgCnnTop.textContent = d.cnn_top || "—";
        if (dbgResnetTop) dbgResnetTop.textContent = d.resnet_top || "—";
        if (dbgEnsembleTop) dbgEnsembleTop.textContent = d.ensemble_top || "—";

        if (dbgRaw) dbgRaw.textContent = `${d.raw_regions || 0} / ${d.accepted_predictions || 0}`;

        if (dbgRej) {
            const rej = d.localization_rejected ?? 0;
            const unq = d.unique_defects ?? 0;
            dbgRej.textContent = `${rej} / ${unq}`;
            dbgRej.className = rej > 0 ? "debug-val danger-val" : "debug-val";
        }

        // Verified frame prediction status
        if (dbgPred) {
            const pred = data.verified_prediction || data.global_prediction || "—";
            const conf = data.global_confidence ?? "";
            dbgPred.textContent = `${pred.toUpperCase()} ${conf ? "(" + conf + "%)" : ""}`;
            if (pred === "uncertain") {
                dbgPred.style.color = "var(--accent-amber)";
            } else if (pred === "normal") {
                dbgPred.style.color = "var(--accent-emerald)";
            } else {
                dbgPred.style.color = "var(--accent-rose)";
            }
        }

        // Localisation state
        if (dbgLoc) {
            const hasRej = (d.localization_rejected ?? 0) > 0;
            const hasAcc = (d.unique_defects ?? 0) > 0;
            if (hasAcc) {
                dbgLoc.textContent = "ACCEPTED";
                dbgLoc.style.color = "var(--accent-emerald)";
            } else if (hasRej) {
                dbgLoc.textContent = "REJECTED";
                dbgLoc.style.color = "var(--accent-rose)";
            } else {
                dbgLoc.textContent = "N/A";
                dbgLoc.style.color = "var(--text-dim)";
            }
        }

        // Event badge
        const dbgTemporal = document.getElementById("dbgTemporal");
        if (dbgTemporal) {
            const active = d.temporal_active ?? 0;
            const new_def = d.new_physical_defects ?? 0;
            const ex_def = d.existing_tracked ?? 0;
            dbgTemporal.textContent = `Active: ${active} (New: ${new_def} | Ex: ${ex_def})`;
        }
        
        const dbgRejection = document.getElementById("dbgRejection");
        if (dbgRejection) {
            dbgRejection.textContent = d.rejection_summary || "—";
            dbgRejection.style.color = d.rejection_summary ? "var(--accent-amber)" : "var(--text-dim)";
        }

        // Event badge
        if (dbgBadge) {
            const ev = d.event_state || "NONE";
            dbgBadge.textContent = `Event: ${ev}`;
            if (ev === "NEW") {
                dbgBadge.style.color = "var(--accent-rose)";
                dbgBadge.style.borderColor = "rgba(244,63,94,0.4)";
            } else if (ev === "EXISTING") {
                dbgBadge.style.color = "var(--accent-amber)";
                dbgBadge.style.borderColor = "rgba(245,158,11,0.4)";
            } else {
                dbgBadge.style.color = "var(--accent-emerald)";
                dbgBadge.style.borderColor = "rgba(16,185,129,0.3)";
            }
        }
    }

    // Fetch System Status & Hardware Telemetry
    async function fetchSystemStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();

            if (data.telemetry) {
                const tel = data.telemetry;
                statusDevice.textContent = tel.device;
                statusMode.textContent = tel.simulation_mode ? "Simulation Mode" : "Physical Hardware";
                simModeText.textContent = tel.simulation_mode ? "SIMULATION MODE" : "HARDWARE ONLINE";
                statusEsp32.textContent = tel.esp32_message;

                if (tel.simulation_mode) {
                    simModeBadge.style.color = "var(--accent-cyan)";
                } else {
                    simModeBadge.style.color = "var(--accent-emerald)";
                }
            }

            // Populate variables for export reports
            currentHistory = data.history || [];
            
            if (data.stats) {
                currentStats = data.stats;
                statTotal.textContent = data.stats.total_inspected || 0;
                statNormal.textContent = data.stats.normal || 0;
                
                const statSessionDefects = document.getElementById("statSessionDefects");
                if (statSessionDefects) {
                    statSessionDefects.textContent = data.stats.defects || 0;
                }
                
                const statCurrentDefects = document.getElementById("statCurrentDefects");
                if (statCurrentDefects) {
                    statCurrentDefects.textContent = currentDetections.length;
                }

                statHoles.textContent = data.stats.holes || 0;
                statStains.textContent = data.stats.stains || 0;
                statWeaving.textContent = data.stats.weaving_errors || 0;
            }

            // History Log Table
            if (data.history && data.history.length > 0) {
                historyTableBody.innerHTML = "";
                data.history.forEach(item => {
                    const row = document.createElement("tr");
                    // Build a human-readable summary of unique defect types
                    let defectSummary = `${item.count} defect(s)`;
                    if (item.defect_summary) {
                        const parts = Object.entries(item.defect_summary)
                            .map(([cls, cnt]) => `${cls.toUpperCase()} ×${cnt}`);
                        defectSummary = parts.join(", ");
                    }
                    row.innerHTML = `
                        <td>${item.timestamp}</td>
                        <td><strong style="color: var(--color-${item.class.toLowerCase()})">${item.class.toUpperCase()}</strong></td>
                        <td>${item.confidence}%</td>
                        <td>${defectSummary}</td>
                        <td><span class="badge info-badge">Motor Halted</span></td>
                    `;
                    historyTableBody.appendChild(row);
                });
            }
        } catch (e) {
            console.log("Status fetch error:", e);
        }
    }

    // Before/After View Mode Listener
    const viewModeAfter = document.getElementById("viewModeAfter");
    const viewModeBefore = document.getElementById("viewModeBefore");
    if (viewModeAfter && viewModeBefore) {
        viewModeAfter.addEventListener("click", () => {
            viewMode = "after";
            viewModeAfter.classList.add("active");
            viewModeBefore.classList.remove("active");
            renderInspectionCanvas(currentImage, currentDetections);
        });
        viewModeBefore.addEventListener("click", () => {
            viewMode = "before";
            viewModeBefore.classList.add("active");
            viewModeAfter.classList.remove("active");
            renderInspectionCanvas(currentImage, []); // Empty detections hides overlays
        });
    }

    // Save Frame & Export Reports Listeners
    const btnExportCsv = document.getElementById("btnExportCsv");
    const btnExportJson = document.getElementById("btnExportJson");
    const btnSaveFrame = document.getElementById("btnSaveFrame");

    if (btnExportCsv) {
        btnExportCsv.addEventListener("click", () => {
            if (!currentHistory || currentHistory.length === 0) {
                alert("No history log available to export yet!");
                return;
            }
            let csvContent = "data:text/csv;charset=utf-8,";
            csvContent += "Timestamp,Primary Defect Type,Confidence %,Detections Count,All Defects\n";
            currentHistory.forEach(item => {
                const allList = item.all_defects ? item.all_defects.join("; ") : item.class;
                csvContent += `"${item.timestamp}","${item.class}","${item.confidence}","${item.count}","${allList}"\n`;
            });
            const encodedUri = encodeURI(csvContent);
            const link = document.createElement("a");
            link.setAttribute("href", encodedUri);
            link.setAttribute("download", `HFDS_inspection_report_${Date.now()}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }

    if (btnExportJson) {
        btnExportJson.addEventListener("click", () => {
            if (!currentHistory) {
                alert("No session data available to export!");
                return;
            }
            const reportData = {
                session_timestamp: new Date().toLocaleString(),
                stats: currentStats || {},
                history: currentHistory
            };
            const blob = new Blob([JSON.stringify(reportData, null, 4)], { type: "application/json" });
            const link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.download = `HFDS_session_data_${Date.now()}.json`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }

    if (btnSaveFrame) {
        btnSaveFrame.addEventListener("click", () => {
            if (!currentImage) {
                alert("No active fabric image frame to save!");
                return;
            }
            const link = document.createElement("a");
            link.href = canvas.toDataURL("image/jpeg", 0.95);
            link.download = `HFDS_marked_frame_${Date.now()}.jpg`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }

    // Fetch & Render Dataset Sample Images
    async function loadTestDatasetSamples() {
        try {
            const res = await fetch("/api/sample_images");
            const data = await res.json();

            if (data.samples && data.samples.length > 0) {
                samplesContainer.innerHTML = "";
                data.samples.forEach(sample => {
                    const card = document.createElement("div");
                    card.className = "sample-card";
                    card.innerHTML = `
                        <img src="${sample.path}" alt="${sample.class}">
                        <span>${sample.class}</span>
                    `;
                    card.addEventListener("click", () => runSamplePrediction(sample.class, sample.filename, sample.path));
                    samplesContainer.appendChild(card);
                });
            } else {
                samplesContainer.innerHTML = "<p>No test samples found.</p>";
            }
        } catch (e) {
            samplesContainer.innerHTML = "<p>Error loading test samples.</p>";
        }
    }

    // Predict Sample Image Click Handler
    async function runSamplePrediction(clsName, filename, imgPath) {
        stopWebcamStream();
        const img = new Image();
        img.onload = async () => {
            currentImage = img;
            activeDefectIndex = -1; // Reset selection index
            renderInspectionCanvas(img, []);
            setAnalysisState(true); // Show progress overlay

            try {
                const res = await fetch(`/api/predict_sample/${clsName}/${filename}`, { method: "POST" });
                const data = await res.json();

                if (data.success) {
                    currentDetections = data.detections || [];
                    renderInspectionCanvas(img, viewMode === "after" ? currentDetections : []);
                    updateDefectChecklist(currentDetections);
                    updateDashboardUI(data);
                    updateDebugPanel(data);
                    fetchSystemStatus();
                }
            } catch (e) {
                alert("Error predicting sample image: " + e.message);
            } finally {
                setAnalysisState(false); // Hide spinner
            }
        };
        img.src = imgPath;
    }

    // Upload File Prediction Handler
    selectUploadBtn.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", async (e) => {
        if (!e.target.files || e.target.files.length === 0) return;
        handleUploadedFile(e.target.files[0]);
    });

    // Browser Webcam Control
    toggleWebcamBtn.addEventListener("click", () => {
        if (isWebcamActive) {
            stopWebcamStream();
        } else {
            stopOpencvCamStream();
            startWebcamStream();
        }
    });

    // Direct OpenCV Camera Control
    toggleOpencvCamBtn.addEventListener("click", () => {
        if (isOpencvCamActive) {
            stopOpencvCamStream();
        } else {
            stopWebcamStream();
            startOpencvCamStream();
        }
    });

    async function startWebcamStream() {
        try {
            webcamStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
            videoElement = document.createElement("video");
            videoElement.srcObject = webcamStream;
            videoElement.play();

            isWebcamActive = true;
            toggleWebcamBtn.innerHTML = '<i class="fa-solid fa-stop"></i> Stop Browser Webcam';
            toggleWebcamBtn.classList.replace("btn-secondary", "btn-warning");

            webcamInterval = setInterval(async () => {
                if (!isWebcamActive || !videoElement || isProcessingWebcamFrame) return;

                const frameId = ++localFrameCounter;
                isProcessingWebcamFrame = true;

                const tempCanvas = document.createElement("canvas");
                tempCanvas.width = videoElement.videoWidth || 640;
                tempCanvas.height = videoElement.videoHeight || 480;
                const tempCtx = tempCanvas.getContext("2d");
                tempCtx.drawImage(videoElement, 0, 0);

                tempCanvas.toBlob(async (blob) => {
                    const formData = new FormData();
                    formData.append("file", blob, "webcam_frame.jpg");
                    formData.append("frame_id", frameId);

                    const frameImg = new Image();
                    frameImg.onload = async () => {
                        try {
                            const res = await fetch("/api/predict_upload", { method: "POST", body: formData });
                            const data = await res.json();

                            if (data.success && frameId >= lastRenderedFrameId) {
                                lastRenderedFrameId = frameId;
                                currentImage = frameImg;
                                currentDetections = data.detections || [];
                                renderInspectionCanvas(frameImg, currentDetections);
                                updateDefectChecklist(currentDetections);
                                updateDashboardUI(data);
                                updateDebugPanel(data);
                            }
                        } catch (e) {
                            console.log("Webcam predict error:", e);
                        } finally {
                            isProcessingWebcamFrame = false;
                        }
                    };
                    frameImg.src = tempCanvas.toDataURL("image/jpeg");
                }, "image/jpeg", 0.8);
            }, 600);
        } catch (e) {
            console.log("Browser webcam access error:", e);
            alert("Browser webcam access blocked or busy: " + e.message + "\n\nSwitching to Direct Python OpenCV Camera Mode...");
            startOpencvCamStream();
        }
    }

    function stopWebcamStream() {
        if (webcamInterval) clearInterval(webcamInterval);
        if (webcamStream) {
            webcamStream.getTracks().forEach(track => track.stop());
        }
        isWebcamActive = false;
        toggleWebcamBtn.innerHTML = '<i class="fa-solid fa-video"></i> Start Browser Webcam';
        toggleWebcamBtn.classList.replace("btn-warning", "btn-secondary");
    }

    // Direct OpenCV Camera Loop
    async function startOpencvCamStream() {
        isOpencvCamActive = true;
        toggleOpencvCamBtn.innerHTML = '<i class="fa-solid fa-stop"></i> Stop OpenCV Camera';
        toggleOpencvCamBtn.classList.replace("btn-secondary", "btn-warning");

        const pollFrame = async () => {
            if (!isOpencvCamActive || isProcessingWebcamFrame) return;
            isProcessingWebcamFrame = true;
            const frameId = ++localFrameCounter;
            try {
                const res = await fetch(`/api/predict_opencv_camera?frame_id=${frameId}`, { method: "POST" });
                const data = await res.json();

                if (data.success && data.image_b64 && (data.frame_id >= lastRenderedFrameId || frameId >= lastRenderedFrameId)) {
                    lastRenderedFrameId = data.frame_id || frameId;
                    const img = new Image();
                    img.onload = () => {
                        currentImage = img;
                        currentDetections = data.detections || [];
                        renderInspectionCanvas(img, currentDetections);
                        updateDefectChecklist(currentDetections);
                        updateDashboardUI(data);
                        updateDebugPanel(data);
                    };
                    img.src = data.image_b64;
                }
            } catch (err) {
                console.log("OpenCV camera poll error:", err);
            } finally {
                isProcessingWebcamFrame = false;
            }
        };

        pollFrame();
        opencvCamInterval = setInterval(pollFrame, 600);
    }

    function stopOpencvCamStream() {
        if (opencvCamInterval) clearInterval(opencvCamInterval);
        isOpencvCamActive = false;
        toggleOpencvCamBtn.innerHTML = '<i class="fa-solid fa-camera-retro"></i> Direct OpenCV Camera';
        toggleOpencvCamBtn.classList.replace("btn-warning", "btn-secondary");
    }

    // Manual Simulation Motor Stop Trigger Button
    simStopBtn.addEventListener("click", async () => {
        try {
            const res = await fetch("/api/hardware/trigger_stop", { method: "POST" });
            const data = await res.json();
            playDefectSound("hole");
            fetchSystemStatus();
        } catch (e) {
            console.log("Trigger stop error:", e);
        }
    });

    // Settings Modal Event Listeners
    settingsBtn.addEventListener("click", () => settingsModal.classList.remove("hidden"));
    closeSettingsBtn.addEventListener("click", () => settingsModal.classList.add("hidden"));

    confSlider.addEventListener("input", (e) => confVal.textContent = `${e.target.value}%`);
    motorTimeSlider.addEventListener("input", (e) => motorTimeVal.textContent = `${e.target.value}s`);

    const nmsSlider = document.getElementById("nmsSlider");
    const nmsVal = document.getElementById("nmsVal");
    if (nmsSlider && nmsVal) {
        nmsSlider.addEventListener("input", (e) => nmsVal.textContent = `${e.target.value}%`);
    }
    const cooldownSlider = document.getElementById("cooldownSlider");
    const cooldownVal = document.getElementById("cooldownVal");
    if (cooldownSlider && cooldownVal) {
        cooldownSlider.addEventListener("input", (e) => cooldownVal.textContent = `${e.target.value}s`);
    }

    saveSettingsBtn.addEventListener("click", async () => {
        const payload = {
            confidence_threshold: parseFloat(confSlider.value) / 100.0,
            region_size: parseInt(document.getElementById("regionSelect").value),
            overlap: parseFloat(document.getElementById("overlapSelect").value),
            nms_iou_threshold: parseFloat(document.getElementById("nmsSlider")?.value || 30) / 100.0,
            motor_stop_seconds: parseFloat(motorTimeSlider.value),
            motor_cooldown_seconds: parseFloat(document.getElementById("cooldownSlider")?.value || 3),
            audio_enabled: audioToggle.checked,
            simulation_mode: simToggle.checked,
            camera_index: 0
        };

        try {
            await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            settingsModal.classList.add("hidden");
            fetchSystemStatus();
        } catch (e) {
            alert("Error saving settings: " + e.message);
        }
    });

    // ==========================================================================
    // Interactive Tab Switching & Navigation Logic
    // ==========================================================================
    const tabSample = document.getElementById("tabSample");
    const tabUpload = document.getElementById("tabUpload");
    const tabCamera = document.getElementById("tabCamera");
    const samplesCard = document.querySelector(".samples-card");

    const emptyStateMainText = document.getElementById("emptyStateMainText");
    const emptyStateOr = document.getElementById("emptyStateOr");
    const emptyStateSubText = document.getElementById("emptyStateSubText");
    const emptyStateIcon = document.querySelector("#emptyState i");

    function setActiveTab(activeTabId) {
        // Stop any running camera loops if user switches away from camera tab
        if (activeTabId !== "tabCamera") {
            stopWebcamStream();
            stopOpencvCamStream();
        }

        // Toggle Active Tab Classes
        [tabSample, tabUpload, tabCamera].forEach(tab => {
            if (tab) {
                if (tab.id === activeTabId) {
                    tab.classList.add("active");
                } else {
                    tab.classList.remove("active");
                }
            }
        });

        // Hide/Show UI Elements based on Selected Mode
        if (activeTabId === "tabSample") {
            // Samples Mode
            if (samplesCard) samplesCard.classList.remove("hidden");
            if (selectUploadBtn) selectUploadBtn.classList.add("hidden");
            if (toggleWebcamBtn) toggleWebcamBtn.classList.add("hidden");
            if (toggleOpencvCamBtn) toggleOpencvCamBtn.classList.add("hidden");

            // Empty state updates
            if (emptyStateIcon) {
                emptyStateIcon.className = "fa-solid fa-flask drag-icon";
            }
            if (emptyStateMainText) emptyStateMainText.textContent = "Test Dataset Samples Mode";
            if (emptyStateOr) emptyStateOr.classList.add("hidden");
            if (emptyStateSubText) emptyStateSubText.textContent = "Select an untouched test sample below to analyze fabric.";
        } 
        else if (activeTabId === "tabUpload") {
            // Upload Mode
            if (samplesCard) samplesCard.classList.add("hidden");
            if (selectUploadBtn) selectUploadBtn.classList.remove("hidden");
            if (toggleWebcamBtn) toggleWebcamBtn.classList.add("hidden");
            if (toggleOpencvCamBtn) toggleOpencvCamBtn.classList.add("hidden");

            // Empty state updates
            if (emptyStateIcon) {
                emptyStateIcon.className = "fa-solid fa-cloud-arrow-up drag-icon";
            }
            if (emptyStateMainText) emptyStateMainText.textContent = "Drag & Drop Fabric Image Here";
            if (emptyStateOr) emptyStateOr.classList.remove("hidden");
            if (emptyStateSubText) emptyStateSubText.textContent = "Select a test sample below or click 'Browse Image File'";
        } 
        else if (activeTabId === "tabCamera") {
            // Camera Mode
            if (samplesCard) samplesCard.classList.add("hidden");
            if (selectUploadBtn) selectUploadBtn.classList.add("hidden");
            if (toggleWebcamBtn) toggleWebcamBtn.classList.remove("hidden");
            if (toggleOpencvCamBtn) toggleOpencvCamBtn.classList.remove("hidden");

            // Empty state updates
            if (emptyStateIcon) {
                emptyStateIcon.className = "fa-solid fa-camera drag-icon";
            }
            if (emptyStateMainText) emptyStateMainText.textContent = "Live Inspection Mode";
            if (emptyStateOr) emptyStateOr.classList.add("hidden");
            if (emptyStateSubText) emptyStateSubText.textContent = "Start browser webcam or direct OpenCV camera to run live inspection.";
        }
    }

    if (tabSample) tabSample.addEventListener("click", () => setActiveTab("tabSample"));
    if (tabUpload) tabUpload.addEventListener("click", () => setActiveTab("tabUpload"));
    if (tabCamera) tabCamera.addEventListener("click", () => setActiveTab("tabCamera"));

    // Set default initial tab
    setActiveTab("tabSample");

    // ==========================================================================
    // Interactive Drag and Drop Upload logic
    // ==========================================================================
    const viewportWrapper = document.getElementById("viewportWrapper");

    if (viewportWrapper) {
        // Prevent default drag behaviors
        ["dragenter", "dragover", "dragleave", "drop"].forEach(eventName => {
            viewportWrapper.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });

        // Add class to wrapper on dragover
        ["dragenter", "dragover"].forEach(eventName => {
            viewportWrapper.addEventListener(eventName, () => {
                // Only allow drag drop if in upload tab
                setActiveTab("tabUpload");
                viewportWrapper.classList.add("drag-over");
            }, false);
        });

        // Remove class on dragleave
        ["dragleave", "drop"].forEach(eventName => {
            viewportWrapper.addEventListener(eventName, () => {
                viewportWrapper.classList.remove("drag-over");
            }, false);
        });

        // Handle file drop
        viewportWrapper.addEventListener("drop", (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;

            if (files && files.length > 0) {
                handleUploadedFile(files[0]);
            }
        }, false);
    }

    // Helper to process dropped/uploaded file
    async function handleUploadedFile(file) {
        if (!file.type.startsWith("image/")) {
            alert("Please drop an image file!");
            return;
        }

        const formData = new FormData();
        formData.append("file", file);

        const img = new Image();
        img.onload = async () => {
            currentImage = img;
            activeDefectIndex = -1;
            renderInspectionCanvas(img, []);
            updateDefectChecklist([]);
            setAnalysisState(true);

            try {
                const res = await fetch("/api/predict_upload", {
                    method: "POST",
                    body: formData
                });
                const data = await res.json();

                if (data.success) {
                    currentDetections = data.detections || [];
                    renderInspectionCanvas(img, viewMode === "after" ? currentDetections : []);
                    updateDefectChecklist(currentDetections);
                    updateDashboardUI(data);
                    updateDebugPanel(data);
                    fetchSystemStatus();
                }
            } catch (err) {
                alert("Error analyzing dropped image: " + err.message);
            } finally {
                setAnalysisState(false);
            }
        };
        img.src = URL.createObjectURL(file);
    }

    // Periodic Polling
    fetchSystemStatus();
    loadTestDatasetSamples();
    setInterval(fetchSystemStatus, 3000);
});
