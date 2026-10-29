# AI-Based Handloom Fabric Defect Detection System using CNN–ResNet Ensemble & IoT Conveyor Automation

An industrial, end-to-end real-time quality inspection system for handloom textile manufacturing. This document details the **complete step-by-step pipeline architecture** from raw dataset preparation to live model inference, localization, web dashboard rendering, and IoT hardware motor control.

---

## 🏗 Complete End-to-End Pipeline Architecture

```text
===========================================================================================
STAGE 1: DATASET PREPARATION & ANTI-LEAKAGE SPLIT
===========================================================================================
  Raw Fabric Photos (~360–400 Original Photos: normal, hole, stain, weaving_error)
                        ↓
  Dataset Cleaning (Remove corrupted, blurry, or black & white mask images)
                        ↓
  Stratified Split BEFORE Augmentation (70% Train / 15% Validation / 15% Test)
                        ↓
  Augmentation ON TRAINING SET ONLY (Rotations, Flips, Contrast → ~400 samples/class)

===========================================================================================
STAGE 2 & 3: DUAL MODEL TRAINING & SOFT-VOTING ENSEMBLE FUSION
===========================================================================================
  Custom CNN (Texture/Edge Specialist)   +   ResNet-50 (Deep Semantic ImageNet Transfer)
                        ↓                                    ↓
              Logits Vector (4,)                    Logits Vector (4,)
                        └─────────────────┬──────────────────┘
                                          ↓
                         Soft-Voting Probability Fusion
                   P_Ensemble(c) = 0.5 * (P_CNN(c) + P_ResNet(c))
                                          ↓
           Test Metrics: Accuracy 77.78% | Precision 80.46% | Recall 78.27%

===========================================================================================
STAGE 4 & 5: LIVE FRAME INGESTION & GLOBAL CONTEXT ANALYSIS
===========================================================================================
  Camera Stream (Webcam / Direct OpenCV Stream via CameraStreamManager Daemon Thread)
                        ↓
  Monotonic Frame ID & In-Flight Request Lock (app.js async request sequencing)
                        ↓
  Full-Frame Soft-Voting Prediction (Establishes Global Context: e.g. NORMAL 96.7%)

===========================================================================================
STAGE 6, 7 & 8: SLIDING-WINDOW REGIONAL INFERENCE & LOCALIZATION
===========================================================================================
  Crop Overlapping 224x224 px Patches across Working Resolution (640x480, 50% Overlap)
                        ↓
  PyTorch Fast Batch Inference on Crops (predict_patches_batch)
                        ↓
  Global Context Conflict Guard (Suppress weak regional defects if Global == NORMAL >= 80%)
                        ↓
  Local Computer Vision Refinement (_refine_defect_box)
  • Stain: Lab color-space deviation (adaptive thresholding) + Otsu
  • Hole: Contrast thresholding + Canny edges
  • Weaving Error: Sobel/Canny edge map + Morphological dilation

===========================================================================================
STAGE 9, 10 & 11: DUPLICATE SUPPRESSION, IOT CONTROL & WEB DASHBOARD
===========================================================================================
  Weighted Non-Maximum Suppression (NMS, IoU >= 0.30 Bounding Box Fusion)
                        ↓
  Event Decision & Debouncing (Track NEW vs EXISTING defect event)
                        ├── Confirmed NEW Defect → Web Audio Alert + ESP32 Motor Stop (1.25s)
                        └── Normal / Existing → Conveyor Continues Running
                        ↓
  Live Dashboard UI (Glassmorphic Web Interface, Probability Bars & Debug Panel)
===========================================================================================
```

---

## 📌 STAGE 1: Dataset Preparation & Anti-Data-Leakage Strategy

The dataset categorises fabric into **exactly 4 classes**:
1. `normal`: Clean fabric without defects (plain, patterned, multi-colored, or textured).
2. `hole`: Structural fabric damage, tears, or missing warp/weft threads.
3. `stain`: Abnormal discolouration, oil spots, or dye stains.
4. `weaving_error`: Structural thread irregularities, loose threads, or misaligned weave.

### Execution Script: `scripts/prepare_dataset.py`

#### 1. Dataset Cleaning & Verification
- Scans `dataset/raw/` to filter out corrupted files, non-RGB images, black-and-white threshold masks, and edge-only images.

#### 2. Stratified Anti-Leakage Split
- The original photographs are split **FIRST** into:
  - **70% Training Set** (`dataset/train/`)
  - **15% Validation Set** (`dataset/val/`)
  - **15% Independent Test Set** (`dataset/test/`)

