# A PROJECT REPORT on "AI-Based Handloom Fabric Defect Detection System using CNN–ResNet Ensemble & IoT Conveyor Automation"

## ABSTRACT
The HFDS (Handloom Fabric Defect Detection System) presents an AI-powered pipeline that recognizes and categorizes defects in handloom textiles from real-time video input. By combining computer vision, deep learning, soft-voting ensemble fusion, and IoT automation, the system bridges traditional handloom manufacturing with modern artificial intelligence. Using a custom CNN trained for texture and edge detection alongside a fine-tuned ResNet-50 model, the system identifies unique defects such as holes, stains, and weaving errors from extracted video frames. These detected defects are verified using classical computer vision techniques like Lab color-space deviation and Otsu thresholding. Finally, the system utilizes a weighted Non-Maximum Suppression (NMS) algorithm to accurately localize physical defects and trigger an IoT-based ESP32 microcontroller to stop the conveyor motor automatically. The system is deployed via a live industrial dashboard UI, allowing users to monitor fabric quality and view defect locations in real-time. This work highlights the potential of AI to automate quality inspection and improve operational efficiency in the textile industry.

---

## CHAPTER 1: INTRODUCTION

### 1.1 INTRODUCTION TO THE PROJECT
The HFDS project is a technology-driven initiative aimed at automating the quality inspection process for handloom textile manufacturing. This project leverages computer vision and deep learning to recognize, classify, and localize intricate defects on handloom fabrics in real-time. By analyzing live camera streams, HFDS classifies regions into four categories: normal, hole, stain, and weaving error. Using a dual-model soft-voting ensemble (Custom CNN + ResNet-50), combined with classical computer vision localization, the system offers robust, highly accurate predictions. This fusion of AI and IoT not only enhances quality control but also ensures immediate intervention by halting the conveyor belt when a defect is detected.

### 1.2 INTRODUCTION TO MACHINE LEARNING
The HFDS project leverages advanced machine learning and deep learning techniques to recognize and analyze fabric defects from live video input. This initiative aims to serve as an industrial automation tool for textile manufacturers. Machine learning enables systems to learn from data, adapt to new inputs, and perform tasks without explicit programming. HFDS employs a blend of deep learning architectures, sliding-window regional inference, and spatial non-maximum suppression to create a seamless pipeline from defect recognition to hardware control.

- **Data Collection and Frame Extraction:** A dataset of approximately 400 original photos comprising normal fabric, holes, stains, and weaving errors is utilized. Video recordings of the handloom process are ingested via a persistent camera stream manager.
- **Defect Detection:** Using a Custom CNN and a ResNet-50 model, the system identifies and classifies distinctive fabric defects with high accuracy.
- **Hardware Integration:** Detected defect events trigger an HTTP POST request to an ESP32 microcontroller, halting the conveyor motor instantly.

### 1.3 INTRODUCTION TO DEEP LEARNING
Deep learning is a specialized area within machine learning that focuses on building layered neural networks capable of learning complex patterns from large datasets. These models are highly effective in image recognition, making deep learning an ideal fit for HFDS. In this project, deep convolutional neural networks (CNNs) are utilized to learn and identify defects in handloom fabric.

#### 1.3.1 Custom CNN and ResNet-50
The system utilizes two distinct deep learning models. The **Custom CNN** acts as a lightweight texture and edge specialist, consisting of 4 convolutional blocks (32, 64, 128, 256 filters) to capture fine weaving lines. The **ResNet-50** acts as a deep semantic specialist using ImageNet pre-trained weights to capture global semantic shapes and discolorations. A soft-voting probability fusion mechanism combines their continuous output probability distributions, reducing model variance and boosting overall precision.

### 1.4 EXISTING METHOD
Traditionally, handloom fabric defect detection has relied on manual inspection, which is labor-intensive, time-consuming, and prone to human error due to fatigue. Some automated methods have used basic image processing or single lightweight CNNs, but these often struggle to generalize across complex handloom patterns, resulting in false positives on patterned normal fabric.

