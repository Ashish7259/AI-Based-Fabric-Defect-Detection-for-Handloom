"""
Coordinates AI predictions, camera frames, and ESP32 motor commands.

The HardwareManager is responsible for:
1. Running one inspection step.
2. Triggering the ESP32 only once for a newly detected defect.
3. Logging hardware events.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Optional

from .config import ESP32_BASE_URL
from .dummy_detector import DetectionResult, DummyFabricDefectDetector
from .esp32_controller import ESP32Controller, ESP32Status


LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "hardware_events.log"


@dataclass(frozen=True)
class InspectionResult:
    detection: DetectionResult
    esp32_status: ESP32Status
    command_sent: bool


class EnsembleDetectionAdapter:
    """Wrap the trained ensemble outputs in the same contract used by the hardware manager."""

    def __init__(self, runner=None) -> None:
        self.runner = runner

    def predict(self, frame) -> DetectionResult:
        if self.runner is None:
            return DummyFabricDefectDetector().predict(frame)

        predicted_class, confidence, probabilities = self.runner.predict_frame(frame)
        label = predicted_class.capitalize()
        if label == "Weaving_error":
            label = "Weaving Error"
        elif label == "Hole":
            label = "Hole"
        elif label == "Stain":
            label = "Stain"
        else:
            label = "Normal"

        if label == "Normal":
            confidence = max(confidence, 0.90)
        return DetectionResult(label=label, confidence=float(confidence), explanation="Ensemble-based inspection result")


class HardwareManager:
    """
    Handles one inspection cycle.

    A stop command is sent ONLY when:
        Normal  --->  Defect

    It will NOT repeatedly send stop commands while the same defect
    continues to appear in consecutive frames.
    """

    def __init__(
        self,
        detector=None,
        controller=None,
    ):
        LOG_DIR.mkdir(exist_ok=True)

        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )

        self.detector = detector or DummyFabricDefectDetector()
        self.controller = controller or ESP32Controller(ESP32_BASE_URL)

        # Remember previous frame state
        self.previous_defect = False

    def inspect_frame(self, frame) -> InspectionResult:
        detection = self.detector.predict(frame)
        command_sent = False

        if detection.is_defect:
            if not self.previous_defect:
                esp32_status = self.controller.stop_motors()
                command_sent = True
                logging.info(
                    "STOP command sent | Defect=%s Confidence=%.2f",
                    detection.label,
                    detection.confidence,
                )
            else:
                esp32_status = self.controller.get_status()
            self.previous_defect = True
        else:
            esp32_status = self.controller.get_status()
            self.previous_defect = False

        return InspectionResult(
            detection=detection,
            esp32_status=esp32_status,
            command_sent=command_sent,
        )

    def get_esp32_status(self):
        return self.controller.get_status()