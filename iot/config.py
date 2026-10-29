"""
Configuration for the real-time fabric inspection hardware test.

Update ESP32_BASE_URL after uploading the ESP32 sketch and checking the
IP address printed in the Arduino Serial Monitor.
"""

ESP32_BASE_URL = "http://10.107.162.59"

STOP_ENDPOINT = "/stop"
STATUS_ENDPOINT = "/status"

REQUEST_TIMEOUT_SECONDS = 2.0
MOTOR_STOP_SECONDS = 3.0

CAMERA_INDEX = 1
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

LIVE_REGION_SIZE = 224
LIVE_STRIDE = 112
LIVE_OVERLAP = 0.50
LIVE_CONFIDENCE_THRESHOLD = 0.65

AUDIO_ENABLED = True
AUDIO_COOLDOWN_SECONDS = 2.0
SOUNDS_DIR = "sounds"

# ---------------------------------------------------------------------------
# Defect detection thresholds (used by server NMS pipeline)
# ---------------------------------------------------------------------------
# Minimum ensemble confidence to accept a patch as a defect candidate.
# 0.55 balances sensitivity (catching real defects) against false positives
# on clean fabric.  Do NOT lower below 0.45 — the small-stain problem is
# solved by improved localization, not by a lower classifier threshold.
DEFECT_CONFIDENCE_THRESHOLD = 0.55

# When the global full-frame prediction is a defect class, regional patches
# matching that same class use this lower threshold to catch small defects
# that occupy a tiny fraction of the 224×224 crop.
GLOBAL_SUPPORT_THRESHOLD = 0.30

# IoU threshold for Non-Maximum Suppression.
# With 50 % overlap on 224 px patches the IoU between adjacent same-sized
# windows is ≈ 0.33, so 0.30 correctly merges neighbours while keeping
# truly separated detections apart.
NMS_IOU_THRESHOLD = 0.30

# Minimum 90th-percentile Lab colour deviation (0-255 scale) that a stain
# patch must show before the bounding-box localisation is accepted.
# Below this level the patch is considered uniform fabric texture and the
# detection is rejected even if the model confidence cleared the threshold.
# Set lower to detect small vivid stains (e.g. orange on white fabric).
MIN_STAIN_DEVIATION = 8

# Global context filtering thresholds
GLOBAL_NORMAL_SUPPRESSION_THRESHOLD = 0.80  # Required global NORMAL confidence to suppress weak regional defects
CONFLICTING_CLASS_THRESHOLD = 0.45           # Required regional confidence when regional class conflicts with global prediction

# ---------------------------------------------------------------------------
# Localization validation constants
# ---------------------------------------------------------------------------
# Minimum defect box area as a fraction of the patch area.
# Boxes smaller than this are considered noise, not real defects.
MIN_DEFECT_AREA_RATIO = 0.005

# Maximum defect box coverage of the patch area.
# A box covering more than this fraction of the patch almost certainly means
# localization captured texture noise rather than a real defect boundary.
MAX_DEFECT_COVERAGE_RATIO = 0.80

# ---------------------------------------------------------------------------
# Temporal defect tracking (cross-frame deduplication)
# ---------------------------------------------------------------------------
# IoU threshold to consider a detection in the current frame as the SAME
# physical defect seen in a previous frame.
TEMPORAL_IOU_THRESHOLD = 0.30

# How long (seconds) a tracked defect stays in memory after the last frame
# it was seen in.  After this timeout it is forgotten, and a defect at the
# same location would be counted as NEW.
TEMPORAL_MEMORY_SECONDS = 3.0

# Seconds to wait after a motor-stop event ends before allowing a new stop.
# Belt-and-suspenders safety alongside spatial temporal tracking.
MOTOR_COOLDOWN_SECONDS = 3.0

DEFECT_CLASSES = [
    "Normal",
    "Hole",
    "Stain",
    "Weaving Error",
]