### 1.5 PROPOSED METHOD
The proposed HFDS project introduces a novel, robust pipeline combining a Custom CNN and ResNet-50 ensemble with an IoT ESP32 control system. The process involves real-time sliding-window region cropping, batch inference, global context conflict filtering, and classical CV refinement (such as Lab color-space thresholding for stains and Canny edge detection for weaving errors). This approach prevents normal textured fabrics from being misclassified and triggers highly reliable motor halts via an ESP32 microcontroller upon confirming genuine defects.

---

## CHAPTER 2: REQUIREMENT SPECIFICATION AND ANALYSIS

### 2.1 FUNCTIONAL REQUIREMENTS

#### 2.1.1 Input Dataset
The dataset comprises a structured collection of labeled handloom fabric images.
- **Training Dataset:** 70% of the data, supplemented with augmentations (rotations, flips, contrast) to reach ~400 samples per class.
- **Validation & Test Dataset:** 15% each, containing strictly untouched, original photographs to prevent data leakage and ensure reliable evaluation.

#### 2.1.2 Deep Learning Based Image Classification
The system extracts $640 \times 480$ px frames, resizing full frames for global context and generating overlapping $224 \times 224$ px patches for regional localization. Soft-voting probability fusion is applied to the predictions.

#### 2.1.3 User Requirements
- The user must be able to view a live dashboard UI (Glassmorphic Web Interface).
- The user must be able to see probability progress bars and a live inference debug panel.
- The system must provide distinct audio alerts for different defects.

#### 2.1.4 System Requirements
- Capable of streaming webcam feeds via a daemon thread without buffer freezing.
- Capable of sending HTTP POST requests to an ESP32 microcontroller.
- Must execute Weighted Non-Maximum Suppression (NMS) to merge overlapping bounding boxes.

### 2.2 NON-FUNCTIONAL REQUIREMENTS

- **Reliability:** The system implements global context conflict guards to prevent false positives and software debouncing (3.0s cooldown) to avoid repeated hardware triggers for the same defect.
- **Performance:** PyTorch fast batch inference is used on sliding-window crops to ensure real-time responsiveness on the live camera stream.
- **Scalability:** The modular design of the FastAPI server, PyTorch engine, and frontend telemetry allows for future integration of more cameras or defect classes.

### 2.3 SOFTWARE REQUIREMENTS
- **Operating System:** Windows / Linux / macOS
- **Language:** Python, JavaScript, HTML, CSS
- **Frameworks & Libraries:** PyTorch, OpenCV, FastAPI, Uvicorn

### 2.4 HARDWARE REQUIREMENTS
- Web Camera for live fabric stream
- ESP32 Microcontroller
- DC Conveyor Motors with Relay Switches
- Standard PC for running inference (GPU recommended for optimal PyTorch performance)

---

## CHAPTER 3: SYSTEM DESIGN

### 3.1 SYSTEM ARCHITECTURE DESIGN
The HFDS architecture follows an 11-stage pipeline:
1. **Dataset Preparation:** Raw fabric photos categorized into normal, hole, stain, and weaving_error. Anti-leakage split and augmentation are applied.
2. **Model Training:** Custom CNN and ResNet-50 models are trained separately.
3. **Ensemble Fusion:** Soft-voting merges the logits from both models.
4. **Live Ingestion:** `CameraStreamManager` grabs fresh frames into a thread-safe buffer.
5. **Global Context:** Full-frame analysis to determine base fabric status.
6. **Regional Inference:** Sliding-window $224 \times 224$ patches are processed in batches.
7. **Context Guard:** Weak regional defects are suppressed if the global context contradicts them strongly.
8. **CV Localization:** Refinement via Lab color space, Otsu, and Canny edge algorithms.
9. **Duplicate Suppression:** Weighted NMS merges overlapping boxes (IoU $\ge$ 0.30).
10. **Event Decision:** If a new unique defect is confirmed, audio is played and the ESP32 stops the motor.
11. **Dashboard:** The Live Dashboard UI renders canvas overlays, telemetry, and debug data.

