"""
FastAPI Backend Server for Handloom AI Defect Detection Web Dashboard.

Provides REST and Streaming APIs for:
1. PyTorch Soft-Voting Ensemble (Custom CNN + ResNet-50) model inference.
2. Overlapping sliding window region inspection with bounding boxes.
3. Live webcam / sample fabric image testing.
4. ESP32 hardware telemetry and Hardware Simulation Mode (for offline testing).
5. Defect statistics, detection history, and probability breakdowns.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import threading
# pyrefly: ignore [missing-import]
import torch
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, File, HTTPException, UploadFile
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse, HTMLResponse
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from PIL import Image

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from scripts.ensemble import build_cnn_model, build_resnet_model
from iot.esp32_controller import ESP32Controller, ESP32Status
from iot.config import (
    ESP32_BASE_URL,
    DEFECT_CONFIDENCE_THRESHOLD,
    GLOBAL_SUPPORT_THRESHOLD,
    MIN_STAIN_DEVIATION,
    GLOBAL_NORMAL_SUPPRESSION_THRESHOLD,
    CONFLICTING_CLASS_THRESHOLD,
    MOTOR_COOLDOWN_SECONDS,
    NMS_IOU_THRESHOLD,
    MIN_DEFECT_AREA_RATIO,
    MAX_DEFECT_COVERAGE_RATIO,
    TEMPORAL_IOU_THRESHOLD,
    TEMPORAL_MEMORY_SECONDS,
)

# Path setup
WEB_DIR = Path(__file__).resolve().parent / "web"
MODELS_DIR = ROOT_DIR / "models"
SOUNDS_DIR = ROOT_DIR / "sounds"
DATASET_DIR = ROOT_DIR / "dataset"

# Global App Setup
app = FastAPI(title="Handloom AI Defect Detection System API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HFDS_GUI_Server")

# Pydantic Schemas
class SettingsModel(BaseModel):
    confidence_threshold: float = Field(DEFECT_CONFIDENCE_THRESHOLD, ge=0.1, le=1.0)
    region_size: int = Field(224, ge=64, le=512)
    overlap: float = Field(0.50, ge=0.0, le=0.9)
    nms_iou_threshold: float = Field(NMS_IOU_THRESHOLD, ge=0.1, le=0.9)
    motor_stop_seconds: float = Field(1.25, ge=0.5, le=10.0)
    motor_cooldown_seconds: float = Field(MOTOR_COOLDOWN_SECONDS, ge=0.0, le=30.0)
    audio_enabled: bool = True
    simulation_mode: bool = True
    camera_index: int = 0


# =========================================================================
# Persistent Background Camera Reader
# =========================================================================
class CameraStreamManager:
    """
    Persistent background OpenCV VideoCapture thread.
    Keeps the camera device open and continuously grabs fresh frames,
    preventing driver-level frame buffer freezing on Windows/DirectShow.
    """
    def __init__(self) -> None:
        self.camera_index = -1
        self.cap = None
        self.latest_frame: np.ndarray | None = None
        self.running = False
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()

    def start(self, camera_index: int = 0) -> None:
        import threading
        with self.lock:
            if self.running and self.camera_index == camera_index:
                return
            self.stop_sync()
            self.camera_index = camera_index
            backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
            self.cap = cv2.VideoCapture(camera_index, backend)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(camera_index)
            if not self.cap.isOpened():
                raise RuntimeError(f"Could not open camera at index {camera_index}")
            self.running = True
            self.thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.thread.start()
            logger.info("Persistent CameraStreamManager started for index %d", camera_index)

    def _reader_loop(self) -> None:
        while self.running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.latest_frame = frame
            else:
                time.sleep(0.01)

    def get_latest_frame(self, camera_index: int = 0) -> np.ndarray:
        if not self.running or self.camera_index != camera_index:
            self.start(camera_index)
        start_t = time.time()
        while time.time() - start_t < 1.5:
            with self.lock:
                if self.latest_frame is not None:
                    return self.latest_frame.copy()
            time.sleep(0.03)
        raise RuntimeError("Timeout waiting for frame from CameraStreamManager")

    def stop_sync(self) -> None:
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        with self.lock:
            self.latest_frame = None


camera_manager = CameraStreamManager()


# =========================================================================
# Temporal Defect Tracker — cross-frame physical defect deduplication
# =========================================================================
class TemporalDefectTracker:
    """
    Maintains a short-term memory of physical defects seen across consecutive
    frames.  Each tracked defect has a class, bounding box, and last-seen
    timestamp.  On each frame the tracker matches current detections against
    the memory using class + IoU, returning whether each detection is NEW
    (first sighting of this physical defect) or EXISTING (continuation).

    Only NEW detections should increment stats, create history entries,
    trigger motor stops, and play audio alerts.
    """

    def __init__(self) -> None:
        self._tracked: List[Dict[str, Any]] = []
        self._next_id: int = 1

    def update(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Match *detections* against tracked memory.  Returns a new list of
        detection dicts, each augmented with:
          - "temporal_status": "NEW" or "EXISTING"
          - "temporal_id":     unique physical defect ID
        Also garbage-collects stale tracked entries.
        """
        now = time.time()

        # 1. Purge stale tracked defects (not seen for TEMPORAL_MEMORY_SECONDS)
        self._tracked = [
            t for t in self._tracked
            if (now - t["last_seen"]) < TEMPORAL_MEMORY_SECONDS
        ]

        matched_track_ids: set = set()
        annotated: List[Dict[str, Any]] = []

        for det in detections:
            best_iou = 0.0
            best_track = None

            for track in self._tracked:
                if track["class"] != det["class"]:
                    continue
                if track["id"] in matched_track_ids:
                    continue  # already matched this frame
                iou = _compute_iou(track["box"], det["box"])
                if iou > best_iou:
                    best_iou = iou
                    best_track = track

            if best_track is not None and best_iou >= TEMPORAL_IOU_THRESHOLD:
                # EXISTING — same physical defect seen before
                best_track["last_seen"] = now
                best_track["box"] = det["box"]  # update position (conveyor drift)
                best_track["confidence"] = det["confidence"]
                matched_track_ids.add(best_track["id"])
                aug = dict(det)
                aug["temporal_status"] = "EXISTING"
                aug["temporal_id"] = best_track["id"]
                annotated.append(aug)
            else:
                # NEW — first sighting of this physical defect
                tid = self._next_id
                self._next_id += 1
                self._tracked.append({
                    "id": tid,
                    "class": det["class"],
                    "box": det["box"],
                    "confidence": det["confidence"],
                    "last_seen": now,
                })
                aug = dict(det)
                aug["temporal_status"] = "NEW"
                aug["temporal_id"] = tid
                annotated.append(aug)

        return annotated

    @property
    def active_count(self) -> int:
        now = time.time()
        return sum(
            1 for t in self._tracked
            if (now - t["last_seen"]) < TEMPORAL_MEMORY_SECONDS
        )

    def reset(self) -> None:
        self._tracked.clear()
        self._next_id = 1