> [!IMPORTANT]
> **Data Leakage Rule**: Augmentation is applied **ONLY to the training set** to expand training samples to $\approx 400$ images per class. The validation and test sets remain 100% untouched original photographs.

---

## 🧠 STAGE 2 & 3: Dual Model Architecture & Soft-Voting Ensemble

### Execution Scripts: `scripts/ensemble.py`, `scripts/train_cnn.py`, `scripts/train_resnet50.py`

### 1. Custom CNN Architecture
- **Purpose**: Lightweight texture and edge specialist.
- **Layers**: 4 Convolutional blocks (32, 64, 128, 256 filters) with `BatchNorm2d`, `ReLU`, `MaxPool2d` ($2 \times 2$), and `Dropout` ($0.25–0.40$).
- **Head**: `AdaptiveAvgPool2d(1,1)` $\rightarrow$ Dense(256 $\rightarrow$ 128) $\rightarrow$ Dense(128 $\rightarrow$ 4).

### 2. ResNet-50 Transfer Learning Architecture
- **Purpose**: Deep semantic specialist.
- **Backbone**: ImageNet pre-trained ResNet-50 with residual bottleneck blocks.
- **Head**: Replaced final fully-connected layer with linear classifier ($2048 \rightarrow 4$).

### 3. Soft-Voting Probability Fusion
For any given fabric input patch $x$:

$$P_{\text{Ensemble}}(c) = \frac{P_{\text{CNN}}(c) + P_{\text{ResNet-50}}(c)}{2}$$

$$\hat{y} = \arg\max_{c \in \{\text{normal}, \text{hole}, \text{stain}, \text{weaving\_error}\}} P_{\text{Ensemble}}(c)$$

### Test Set Performance Metrics:
* **Accuracy**: $\mathbf{77.78\%}$
* **Macro Precision**: $\mathbf{80.46\%}$
* **Macro Recall**: $\mathbf{78.27\%}$
* **Macro F1-Score**: $\mathbf{78.41\%}$

---

## 📹 STAGE 4 & 5: Live Frame Ingestion & Global Context Analysis

### Execution Files: `gui/server.py`, `gui/web/app.js`

### 1. Persistent Camera Stream (`CameraStreamManager`)
- OpenCV `VideoCapture` is maintained in a persistent background daemon thread (`CameraStreamManager` in `server.py`).
- Continuously grabs fresh frames into a thread-safe `latest_frame` buffer, eliminating Windows DirectShow driver buffer freezing.

### 2. Monotonic Frame ID & In-Flight Lock
- In `app.js`, `isProcessingWebcamFrame` lock skips interval ticks if a fetch request is currently in-flight.
- Every frame request contains an incrementing `frame_id`. Out-of-order responses (`data.frame_id < lastRenderedFrameId`) are discarded.

### 3. Full-Frame Global Prediction
- Full frame is resized to $224 \times 224$ px and evaluated via `predict_patch()`.
- Establishes global context confidence (e.g. `NORMAL` $96.7\%$ or `STAIN` $97.0\%$).

---

## 🔬 STAGE 6, 7 & 8: Regional Inspection, Context Filtering & Localisation

### Execution Files: `gui/server.py`, `iot/config.py`

### 1. Sliding-Window Region Crop Generation
- Working frame ($640 \times 480$ px) is cropped into overlapping $224 \times 224$ px regions with a $50\%$ overlap (stride $112$ px).
- Crops are batched and processed simultaneously via `predict_patches_batch()` in PyTorch.

### 2. Global Context Conflict Filtering
- **Normal Context Protection**: If global prediction is `NORMAL` ($\ge 80\%$), regional candidate predictions (e.g. `HOLE` 63%) require candidate confidence $\ge 75\%$ + valid localization to be accepted.
- **Class Conflict Protection**: If regional class conflicts with a non-normal global class (e.g. Global `STAIN` 53% vs Regional `WEAVING_ERROR` 48%), candidate confidence must be $\ge 70\%$.

### 3. Classical Computer Vision Localisation (`_refine_defect_box`)
For candidate defect patches:
- **Stain**: Converts patch to $L^*a^*b^*$ color space. Measures per-pixel color/luminance deviation from median fabric color. If global stain confidence is $\ge 85\%$, required Lab deviation scales down adaptively from $18$ to $8$. Applies Otsu thresholding on deviant regions.
- **Hole**: Applies median blur, thresholding dark regions ($\le 70\%$ median brightness) + Canny edge detection.
- **Weaving Error**: Canny edge map + morphological dilation with rectangular kernel.
- **Post-Check**: Rejects refined boxes covering $\ge 82\%$ of patch area (prevents noise boxes).

