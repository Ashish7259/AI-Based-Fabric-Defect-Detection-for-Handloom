from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from scripts.live_inspection import LiveInspectionRunner


class LiveInspectionGUI:
    def __init__(self, camera_index: int = 0) -> None:
        self.runner = LiveInspectionRunner(camera_index=camera_index)
        self.window_name = "Handloom AI Inspection"
        self.running = True

    def run(self, image_path: str | None = None) -> None:
        if image_path is not None:
            frame = cv2.imread(image_path)
            if frame is None:
                raise FileNotFoundError(f"Unable to read image: {image_path}")
            working_frame = self.runner._prepare_frame(frame)
            frame_pred, frame_conf, frame_probs = self.runner.predict_frame(working_frame)
            detections = self.runner.detect_regions(working_frame)
            self._draw_dashboard(frame, working_frame, frame_pred, frame_conf, frame_probs, detections)
            cv2.imshow(self.window_name, frame)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            return

        cap = cv2.VideoCapture(self.runner.camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"Unable to open camera index {self.runner.camera_index}")

        while self.running:
            ret, frame = cap.read()
            if not ret:
                break

            working_frame = self.runner._prepare_frame(frame)
            frame_pred, frame_conf, frame_probs = self.runner.predict_frame(working_frame)
            detections = self.runner.detect_regions(working_frame)
            self.runner._update_stats(detections)

            if detections:
                for detection in detections:
                    class_name = str(detection["class"])
                    self.runner._play_audio(class_name)
                    self.runner.history.append((class_name, float(detection["confidence"]), self._timestamp()))
                    if len(self.runner.history) > 10:
                        self.runner.history.pop(0)

            self._draw_dashboard(frame, working_frame, frame_pred, frame_conf, frame_probs, detections)
            cv2.imshow(self.window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()

    def _timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def _draw_dashboard(
        self,
        frame: np.ndarray,
        working_frame: np.ndarray,
        frame_pred: str,
        frame_conf: float,
        frame_probs: dict,
        detections: List[dict],
    ) -> None:
        height, width = frame.shape[:2]
        overlay = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.rectangle(overlay, (0, 0), (width, height), (20, 20, 20), -1)

        preview = cv2.resize(working_frame, (width // 2, height // 2))
        preview_h, preview_w = preview.shape[:2]
        overlay[:preview_h, :preview_w] = preview
        cv2.rectangle(overlay, (0, 0), (preview_w, preview_h), (0, 255, 0), 2)

        cv2.putText(overlay, "HANDLOOM AI INSPECTION", (preview_w + 20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(overlay, "AI ACTIVE", (preview_w + 20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(overlay, f"Current: {frame_pred} ({frame_conf * 100:.1f}%)", (preview_w + 20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        x0 = preview_w + 20
        y0 = 140
        if detections:
            cv2.putText(overlay, "DEFECTS", (x0, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            for i, detection in enumerate(detections[:4], start=1):
                label = f"{i}. {detection['class']} {detection['confidence']*100:.1f}%"
                cv2.putText(overlay, label, (x0, y0 + 25 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        else:
            cv2.putText(overlay, "FABRIC NORMAL", (x0, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        cv2.putText(overlay, "Status", (x0, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(overlay, "Models: READY", (x0, 285), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(overlay, "Camera: CONNECTED", (x0, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(overlay, "ESP32: NOT CONNECTED", (x0, 335), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.putText(overlay, "Stats", (x0, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(overlay, f"Total: {self.runner.stats['total_inspected']}", (x0, 405), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(overlay, f"Normal: {self.runner.stats['normal']}", (x0, 430), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(overlay, f"Defects: {self.runner.stats['defects']}", (x0, 455), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.putText(overlay, "Probabilities", (x0, 510), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y = 535
        for cls, score in frame_probs.items():
            cv2.putText(overlay, f"{cls}: {score * 100:.1f}%", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            y += 20

        if self.runner.history:
            cv2.putText(overlay, "History", (x0, 650), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            for i, (defect_class, confidence, ts) in enumerate(self.runner.history[-5:], start=1):
                cv2.putText(overlay, f"{ts} {defect_class} {confidence * 100:.1f}%", (x0, 675 + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        alpha = 0.75
        frame[:] = cv2.addWeighted(frame, 1 - alpha, overlay, alpha, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the handloom inspection dashboard")
    parser.add_argument("--image-path", type=str, default=None, help="Optional image to render in the dashboard")
    args = parser.parse_args()

    gui = LiveInspectionGUI(camera_index=0)
    gui.run(image_path=args.image_path)


if __name__ == "__main__":
    main()
