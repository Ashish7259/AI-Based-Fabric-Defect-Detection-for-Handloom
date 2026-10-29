"""
Wi-Fi controller for ESP32 motor commands.

The laptop sends HTTP commands to the ESP32. The ESP32 sketch owns the
motor timing, so Python only requests a stop event and does not need to
sleep for motor restart.
"""

from dataclasses import dataclass
from typing import Optional

import requests

from .config import REQUEST_TIMEOUT_SECONDS, STATUS_ENDPOINT, STOP_ENDPOINT


@dataclass(frozen=True)
class ESP32Status:
    connected: bool
    motor_status: str
    message: str


class ESP32Controller:
    """Small HTTP client for the ESP32 motor controller."""

    def __init__(self, base_url: str, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def stop_motors(self) -> ESP32Status:
        return self._post(STOP_ENDPOINT)

    def get_status(self) -> ESP32Status:
        return self._get(STATUS_ENDPOINT)

    def _post(self, endpoint: str) -> ESP32Status:
        try:
            response = requests.post(
                f"{self.base_url}{endpoint}",
                timeout=self.timeout_seconds,
            )
            return self._parse_response(response)
        except requests.RequestException as exc:
            return ESP32Status(False, "Unknown", f"ESP32 request failed: {exc}")

    def _get(self, endpoint: str) -> ESP32Status:
        try:
            response = requests.get(
                f"{self.base_url}{endpoint}",
                timeout=self.timeout_seconds,
            )
            return self._parse_response(response)
        except requests.RequestException as exc:
            return ESP32Status(False, "Unknown", f"ESP32 request failed: {exc}")

    def _parse_response(self, response: requests.Response) -> ESP32Status:
        if not response.ok:
            return ESP32Status(
                False,
                "Unknown",
                f"ESP32 returned HTTP {response.status_code}",
            )

        payload: Optional[dict] = None
        try:
            payload = response.json()
        except ValueError:
            return ESP32Status(True, "Unknown", response.text.strip())

        motor_status = str(payload.get("motor_status", "Unknown"))
        message = str(payload.get("message", "OK"))
        return ESP32Status(True, motor_status, message)