---

## 🎯 STAGE 9, 10 & 11: NMS, IoT Conveyor Control & Web Dashboard

### Execution Files: `gui/server.py`, `iot/esp32_controller.py`, `gui/web/app.js`

### 1. Spatial Non-Maximum Suppression (Weighted NMS)
- Candidate bounding boxes of the same class with Intersection over Union (IoU) $\ge 0.30$ or center-distance within merge limits are clustered.
- Merges clusters using confidence-weighted average coordinates:

$$x_1 = \frac{\sum x_{1,i} \cdot C_i}{\sum C_i}, \quad y_1 = \frac{\sum y_{1,i} \cdot C_i}{\sum C_i}$$

### 2. Event Decision & ESP32 Motor Stop
- If unique physical defects $> 0$ and conveyor is `RUNNING` and cooldown elapsed ($3.0$s):
  - Sets `event_state = "NEW"`.
  - Plays defect-specific Web Audio sound (`hole.wav`, `stain.wav`, `weaving_error.wav`) **ONCE**.
  - Issues HTTP POST `/stop` to ESP32 microcontroller, halting conveyor motor for $1.25$ seconds (`MOTOR_STOP_SECONDS`).
  - Motor automatically resumes when timer elapses (`motor_state` reverts to `RUNNING`).

### 3. Industrial Web Dashboard UI
- Renders live canvas overlays, probability progress bars, recent defect history log, and **Live Inference Debug Panel** showing:
  - Frame ID & Timestamp
  - Inference Latency ($ms$)
  - Raw CNN, ResNet-50, and Soft-Voting probabilities
  - Raw Regions / Accepted / Loc Rejected / Unique Defects count
  - Event State (`NEW` / `EXISTING` / `NONE`)

---

## 📁 Project Directory Map & File Responsibilities

| File Path | Function / Responsibility |
|---|---|
| `gui/run_gui.py` | Launcher script. Boots FastAPI server & opens web browser. |
| `gui/server.py` | FastAPI server, PyTorch Inspection Engine, `CameraStreamManager`, NMS, CV Localisation. |
| `gui/web/index.html` | HTML5 industrial glassmorphism dashboard layout. |
| `gui/web/styles.css` | Design system CSS (tokens, probability bars, micro-animations, debug card). |
| `gui/web/app.js` | Frontend engine: Canvas rendering, Web Audio synth, frame locking, telemetry. |
| `iot/config.py` | Configuration thresholds, confidence limits, NMS IoU, ESP32 endpoints. |
| `iot/esp32_controller.py` | REST API client for sending stop/start signals to ESP32 motor relays. |
| `models/cnn_best.pth` | Saved PyTorch weights for trained Custom CNN. |
| `models/resnet50_best.pth` | Saved PyTorch weights for trained ResNet-50. |
| `scripts/ensemble.py` | PyTorch network definitions (`CustomCNN`, `ResNet50`) & Soft-Voting builder. |
| `scripts/prepare_dataset.py` | Dataset cleaning, stratified 70/15/15 split, and training augmentation. |

---

## 🚀 How to Run the Project

1. Open PowerShell in project root:
   ```powershell
   cd c:\Projects\HFDS
   ```
2. Run GUI launcher:
   ```powershell
   handloom_env310\Scripts\python.exe gui\run_gui.py
   ```
3. Open browser at `http://127.0.0.1:8000`.

---

## 🎓 Comprehensive Viva Voce (Oral Defense) Q&A Guide

### Q1: Walk me through the end-to-end technical pipeline from fabric camera to motor stop.
> **Answer**: 
> 1. **Camera Capture**: `CameraStreamManager` continuously captures fresh $640 \times 480$ px frames in a persistent background thread.
> 2. **Global Context**: The frame is resized to $224 \times 224$ px and evaluated by our Custom CNN + ResNet-50 Soft-Voting ensemble to establish full-frame global probabilities.
> 3. **Sliding-Window Crops**: Overlapping $224 \times 224$ px crops ($50\%$ overlap) are extracted and processed in PyTorch batches.
> 4. **Context Filtering & CV Localisation**: Regional candidate patches clearing threshold ($0.65$) are validated against global context and refined via adaptive Lab color-space deviation and edge detection.
> 5. **Weighted NMS**: Candidate boxes with IoU $\ge 0.30$ are merged into unique physical defects.
> 6. **IoT Motor Halt**: If a new confirmed defect is found, the server dispatches a POST request to an ESP32 microcontroller, opening relay switches to stop the conveyor motor for $1.25$s.