# =========================================================================
# IoU helper (module-level so TemporalDefectTracker can use it)
# =========================================================================
def _compute_iou(boxA: List[int], boxB: List[int]) -> float:
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    if interArea == 0:
        return 0.0

    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

    unionArea = float(boxAArea + boxBArea - interArea)
    return interArea / unionArea if unionArea > 0 else 0.0


# =========================================================================
# Inspection Engine
# =========================================================================
class InspectionEngine:
    def __init__(self) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("Initializing Inspection Engine on device: %s", self.device)

        # Classes mapping
        self.classes = self._load_classes()
        logger.info("Loaded classes: %s", self.classes)

        # Model Loading
        self.cnn_model = None
        self.resnet_model = None
        self.models_loaded = False
        self._load_models()

        # ESP32 Controller & Hardware State
        self.esp32_controller = ESP32Controller(ESP32_BASE_URL)
        self.simulation_mode = True
        self.camera_connected = False
        self.esp32_connected = False

        # Conveyor Motor State
        self.motor_state = "RUNNING"  # "RUNNING" or "STOPPED"
        self.motor_stop_until = 0.0
        self.motor_last_stop_time = 0.0  # timestamp when the last stop event ended

        # Runtime Settings
        self.settings = SettingsModel()

        # Statistics & Detection History
        self.stats = {
            "total_inspected": 0,
            "normal": 0,
            "defects": 0,
            "holes": 0,
            "stains": 0,
            "weaving_errors": 0,
        }
        self.history: List[Dict[str, Any]] = []

        # Audio cooldown timestamp map
        self.last_audio_played: Dict[str, float] = {}

        # Temporal defect tracker — cross-frame physical dedup
        self.temporal_tracker = TemporalDefectTracker()

    def _load_classes(self) -> List[str]:
        classes_file = MODELS_DIR / "resnet50_classes.json"
        if classes_file.exists():
            try:
                with open(classes_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Error reading classes file: %s", e)
        return ["hole", "normal", "stain", "weaving_error"]

    def _load_models(self) -> None:
        try:
            logger.info("Loading Custom CNN weights...")
            self.cnn_model = build_cnn_model(num_classes=len(self.classes), device=self.device)
            self.cnn_model.eval()

            logger.info("Loading ResNet-50 weights...")
            self.resnet_model = build_resnet_model(num_classes=len(self.classes), device=self.device)
            self.resnet_model.eval()

            self.models_loaded = True
            logger.info("Models loaded successfully!")
        except Exception as e:
            logger.error("Failed to load models: %s", e)
            self.models_loaded = False

    def transform_patch(self, img_pil: Image.Image) -> torch.Tensor:
        # Preprocessing standard 224x224 RGB with ImageNet Normalization
        img_resized = img_pil.resize((224, 224), Image.BILINEAR)
        img_np = np.array(img_resized, dtype=np.float32) / 255.0
        # Normalization
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img_norm = (img_np - mean) / std
        # HWC -> CHW -> NCHW
        tensor = torch.from_numpy(img_norm).permute(2, 0, 1).unsqueeze(0).to(self.device)
        return tensor

    def predict_patch(self, img_pil: Image.Image) -> Dict[str, Any]:
        """Runs Custom CNN and ResNet-50 and combines them via Soft Voting."""
        if not self.models_loaded:
            raise RuntimeError("Models not loaded properly")

        tensor = self.transform_patch(img_pil)

        with torch.no_grad():
            cnn_logits = self.cnn_model(tensor)
            resnet_logits = self.resnet_model(tensor)

            cnn_probs = torch.softmax(cnn_logits, dim=1).cpu().numpy()[0]
            resnet_probs = torch.softmax(resnet_logits, dim=1).cpu().numpy()[0]

            # Soft Voting Ensemble Average
            ensemble_probs = (cnn_probs + resnet_probs) / 2.0

        best_idx = int(np.argmax(ensemble_probs))
        predicted_class = self.classes[best_idx]
        confidence = float(ensemble_probs[best_idx])

        cnn_dict = {self.classes[i]: float(cnn_probs[i]) for i in range(len(self.classes))}
        resnet_dict = {self.classes[i]: float(resnet_probs[i]) for i in range(len(self.classes))}
        ensemble_dict = {self.classes[i]: float(ensemble_probs[i]) for i in range(len(self.classes))}

        return {
            "class": predicted_class,
            "confidence": confidence,
            "probabilities": {
                "cnn": cnn_dict,
                "resnet": resnet_dict,
                "ensemble": ensemble_dict,
            },
        }

    def predict_patches_batch(self, crop_pils: List[Image.Image]) -> List[Dict[str, Any]]:
        """Runs Custom CNN and ResNet-50 on a batch of image crops simultaneously to eliminate lag."""
        if not crop_pils or not self.models_loaded:
            return []

        tensors = [self.transform_patch(img) for img in crop_pils]
        batch_tensor = torch.cat(tensors, dim=0)

        with torch.no_grad():
            cnn_logits = self.cnn_model(batch_tensor)
            resnet_logits = self.resnet_model(batch_tensor)

            cnn_probs = torch.softmax(cnn_logits, dim=1).cpu().numpy()
            resnet_probs = torch.softmax(resnet_logits, dim=1).cpu().numpy()

            # Soft Voting Ensemble Average
            ensemble_probs = (cnn_probs + resnet_probs) / 2.0

        results = []
        for b in range(len(crop_pils)):
            best_idx = int(np.argmax(ensemble_probs[b]))
            predicted_class = self.classes[best_idx]
            confidence = float(ensemble_probs[b, best_idx])

            cnn_dict = {self.classes[i]: float(cnn_probs[b, i]) for i in range(len(self.classes))}
            resnet_dict = {self.classes[i]: float(resnet_probs[b, i]) for i in range(len(self.classes))}
            ensemble_dict = {self.classes[i]: float(ensemble_probs[b, i]) for i in range(len(self.classes))}

            results.append({
                "class": predicted_class,
                "confidence": confidence,
                "probabilities": {
                    "cnn": cnn_dict,
                    "resnet": resnet_dict,
                    "ensemble": ensemble_dict,
                },
            })
        return results

    # =====================================================================
    # Main frame inspection pipeline
    # =====================================================================
    def inspect_image_numpy(
        self,
        frame_bgr: np.ndarray,
        frame_id: int | None = None,
        timestamp: str | None = None,
    ) -> Dict[str, Any]:
        """
        Runs sliding-window overlapping region inspection over an image frame
        using fast PyTorch batching.  Applies:
          1. Global full-frame ensemble prediction
          2. Regional sliding-window patch inference
          3. Class-specific CV localization inside each patch
          4. Spatial NMS duplicate suppression
          5. Temporal cross-frame physical defect deduplication
        """
        start_time = time.time()
        fid = frame_id or int(start_time * 1000)
        ts = timestamp or datetime.now().strftime("%H:%M:%S.%f")[:-3]

        h_orig, w_orig = frame_bgr.shape[:2]

        # Resize to standard working resolution for consistent inference speed
        max_dim = 640
        if max(h_orig, w_orig) > max_dim:
            scale = max_dim / float(max(h_orig, w_orig))
            w_work = max(64, int(w_orig * scale))
            h_work = max(64, int(h_orig * scale))
            frame_work = cv2.resize(frame_bgr, (w_work, h_work), interpolation=cv2.INTER_AREA)
        else:
            frame_work = frame_bgr.copy()
            w_work, h_work = w_orig, h_orig

        frame_rgb = cv2.cvtColor(frame_work, cv2.COLOR_BGR2RGB)
        img_full_pil = Image.fromarray(frame_rgb)

        # ---- Step 1: Full-frame global prediction ----
        global_result = self.predict_patch(img_full_pil)
        global_pred = global_result["class"]
        global_conf = global_result["confidence"]
        global_probs = global_result["probabilities"]["ensemble"]
        global_stain_conf = float(global_probs.get("stain", 0.0))

        # ---- Step 2: Sliding Window Overlapping Region Detections ----
        region_size = self.settings.region_size
        overlap = self.settings.overlap
        stride = max(16, int(round(region_size * (1.0 - overlap))))

        crop_pils = []
        crop_coords = []

        for y in range(0, max(1, h_work - region_size + 1), stride):
            for x in range(0, max(1, w_work - region_size + 1), stride):
                crop_box = (x, y, min(w_work, x + region_size), min(h_work, y + region_size))
                crop_pils.append(img_full_pil.crop(crop_box))
                crop_coords.append((x, y))

        raw_region_count = len(crop_pils)

        # Perform fast batch inference
        predictions = self.predict_patches_batch(crop_pils)

        raw_detections = []
        loc_rejected_count = 0
        rejection_reasons: List[str] = []
        scale_x = w_orig / float(w_work)
        scale_y = h_orig / float(h_work)

        for (x, y), pred in zip(crop_coords, predictions):
            class_name = pred["class"]
            conf = pred["confidence"]
            ens_probs = pred["probabilities"]["ensemble"]

            # ---- Regional candidate threshold logic ----
            # Standard threshold from settings
            min_thresh = self.settings.confidence_threshold

            # If global prediction is a defect class AND this patch's
            # prediction for that same class exceeds GLOBAL_SUPPORT_THRESHOLD,
            # use the lower threshold to catch small defects that occupy
            # a tiny fraction of the 224×224 crop.
            target_class = class_name
            if (global_pred != "normal"
                    and global_conf >= 0.65
                    and class_name != global_pred):
                # Check if the patch shows support for the global defect class
                global_cls_patch_conf = float(ens_probs.get(global_pred, 0.0))
                if global_cls_patch_conf >= GLOBAL_SUPPORT_THRESHOLD:
                    target_class = global_pred
                    conf = global_cls_patch_conf
                    min_thresh = GLOBAL_SUPPORT_THRESHOLD

            # Skip normal patches
            if target_class == "normal":
                continue
            if conf < min_thresh:
                continue

            # ---- Global context filtering ----
            # 1. If global frame prediction is NORMAL with high confidence (>= 0.80),
            # require higher candidate confidence (>= 0.75) to prevent weak regional
            # false positives on clean fabric.
            if global_pred == "normal" and global_conf >= GLOBAL_NORMAL_SUPPRESSION_THRESHOLD:
                if conf < 0.75:
                    logger.debug(
                        "Regional candidate %s %.0f%% REJECTED by high-confidence "
                        "global NORMAL context (%.0f%%)",
                        target_class, conf * 100, global_conf * 100,
                    )
                    continue

            # 2. If regional class conflicts with non-normal global prediction,
            # require candidate confidence >= 0.70
            if global_pred != "normal" and target_class != global_pred:
                if conf < CONFLICTING_CLASS_THRESHOLD:
                    logger.debug(
                        "Regional candidate %s %.0f%% REJECTED due to conflict "
                        "with global %s (%.0f%%)",
                        target_class, conf * 100, global_pred, global_conf * 100,
                    )
                    continue

            # ---- Step 3: Class-specific CV localization ----
            rx1 = x
            ry1 = y
            rx2 = min(w_work, x + region_size)
            ry2 = min(h_work, y + region_size)

            patch_bgr = frame_work[ry1:ry2, rx1:rx2]

            local_box, reject_reason = self._refine_defect_box(
                patch_bgr, target_class, global_stain_conf=global_stain_conf
            )

            if local_box is None:
                loc_rejected_count += 1
                if reject_reason:
                    rejection_reasons.append(
                        f"{target_class} {conf*100:.0f}% @ ({rx1},{ry1}): {reject_reason}"
                    )
                logger.debug(
                    "Detection SKIPPED: %s %.0f%% — %s",
                    target_class, conf * 100, reject_reason or "localisation returned None",
                )
                continue

            # ---- Step 4: Scale coordinates back to original image ----
            bx1 = int((rx1 + local_box[0]) * scale_x)
            by1 = int((ry1 + local_box[1]) * scale_y)
            bx2 = int((rx1 + local_box[2]) * scale_x)
            by2 = int((ry1 + local_box[3]) * scale_y)

            # Clamp to image bounds
            bx1 = max(0, min(bx1, w_orig))
            by1 = max(0, min(by1, h_orig))
            bx2 = max(0, min(bx2, w_orig))
            by2 = max(0, min(by2, h_orig))

            raw_detections.append({
                "class": target_class,
                "confidence": conf,
                "box": [bx1, by1, bx2, by2],
                "probabilities": pred["probabilities"],
            })

        accepted_count = len(raw_detections)

        # ---- Step 5: Spatial NMS duplicate suppression ----
        filtered_detections = self._nms_suppression(raw_detections)
        unique_count = len(filtered_detections)

        # ---- Step 6: Temporal cross-frame deduplication ----
        temporal_detections = self.temporal_tracker.update(filtered_detections)

        new_defects = [d for d in temporal_detections if d.get("temporal_status") == "NEW"]
        existing_defects = [d for d in temporal_detections if d.get("temporal_status") == "EXISTING"]

        logger.info(
            "Frame analysis: Raw regions: %d | Accepted: %d | "
            "Unique spatial: %d | NEW physical: %d | EXISTING: %d",
            raw_region_count, accepted_count, unique_count,
            len(new_defects), len(existing_defects),
        )

        # ---- Motor control ----
        now = time.time()
        if now < self.motor_stop_until:
            self.motor_state = "STOPPED"
        else:
            self.motor_state = "RUNNING"

        defect_found = unique_count > 0
        audio_trigger = None
        event_state = "NONE"

        # Only trigger motor stop and audio for NEW physical defects
        if new_defects:
            first_new = new_defects[0]
            audio_trigger = first_new["class"]
            event_state = "NEW"

            cooldown_elapsed = (now - self.motor_last_stop_time) >= self.settings.motor_cooldown_seconds
            if self.motor_state == "RUNNING" and cooldown_elapsed:
                self._trigger_motor_stop()

            # Record history entry — ONLY for NEW physical defects
            defect_type_counts: Dict[str, int] = {}
            for det in new_defects:
                defect_type_counts[det["class"]] = defect_type_counts.get(det["class"], 0) + 1

            history_entry = {
                "id": str(int(time.time() * 1000)),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "class": first_new["class"],
                "confidence": round(first_new["confidence"] * 100, 1),
                "count": len(new_defects),
                "all_defects": [d["class"] for d in new_defects],
                "defect_summary": defect_type_counts,
            }
            self.history.insert(0, history_entry)
            if len(self.history) > 30:
                self.history.pop()

            # Update stats — count ONLY new physical defects
            self.stats["total_inspected"] += 1
            self.stats["defects"] += len(new_defects)
            for det in new_defects:
                cls = det["class"]
                if cls == "hole":
                    self.stats["holes"] += 1
                elif cls == "stain":
                    self.stats["stains"] += 1
                elif cls == "weaving_error":
                    self.stats["weaving_errors"] += 1

        elif defect_found and not new_defects:
            # All detections are EXISTING — same physical defects continuing
            event_state = "EXISTING"
            self.stats["total_inspected"] += 1
        else:
            event_state = "NONE"
            self.stats["total_inspected"] += 1
            self.stats["normal"] += 1

        remaining_stop_seconds = max(0.0, round(self.motor_stop_until - now, 1))

        # ---- Verified prediction status ----
        if defect_found:
            # Use the highest-confidence verified detection
            best_det = max(temporal_detections, key=lambda d: d["confidence"])
            verified_prediction = best_det["class"]
        elif global_pred != "normal" and not defect_found:
            verified_prediction = "uncertain"
        else:
            verified_prediction = "normal"

        processing_time_ms = round((time.time() - start_time) * 1000, 1)

        cnn_top = max(global_result["probabilities"]["cnn"], key=global_result["probabilities"]["cnn"].get)
        resnet_top = max(global_result["probabilities"]["resnet"], key=global_result["probabilities"]["resnet"].get)

        # Build rejection diagnostics summary
        rejection_summary = ""
        if loc_rejected_count > 0 and not defect_found:
            rejection_summary = (
                f"Global: {global_pred.upper()} ({global_conf*100:.0f}%) — "
                f"{loc_rejected_count} candidate(s) rejected by localization"
            )
            if rejection_reasons:
                rejection_summary += f" | Top reason: {rejection_reasons[0]}"

        return {
            "success": True,
            "frame_id": fid,
            "timestamp": ts,
            "processing_time_ms": processing_time_ms,
            "global_prediction": global_pred,
            "global_confidence": round(global_conf * 100, 1),
            "verified_prediction": verified_prediction,
            "probabilities": global_result["probabilities"],
            "detections": temporal_detections,
            "defect_detected": defect_found,
            "audio_alert": audio_trigger,
            "motor_state": self.motor_state,
            "motor_stop_remaining": remaining_stop_seconds,
            "stats": self.stats,
            "debug": {
                "frame_id": fid,
                "processing_time_ms": processing_time_ms,
                "raw_regions": raw_region_count,
                "accepted_predictions": accepted_count,
                "localization_rejected": loc_rejected_count,
                "unique_defects": unique_count,
                "new_physical_defects": len(new_defects),
                "existing_tracked": len(existing_defects),
                "temporal_active": self.temporal_tracker.active_count,
                "event_state": event_state,
                "cnn_top": f"{cnn_top.upper()} ({round(global_result['probabilities']['cnn'][cnn_top]*100,1)}%)",
                "resnet_top": f"{resnet_top.upper()} ({round(global_result['probabilities']['resnet'][resnet_top]*100,1)}%)",
                "ensemble_top": f"{global_pred.upper()} ({round(global_conf*100,1)}%)",
                "rejection_summary": rejection_summary,
            },
        }

    def _trigger_motor_stop(self) -> None:
        """Send ONE stop command for the current defect event."""
        now = time.time()
        self.motor_state = "STOPPED"
        self.motor_stop_until = now + self.settings.motor_stop_seconds
        self.motor_last_stop_time = now  # updated again when motor restarts

        logger.info("Motor stop triggered — will resume in %.1fs", self.settings.motor_stop_seconds)

        if not self.simulation_mode and self.esp32_connected:
            try:
                self.esp32_controller.stop_motors()
            except Exception as e:
                logger.warning("ESP32 stop signal failed: %s", e)

    # =====================================================================
    # Spatial NMS — Weighted Bounding Box Fusion
    # =====================================================================
    def _nms_suppression(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Spatial duplicate suppression using Weighted Bounding Box Fusion.

        Groups overlapping or nearby same-class detections into clusters,
        then merges each cluster into a single representative detection
        whose coordinates are the confidence-weighted average of the cluster.
        """
        if not detections:
            return []

        iou_threshold = self.settings.nms_iou_threshold

        # Sort detections by confidence descending
        detections = sorted(detections, key=lambda d: d["confidence"], reverse=True)

        # Calculate merge distance dynamically from detection box size
        avg_w = sum(d["box"][2] - d["box"][0] for d in detections) / len(detections)
        avg_h = sum(d["box"][3] - d["box"][1] for d in detections) / len(detections)
        merge_distance = max(avg_w, avg_h)

        clusters: List[List[Dict[str, Any]]] = []

        for det in detections:
            assigned = False
            bx1, by1, bx2, by2 = det["box"]
            cx = (bx1 + bx2) / 2.0
            cy = (by1 + by2) / 2.0

            for cluster in clusters:
                if cluster[0]["class"] != det["class"]:
                    continue

                overlaps = False
                for member in cluster:
                    iou = _compute_iou(member["box"], det["box"])
                    if iou >= iou_threshold:
                        overlaps = True
                        break

                    mx1, my1, mx2, my2 = member["box"]
                    mcx = (mx1 + mx2) / 2.0
                    mcy = (my1 + my2) / 2.0
                    dist = ((cx - mcx) ** 2 + (cy - mcy) ** 2) ** 0.5
                    if dist < merge_distance:
                        overlaps = True
                        break

                if overlaps:
                    cluster.append(det)
                    assigned = True
                    break

            if not assigned:
                clusters.append([det])

        merged_detections = []
        for cluster in clusters:
            total_weight = sum(item["confidence"] for item in cluster)

            x1 = sum(item["box"][0] * item["confidence"] for item in cluster) / total_weight
            y1 = sum(item["box"][1] * item["confidence"] for item in cluster) / total_weight
            x2 = sum(item["box"][2] * item["confidence"] for item in cluster) / total_weight
            y2 = sum(item["box"][3] * item["confidence"] for item in cluster) / total_weight

            max_conf = max(item["confidence"] for item in cluster)
            representative = cluster[0]

            avg_probs = {}
            for model_key in ["cnn", "resnet", "ensemble"]:
                if model_key in representative["probabilities"]:
                    model_avg = {}
                    for class_name in representative["probabilities"][model_key]:
                        sum_val = sum(item["probabilities"][model_key][class_name] for item in cluster)
                        model_avg[class_name] = sum_val / len(cluster)
                    avg_probs[model_key] = model_avg

            merged_detections.append({
                "class": representative["class"],
                "confidence": max_conf,
                "box": [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))],
                "probabilities": avg_probs,
            })

        return merged_detections

    # =====================================================================
    # Class-specific CV Localization
    # =====================================================================
    def _refine_defect_box(
        self,
        patch_bgr: np.ndarray,
        class_name: str,
        global_stain_conf: float = 0.0,
    ) -> tuple:
        """
        Refines a coarse patch bounding box by using classical image processing
        to tightly segment/localize the defect inside the patch.

        Returns:
            (local_box, None)          on success — local_box = [x1, y1, x2, y2]
            (None, rejection_reason)   on failure — detection should be rejected
        """
        h, w = patch_bgr.shape[:2]
        patch_area = h * w

        if class_name.lower() == "normal":
            return [0, 0, w, h], None

        gray = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2GRAY)
        combined = None  # binary mask for contour extraction

        # =================================================================
        # STAIN localization — Lab colour deviation with robust background
        # =================================================================
        if class_name.lower() == "stain":
            lab = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2Lab)

            # Robust background estimation: use corner pixels instead of
            # global median so the stain itself doesn't skew the estimate.
            corner_size = max(8, min(h // 6, w // 6))
            corners = np.concatenate([
                lab[:corner_size, :corner_size].reshape(-1, 3),
                lab[:corner_size, -corner_size:].reshape(-1, 3),
                lab[-corner_size:, :corner_size].reshape(-1, 3),
                lab[-corner_size:, -corner_size:].reshape(-1, 3),
            ], axis=0)
            bg_color = np.median(corners, axis=0).astype(np.uint8)

            # Per-pixel absolute deviation from background
            diff = cv2.absdiff(lab, bg_color)
            diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

            # Bilateral filter preserves edges while smoothing normal texture
            blurred = cv2.bilateralFilter(diff_gray, 9, 40, 40)

            # Adaptive deviation requirement
            effective_stain_dev = MIN_STAIN_DEVIATION
            if global_stain_conf >= 0.70:
                effective_stain_dev = max(4, int(MIN_STAIN_DEVIATION * 0.50))
            elif global_stain_conf >= 0.45:
                effective_stain_dev = max(5, int(MIN_STAIN_DEVIATION * 0.65))

            p90_deviation = float(np.percentile(blurred, 90))
            if p90_deviation < effective_stain_dev:
                return None, f"p90 deviation {p90_deviation:.1f} < threshold {effective_stain_dev} (uniform fabric)"

            # Adaptive thresholding instead of blind Otsu
            _, combined = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Morphological cleanup: remove tiny dots, connect nearby regions
            kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel_open)
            kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel_close)

        # =================================================================
        # HOLE localization — adaptive dark region detection
        # =================================================================
        elif class_name.lower() == "hole":
            # Holes are dark/high-contrast regions relative to fabric
            blurred = cv2.medianBlur(gray, 5)

            # Corner-based background brightness estimation
            corner_size = max(8, min(h // 6, w // 6))
            corners = np.concatenate([
                blurred[:corner_size, :corner_size].ravel(),
                blurred[:corner_size, -corner_size:].ravel(),
                blurred[-corner_size:, :corner_size].ravel(),
                blurred[-corner_size:, -corner_size:].ravel(),
            ])
            bg_brightness = float(np.median(corners))

            # Threshold: significantly darker than background
            thresh_val = max(10, int(bg_brightness * 0.60))
            _, thresh_dark = cv2.threshold(blurred, thresh_val, 255, cv2.THRESH_BINARY_INV)

            # Edge detection to capture sharp hole boundaries
            edges = cv2.Canny(blurred, 40, 120)

            combined = cv2.bitwise_or(thresh_dark, edges)

            # Morphological closing to connect fragmented regions
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

        # =================================================================
        # WEAVING_ERROR localization — texture anomaly detection
        # =================================================================
        elif class_name.lower() == "weaving_error":
            # Weaving errors disrupt the uniform repetitive pattern.
            # Use local variance to find high-variation anomalies.
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Compute local standard deviation using box filter
            gray_f = blurred.astype(np.float32)
            mean_sq = cv2.blur(gray_f ** 2, (15, 15))
            sq_mean = cv2.blur(gray_f, (15, 15)) ** 2
            local_var = np.sqrt(np.maximum(mean_sq - sq_mean, 0))

            # Normalize variance map to 0-255
            if local_var.max() > 0:
                var_norm = (local_var / local_var.max() * 255).astype(np.uint8)
            else:
                return None, "zero local variance (completely uniform patch)"

            # Otsu threshold on variance map
            _, combined = cv2.threshold(var_norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Also add Canny edges for structural boundaries
            edges = cv2.Canny(blurred, 30, 100)
            combined = cv2.bitwise_or(combined, edges)

            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            combined = cv2.dilate(combined, kernel, iterations=1)
            combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

        else:
            return None, f"unknown defect class: {class_name}"

        # =================================================================
        # Contour extraction and box validation (common for all classes)
        # =================================================================
        if combined is None:
            return None, "no binary mask produced"

        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None, "no contours found in binary mask"

        # Filter out extremely small contours (noise)
        min_area_px = max(20, int(patch_area * MIN_DEFECT_AREA_RATIO))
        valid_contours = [c for c in contours if cv2.contourArea(c) > min_area_px]

        if not valid_contours:
            return None, f"all {len(contours)} contour(s) below min area {min_area_px}px"

        # For stain: pick the largest contour (or top-2) to focus on the
        # actual stain region, not scattered noise
        if class_name.lower() == "stain":
            valid_contours = sorted(valid_contours, key=cv2.contourArea, reverse=True)[:3]

        # Compute bounding box enclosing all valid contours
        x1s, y1s, x2s, y2s = [], [], [], []
        for c in valid_contours:
            bx, by, bw, bh = cv2.boundingRect(c)
            x1s.append(bx)
            y1s.append(by)
            x2s.append(bx + bw)
            y2s.append(by + bh)

        lx1, ly1, lx2, ly2 = min(x1s), min(y1s), max(x2s), max(y2s)

        # Padding (6px each side)
        pad = 6
        lx1 = max(0, lx1 - pad)
        ly1 = max(0, ly1 - pad)
        lx2 = min(w, lx2 + pad)
        ly2 = min(h, ly2 + pad)

        box_w = lx2 - lx1
        box_h = ly2 - ly1

        # ---- Validation: minimum box size ----
        if box_w < 12 or box_h < 12:
            return None, f"refined box too small ({box_w}×{box_h}px)"

        # ---- Validation: maximum coverage ratio ----
        box_area = box_w * box_h
        coverage = box_area / patch_area if patch_area > 0 else 1.0
        if coverage >= MAX_DEFECT_COVERAGE_RATIO:
            return None, (
                f"refined box covers {coverage*100:.0f}% of patch "
                f"(>{MAX_DEFECT_COVERAGE_RATIO*100:.0f}% — likely texture noise)"
            )

        return [lx1, ly1, lx2, ly2], None

    # =====================================================================
    # Camera capture
    # =====================================================================
    def capture_opencv_frame(self, camera_index: int = 0, frame_id: int | None = None) -> Dict[str, Any]:
        """Captures a fresh live frame using the persistent CameraStreamManager background thread."""
        frame_bgr = camera_manager.get_latest_frame(camera_index)
        result = self.inspect_image_numpy(frame_bgr, frame_id=frame_id)
        _, buffer = cv2.imencode(".jpg", frame_bgr)
        img_b64 = base64.b64encode(buffer).decode("utf-8")
        result["image_b64"] = f"data:image/jpeg;base64,{img_b64}"
        return result

    def check_hardware_telemetry(self) -> Dict[str, Any]:
        """Poll physical ESP32 or return hardware simulation state."""
        if self.simulation_mode:
            self.esp32_connected = True
            esp_status_msg = "SIMULATED (Offline Testing Active)"
        else:
            try:
                esp_status = self.esp32_controller.get_status()
                self.esp32_connected = esp_status.connected
                esp_status_msg = esp_status.message
            except Exception:
                self.esp32_connected = False
                esp_status_msg = "Disconnected"

        now = time.time()
        if now < self.motor_stop_until:
            self.motor_state = "STOPPED"
        else:
            if self.motor_state == "STOPPED":
                # Motor just restarted — record the time for cooldown logic
                self.motor_last_stop_time = now
            self.motor_state = "RUNNING"

        return {
            "device": str(self.device).upper(),
            "models_loaded": self.models_loaded,
            "simulation_mode": self.simulation_mode,
            "camera_connected": self.camera_connected,
            "esp32_connected": self.esp32_connected,
            "esp32_message": esp_status_msg,
            "motor_state": self.motor_state,
            "motor_stop_remaining": max(0.0, round(self.motor_stop_until - now, 1)),
            "classes": self.classes,
        }


# Initialize Global Engine Instance
engine = InspectionEngine()


# API Endpoints
@app.get("/api/status")
def get_system_status():
    telemetry = engine.check_hardware_telemetry()
    return {
        "status": "ONLINE",
        "telemetry": telemetry,
        "settings": engine.settings.dict(),
        "stats": engine.stats,
        "history": engine.history[:10],
    }


@app.post("/api/settings")
def update_settings(new_settings: SettingsModel):
    engine.settings = new_settings
    engine.simulation_mode = new_settings.simulation_mode
    logger.info("Updated settings: %s", engine.settings.dict())
    return {"status": "SUCCESS", "settings": engine.settings.dict()}


@app.post("/api/predict_upload")
async def predict_upload_file(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        img_pil = Image.open(io.BytesIO(contents)).convert("RGB")
        frame_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

        result = engine.inspect_image_numpy(frame_bgr)
        return result
    except Exception as e:
        logger.error("Upload prediction error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sample_images")
def get_sample_images():
    """Finds test set fabric images for user testing."""
    samples = []

    test_path = DATASET_DIR / "test"
    if test_path.exists():
        for cls_folder in test_path.iterdir():
            if cls_folder.is_dir():
                cls_name = cls_folder.name
                images = [f.name for f in cls_folder.glob("*.*") if f.suffix.lower() in [".jpg", ".jpeg", ".png"]]
                for img in images[:5]:
                    samples.append({
                        "class": cls_name,
                        "filename": img,
                        "path": f"/api/sample_image_file/{cls_name}/{img}"
                    })

    return {"samples": samples}


@app.get("/api/sample_image_file/{cls_name}/{filename}")
def serve_sample_image_file(cls_name: str, filename: str):
    file_path = DATASET_DIR / "test" / cls_name / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Sample image not found")
    return FileResponse(file_path)


@app.post("/api/predict_sample/{cls_name}/{filename}")
def predict_sample(cls_name: str, filename: str):
    file_path = DATASET_DIR / "test" / cls_name / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Sample image not found")

    frame_bgr = cv2.imread(str(file_path))
    if frame_bgr is None:
        raise HTTPException(status_code=400, detail="Could not read image file")

    result = engine.inspect_image_numpy(frame_bgr)
    return result


@app.post("/api/hardware/toggle_simulation")
def toggle_simulation():
    engine.simulation_mode = not engine.simulation_mode
    engine.settings.simulation_mode = engine.simulation_mode
    return {"simulation_mode": engine.simulation_mode}


@app.post("/api/hardware/trigger_stop")
def trigger_manual_stop():
    engine._trigger_motor_stop()
    return {"status": "SUCCESS", "motor_state": engine.motor_state, "remaining": engine.settings.motor_stop_seconds}


@app.post("/api/predict_opencv_camera")
def predict_opencv_camera(camera_index: int = 0, frame_id: int | None = None):
    try:
        result = engine.capture_opencv_frame(camera_index=camera_index, frame_id=frame_id)
        return result
    except Exception as e:
        logger.error("OpenCV camera capture error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# Serve Static Web UI Files
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    index_html = WEB_DIR / "index.html"
    if index_html.exists():
        return HTMLResponse(content=index_html.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Handloom AI Dashboard Web UI loading...</h2>")


if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
