from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
# pyrefly: ignore [missing-import]
import torch
from PIL import Image
# pyrefly: ignore [missing-import]
from torchvision import transforms

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from scripts.ensemble import build_cnn_model, build_resnet_model

try:
    import winsound
except ImportError:  # pragma: no cover - fallback for non-Windows
    winsound = None

try:
    from iot.config import (
        AUDIO_COOLDOWN_SECONDS,
        AUDIO_ENABLED,
        LIVE_CONFIDENCE_THRESHOLD,
        LIVE_OVERLAP,
        LIVE_REGION_SIZE,
        NMS_IOU_THRESHOLD,
        SOUNDS_DIR,
    )
except ImportError:  # pragma: no cover - fallback for direct execution
    AUDIO_ENABLED = True
    AUDIO_COOLDOWN_SECONDS = 2.0
    LIVE_REGION_SIZE = 224
    LIVE_OVERLAP = 0.50
    LIVE_CONFIDENCE_THRESHOLD = 0.65
    NMS_IOU_THRESHOLD = 0.30
    SOUNDS_DIR = ROOT / "sounds"

MODELS_DIR = ROOT / "models"


def load_class_names() -> List[str]:
    classes_path = MODELS_DIR / "resnet50_classes.json"
    if classes_path.exists():
        return json.loads(classes_path.read_text(encoding="utf-8"))
    return ["hole", "normal", "stain", "weaving_error"]


def build_transform() -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