### Q2: Why did you choose Soft-Voting Ensemble (Custom CNN + ResNet-50)?
> **Answer**: Custom CNN acts as a lightweight local texture and edge specialist, ideal for fine line weaving errors. ResNet-50 brings deep residual ImageNet transfer learning to capture global semantic shapes and discolouration stains. Soft voting averages their continuous output probability distributions ($P_{\text{Ensemble}} = \frac{P_{\text{CNN}} + P_{\text{ResNet}}}{2}$), reducing model variance and boosting accuracy to $77.78\%$.

### Q3: How did you prevent Data Leakage during dataset preparation?
> **Answer**: Original photographs were split **BEFORE** any data augmentation was performed (70% Train, 15% Validation, 15% Test). Augmentation (rotation, flips, contrast adjustment) was applied **exclusively to the training set**. Validation and test sets contained 100% untouched original photographs.

### Q4: Why did you use Sliding-Window + CV Refinement instead of YOLO or Mask R-CNN?
> **Answer**: YOLO and Mask R-CNN require expensive, manually annotated bounding-box dataset labels ($x, y, w, h$). Our dataset consists of image-level classification labels. The sliding-window approach allows classification models to localize defects across large fabric frames, while classical CV (Lab color space, Otsu, Canny) dynamically draws bounding boxes around anomalies without needing bounding-box training annotations.

### Q5: How does your system prevent false alarms on patterned normal fabric?
> **Answer**: 
> 1. Training set explicitly includes patterned normal fabric samples.
> 2. Global Context Filtering suppresses weak regional candidate predictions (e.g. `HOLE` 63%) when global prediction is `NORMAL` ($\ge 80\%$).
> 3. Color deviation pre-checks require candidate stain patches to exceed median fabric deviation before Otsu thresholding can generate a box.

### Q6: Explain Weighted Non-Maximum Suppression (NMS).
> **Answer**: Overlapping sliding windows often detect the same physical defect multiple times. NMS groups overlapping boxes of the same class (IoU $\ge 0.30$) into clusters. Instead of arbitrarily picking one box, Weighted NMS computes the confidence-weighted average of all cluster box coordinates:
> $$x_1 = \frac{\sum x_{1,i} \cdot C_i}{\sum C_i}, \quad y_1 = \frac{\sum y_{1,i} \cdot C_i}{\sum C_i}$$
> This produces smooth, accurate bounding boxes around physical defects.

### Q7: Explain the $L^*a^*b^*$ color space usage for stain detection.
> **Answer**: Unlike RGB space, where brightness and color are coupled across R, G, B channels, $L^*a^*b^*$ separates Lightness ($L^*$) from color channels ($a^*$ green-red, $b^*$ blue-yellow). We measure per-pixel absolute distance from median fabric color in Lab space. This isolates stains based on color deviation regardless of background fabric color or minor lighting variations.

### Q8: How did you fix OpenCV camera driver freezing on Windows?
> **Answer**: Opening and closing `cv2.VideoCapture` on every HTTP request causes Windows DirectShow drivers to reload initial camera buffer frames repeatedly, serving identical frozen frames. We implemented `CameraStreamManager` ([server.py](file:///c:/Projects/HFDS/gui/server.py#L88)), a persistent background thread that holds the camera open and continuously updates a single `latest_frame` buffer.

### Q9: How does the IoT conveyor control integration work?
> **Answer**: When a confirmed defect event is detected, FastAPI sends an HTTP POST `/stop` request to an ESP32 microcontroller over Wi-Fi. The ESP32 triggers a relay module to break the circuit to DC conveyor motors for $1.25$ seconds. Software debouncing ($3.0$s cooldown) prevents consecutive frames from repeatedly halting the conveyor for the same physical defect.

### Q10: What are the main performance metrics of your model?
> **Answer**: Evaluated on the independent test set:
> - **Accuracy**: $77.78\%$
> - **Macro Precision**: $80.46\%$
> - **Macro Recall**: $78.27\%$
> - **Macro F1-Score**: $78.41\%$