---

## CHAPTER 4: SYSTEM IMPLEMENTATION

### 4.1 DATASET PREPARATION
The initial phase involved collecting ~360-400 raw fabric photos. The dataset was cleaned by removing corrupted, blurry, or black & white mask images. A rigorous anti-leakage strategy was enforced: a stratified split (70/15/15) was applied *before* any data augmentation. Only the training set underwent augmentations like rotations, flips, and contrast adjustments to yield approximately 400 robust samples per class. 

### 4.2 MODELING & TRAINING
Two models were independently trained:
- **Custom CNN:** 4 Convolutional blocks optimized for texture and edges.
- **ResNet-50:** Pre-trained on ImageNet, utilizing a linear classifier head ($2048 \rightarrow 4$).
The dual predictions were fused using a Soft-Voting probability method ($P_{Ensemble} = 0.5 \times (P_{CNN} + P_{ResNet})$), resulting in a test accuracy of $77.78\%$, macro precision of $80.46\%$, and macro recall of $78.27\%$.

### 4.3 LOCALIZATION & NMS
Instead of heavy frameworks like YOLO, the system utilizes overlapping sliding windows combined with classic computer vision. For instance, stain detection transforms patches into the $L^*a^*b^*$ color space to isolate color deviations from the median fabric tone, adjusting adaptively based on global confidence. Overlapping detections of the same physical defect are cleanly merged using confidence-weighted Non-Maximum Suppression (NMS).

---

## CHAPTER 5: SYSTEM TESTING

### 5.1 TYPES OF TESTS
- **Unit Testing:** Individual components like the `CameraStreamManager`, the PyTorch batch prediction functions, and the Lab color-space thresholding were tested independently.
- **Integration Testing:** Ensuring the PyTorch inference engine seamlessly communicated with the FastAPI server and that the web frontend (app.js) correctly locked frames during in-flight requests.
- **System Testing:** Live webcam testing to evaluate end-to-end latency, global context filtering (ensuring normal patterns weren't flagged as stains), and hardware control (verifying the ESP32 received the `/stop` endpoint within the expected time limit).
- **Acceptance Testing:** Verified against 8 core live scenarios, ensuring:
  - Normal fabric triggers no boxes or sounds.
  - Patterned fabric is not misclassified.
  - A genuine defect plays sound exactly once, stops the motor for 1.25s, and doesn't repeat while the defect remains visible.
  - Transitions (e.g., Stain disappearing, Hole appearing) are handled fluidly with new bounding boxes and unique events.

---

## CHAPTER 6: CONCLUSION AND SCOPE FOR FUTURE ENHANCEMENT

### 6.1 CONCLUSION
The HFDS project successfully demonstrates a highly functional, AI-driven automation pipeline for handloom fabric quality inspection. By strategically pairing a custom CNN with a deep ResNet-50 model via soft voting, the system achieves robust classification that avoids the pitfalls of complex patterned textiles. The integration of sliding-window inference and intelligent classical computer vision for localization sidesteps the need for expensive bounding-box dataset labeling. Furthermore, the seamless IoT integration with ESP32 microcontrollers and the glassmorphic live web dashboard prove that modern AI can be practically and efficiently deployed on factory floors to enhance manufacturing processes.

### 6.2 SCOPE OF FUTURE ENHANCEMENT
Future advancements could involve expanding the defect categories to detect finer anomalies, such as subtle dye bleeding or yarn thickness inconsistencies. The model could be upgraded to utilize dedicated object-detection architectures like YOLO or Mask R-CNN if extensive bounding-box annotated datasets become available, which would eliminate the need for sliding windows. Additionally, the system could be deployed on edge TPU devices (like NVIDIA Jetson) for faster, decentralized inference without relying on a central PC. Support for multi-camera synchronous streams would also enable 360-degree cylindrical inspection of fabric rolls.