class LiveInspectionRunner:
    def __init__(
        self,
        camera_index: int = 0,
        device: torch.device | None = None,
        region_size: int = LIVE_REGION_SIZE,
        stride: int | None = None,
        overlap: float = LIVE_OVERLAP,
        confidence_threshold: float = LIVE_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.classes = load_class_names()
        self.transform = build_transform()
        self.cnn_model = build_cnn_model(num_classes=len(self.classes), device=self.device)
        self.resnet_model = build_resnet_model(num_classes=len(self.classes), device=self.device)
        self.cnn_model.eval()
        self.resnet_model.eval()
        self.camera_index = camera_index
        self.region_size = max(64, region_size)
        self.overlap = overlap
        self.confidence_threshold = confidence_threshold
        self.stride = stride if stride is not None else max(1, int(round(self.region_size * (1 - overlap))))
        self.audio_enabled = AUDIO_ENABLED
        self.audio_cooldown_seconds = AUDIO_COOLDOWN_SECONDS
        self.last_audio_play_time: Dict[str, float] = {}
        self.stats = {
            "total_inspected": 0,
            "normal": 0,
            "defects": 0,
            "holes": 0,
            "stains": 0,
            "weaving_errors": 0,
        }
        self.history: List[Tuple[str, float, str]] = []
        self.sounds_dir = Path(SOUNDS_DIR)

    def _prepare_frame(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        if width > 640 or height > 480:
            scale = min(640 / width, 480 / height)
            new_width = max(320, int(width * scale))
            new_height = max(240, int(height * scale))
            return cv2.resize(frame, (new_width, new_height))
        return frame

    def predict_frame(self, frame: np.ndarray) -> Tuple[str, float, Dict[str, float]]:
        resized_frame = self._prepare_frame(frame)
        rgb_image = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_image)
        tensor = self.transform(pil_image).unsqueeze(0).to(self.device)

        with torch.inference_mode():
            cnn_logits = self.cnn_model(tensor)
            resnet_logits = self.resnet_model(tensor)

        cnn_probs = torch.softmax(cnn_logits, dim=1)[0].cpu().tolist()
        resnet_probs = torch.softmax(resnet_logits, dim=1)[0].cpu().tolist()
        ensemble_probs = [(cnn + resnet) / 2.0 for cnn, resnet in zip(cnn_probs, resnet_probs)]

        probabilities = {cls: float(score) for cls, score in zip(self.classes, ensemble_probs)}
        predicted_class = max(probabilities, key=probabilities.get)
        confidence = probabilities[predicted_class]
        return predicted_class, confidence, probabilities

    def _generate_regions(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        height, width = frame.shape[:2]
        regions: List[Tuple[int, int, int, int]] = []
        y = 0
        while y < height:
            x = 0
            while x < width:
                region_h = min(self.region_size, height - y)
                region_w = min(self.region_size, width - x)
                regions.append((x, y, region_w, region_h))
                if region_w < self.region_size:
                    break
                x += self.stride
            if region_h < self.region_size:
                break
            y += self.stride
        return regions

    @staticmethod
    def _iou(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = box_a
        bx, by, bw, bh = box_b
        inter_x1 = max(ax, bx)
        inter_y1 = max(ay, by)
        inter_x2 = min(ax + aw, bx + bw)
        inter_y2 = min(ay + ah, by + bh)
        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0
        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        union_area = aw * ah + bw * bh - inter_area
        return inter_area / union_area if union_area > 0 else 0.0

    def _refine_defect_box(self, patch_bgr: np.ndarray, class_name: str) -> List[int]:
        """
        Refines a coarse patch bounding box by using classical image processing
        to tightly segment/localize the defect inside the patch.
        Returns local [x1, y1, x2, y2] relative to the patch.
        """
        h, w = patch_bgr.shape[:2]
        default_box = [0, 0, w, h]

        if class_name == "normal" or class_name == "Normal":
            return default_box

        # Convert to grayscale
        gray = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2GRAY)
        
        if class_name.lower() == "hole":
            # Holes are typically dark/high-contrast.
            # Apply median blur to reduce fabric texture noise.
            blurred = cv2.medianBlur(gray, 5)
            # Threshold to find dark regions (below a fraction of the median brightness)
            median_val = np.median(blurred)
            thresh_val = max(10, int(median_val * 0.70))
            _, thresh = cv2.threshold(blurred, thresh_val, 255, cv2.THRESH_BINARY_INV)
            
            # Also try Canny edge detection to capture high contrast boundaries
            edges = cv2.Canny(blurred, 30, 150)
            combined = cv2.bitwise_or(thresh, edges)
        
        elif class_name.lower() == "stain":
            # Stains represent color/brightness deviation from the background fabric.
            # Convert to L*a*b* to capture color and luminosity differences
            lab = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2Lab)
            # Calculate deviation from the median color of the patch
            median_color = np.median(lab, axis=(0, 1))
            diff = cv2.absdiff(lab, np.uint8(median_color))
            # Sum color deviations
            diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(diff_gray, (5, 5), 0)
            # Threshold deviation via Otsu
            _, combined = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
        elif class_name.lower() == "weaving_error":
            # Weaving errors disrupt the uniform pattern.
            # Use Sobel filter or Canny to get edge map
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 20, 100)
            # Dilate edges to merge nearby structural elements
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            combined = cv2.dilate(edges, kernel, iterations=2)
            
        else:
            combined = gray

        # Find contours
        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return default_box

        # Filter out extremely small contours (noise)
        min_area = 15  # pixels
        valid_contours = [c for c in contours if cv2.contourArea(c) > min_area]

        if not valid_contours:
            # If all are small noise, try the largest one regardless
            valid_contours = [max(contours, key=cv2.contourArea)]

        # Compute bounding box that encloses all valid contours
        x1s, y1s, x2s, y2s = [], [], [], []
        for c in valid_contours:
            x, y, cw, ch = cv2.boundingRect(c)
            x1s.append(x)
            y1s.append(y)
            x2s.append(x + cw)
            y2s.append(y + ch)

        if not x1s:
            return default_box

        lx1, ly1, lx2, ly2 = min(x1s), min(y1s), max(x2s), max(y2s)

        # Pad the bounding box slightly (e.g., 6 pixels on each side) to make it look nice
        pad = 6
        lx1 = max(0, lx1 - pad)
        ly1 = max(0, ly1 - pad)
        lx2 = min(w, lx2 + pad)
        ly2 = min(h, ly2 + pad)

        # Ensure box is non-degenerate (e.g., at least 15x15 pixels)
        if (lx2 - lx1) < 15 or (ly2 - ly1) < 15:
            return default_box

        return [lx1, ly1, lx2, ly2]

    def _suppress_duplicates(self, candidates: List[Dict[str, object]]) -> List[Dict[str, object]]:
        """Spatial duplicate suppression using Weighted Bounding Box Fusion.

        Groups overlapping/nearby candidates of the same class and merges them
        using a confidence-weighted average of their coordinates.
        """
        if not candidates:
            return []

        # Sort by confidence descending
        ordered = sorted(candidates, key=lambda item: item["confidence"], reverse=True)

        # Calculate merge distance dynamically from candidate box dimensions
        avg_w = sum(c["box"][2] for c in ordered) / len(ordered)
        avg_h = sum(c["box"][3] for c in ordered) / len(ordered)
        merge_distance = max(avg_w, avg_h)

        clusters: List[List[Dict[str, object]]] = []

        for candidate in ordered:
            assigned = False
            box = candidate["box"]  # (x, y, w, h)
            cx = box[0] + box[2] / 2.0
            cy = box[1] + box[3] / 2.0

            for cluster in clusters:
                if cluster[0]["class"] != candidate["class"]:
                    continue

                overlaps = False
                for member in cluster:
                    # IoU check
                    iou = self._iou(member["box"], box)
                    if iou > NMS_IOU_THRESHOLD:
                        overlaps = True
                        break

                    # Center distance check
                    mbox = member["box"]
                    mcx = mbox[0] + mbox[2] / 2.0
                    mcy = mbox[1] + mbox[3] / 2.0
                    dist = ((cx - mcx) ** 2 + (cy - mcy) ** 2) ** 0.5
                    if dist < merge_distance:
                        overlaps = True
                        break

                if overlaps:
                    cluster.append(candidate)
                    assigned = True
                    break

            if not assigned:
                clusters.append([candidate])

        # Merge clusters
        merged = []
        for cluster in clusters:
            total_weight = sum(item["confidence"] for item in cluster)

            # Weighted average coordinates: x, y, w, h
            # We average the corners (x1, y1, x2, y2) and then convert back to (x, y, w, h)
            x1 = sum(item["box"][0] * item["confidence"] for item in cluster) / total_weight
            y1 = sum(item["box"][1] * item["confidence"] for item in cluster) / total_weight
            x2 = sum((item["box"][0] + item["box"][2]) * item["confidence"] for item in cluster) / total_weight
            y2 = sum((item["box"][1] + item["box"][3]) * item["confidence"] for item in cluster) / total_weight

            max_conf = max(item["confidence"] for item in cluster)
            representative = cluster[0]

            # Average flat class probabilities across the cluster
            avg_probs = {}
            if representative.get("probabilities"):
                for class_name in representative["probabilities"]:
                    sum_val = sum(item["probabilities"][class_name] for item in cluster if "probabilities" in item)
                    avg_probs[class_name] = sum_val / len(cluster)

            merged.append({
                "class": representative["class"],
                "confidence": max_conf,
                "box": (int(round(x1)), int(round(y1)), int(round(x2 - x1)), int(round(y2 - y1))),
                "probabilities": avg_probs,
            })

        return merged

    def detect_regions(self, frame: np.ndarray) -> List[Dict[str, object]]:
        candidates: List[Dict[str, object]] = []
        for x, y, width, height in self._generate_regions(frame):
            region = frame[y : y + height, x : x + width]
            predicted_class, confidence, probabilities = self.predict_frame(region)
            if predicted_class != "normal" and confidence >= self.confidence_threshold:
                # Local CV refinement to locate the tightest bounding box
                local_box = self._refine_defect_box(region, predicted_class)
                rx = x + local_box[0]
                ry = y + local_box[1]
                rw = local_box[2] - local_box[0]
                rh = local_box[3] - local_box[1]
                
                candidates.append(
                    {
                        "class": predicted_class,
                        "confidence": confidence,
                        "box": (rx, ry, rw, rh),
                        "probabilities": probabilities,
                    }
                )
        return self._suppress_duplicates(candidates)

    def _play_audio(self, defect_class: str) -> None:
        if not self.audio_enabled or winsound is None:
            return
        now = time.time()
        if self.last_audio_play_time.get(defect_class, 0.0) + self.audio_cooldown_seconds > now:
            return
        self.last_audio_play_time[defect_class] = now
        sound_path = self.sounds_dir / f"{defect_class}.wav"
        if sound_path.exists():
            winsound.PlaySound(str(sound_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            winsound.Beep(1200, 120)

    def _update_stats(self, detections: List[Dict[str, object]]) -> None:
        """Update inspection stats based on UNIQUE physical defect detections."""
        self.stats["total_inspected"] += 1
        if not detections:
            self.stats["normal"] += 1
            return
        # Count unique physical defects (after NMS), not raw patches
        self.stats["defects"] += len(detections)
        for detection in detections:
            class_name = str(detection["class"])
            if class_name == "hole":
                self.stats["holes"] += 1
            elif class_name == "stain":
                self.stats["stains"] += 1
            elif class_name == "weaving_error":
                self.stats["weaving_errors"] += 1

    def _draw_overlay(self, frame: np.ndarray, frame_pred: str, frame_conf: float, frame_probs: Dict[str, float], detections: List[Dict[str, object]]) -> None:
        cv2.putText(frame, "HANDLOOM AI INSPECTION", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, "AI ACTIVE", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"Frame: {frame_pred} ({frame_conf * 100:.1f}%)", (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if detections:
            cv2.putText(frame, "DEFECTS DETECTED", (10, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            for idx, detection in enumerate(detections[:3], start=1):
                x, y, width, height = detection["box"]
                cv2.rectangle(frame, (x, y), (x + width, y + height), (0, 0, 255), 2)
                text = f"{idx}. {detection['class']} {detection['confidence'] * 100:.1f}%"
                cv2.putText(frame, text, (10, 145 + (idx - 1) * 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        else:
            cv2.putText(frame, "FABRIC NORMAL", (10, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        y = 220
        for cls, score in frame_probs.items():
            text = f"{cls}: {score * 100:.1f}%"
            cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            y += 20

        cv2.putText(frame, f"Total Inspected: {self.stats['total_inspected']}", (frame.shape[1] - 240, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Normal: {self.stats['normal']}", (frame.shape[1] - 240, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Defects: {self.stats['defects']}", (frame.shape[1] - 240, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Holes: {self.stats['holes']}", (frame.shape[1] - 240, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Stains: {self.stats['stains']}", (frame.shape[1] - 240, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Weaving Errors: {self.stats['weaving_errors']}", (frame.shape[1] - 240, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        if self.history:
            cv2.putText(frame, "Recent Defects", (frame.shape[1] - 240, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            for idx, (defect_class, confidence, timestamp_text) in enumerate(self.history[-4:], start=1):
                cv2.putText(frame, f"{timestamp_text} {defect_class} {confidence * 100:.1f}%", (frame.shape[1] - 240, 185 + idx * 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    def run_webcam(self, window_name: str = "Handloom Live Inspection") -> None:
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"Unable to open camera index {self.camera_index}")

        print(f"Camera opened on index {self.camera_index}")
        print("Press 'q' to quit")

        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to read frame from camera")
                break

            frame_pred, frame_conf, frame_probs = self.predict_frame(frame)
            working_frame = self._prepare_frame(frame)
            detections = self.detect_regions(working_frame)
            self._update_stats(detections)

            if detections:
                for detection in detections:
                    class_name = str(detection["class"])
                    self._play_audio(class_name)
                    self.history.append((class_name, float(detection["confidence"]), datetime.now().strftime("%H:%M:%S")))
                    if len(self.history) > 10:
                        self.history.pop(0)

            self._draw_overlay(frame, frame_pred, frame_conf, frame_probs, detections)
            cv2.imshow(window_name, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()

    def run_on_image(self, image_path: Path) -> Tuple[str, float, Dict[str, float], List[Dict[str, object]]]:
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Unable to read image: {image_path}")
        resized_image = self._prepare_frame(image)
        predicted_class, confidence, probabilities = self.predict_frame(resized_image)
        detections = self.detect_regions(resized_image)
        return predicted_class, confidence, probabilities, detections


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live inspection using the trained CNN + ResNet ensemble")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index")
    parser.add_argument("--image-path", type=Path, default=None, help="Optional image path to test inference once")
    parser.add_argument("--region-size", type=int, default=LIVE_REGION_SIZE, help="Region size for overlapping scan")
    parser.add_argument("--stride", type=int, default=None, help="Step size between regions")
    parser.add_argument("--overlap", type=float, default=LIVE_OVERLAP, help="Overlap between adjacent regions")
    parser.add_argument("--confidence-threshold", type=float, default=LIVE_CONFIDENCE_THRESHOLD, help="Minimum confidence to keep a defect candidate")
    args = parser.parse_args()

    runner = LiveInspectionRunner(
        camera_index=args.camera_index,
        region_size=args.region_size,
        stride=args.stride,
        overlap=args.overlap,
        confidence_threshold=args.confidence_threshold,
    )
    if args.image_path is not None:
        if not args.image_path.exists():
            raise FileNotFoundError(f"Image not found: {args.image_path}")
        predicted_class, confidence, probabilities, detections = runner.run_on_image(args.image_path)
        print(f"Image: {args.image_path}")
        print(f"Predicted class: {predicted_class}")
        print(f"Confidence: {confidence:.4f}")
        print("Detections:")
        if detections:
            for detection in detections:
                print(f"  {detection['class']} {detection['confidence']:.4f} box={detection['box']}")
        else:
            print("  none")
        for cls, score in probabilities.items():
            print(f"  {cls}: {score:.4f}")
    else:
        runner.run_webcam()


if __name__ == "__main__":
    main()
