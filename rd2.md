You are continuing work on my existing project:

"AI-Based Handloom Fabric Defect Detection using CNN–ResNet Ensemble"

IMPORTANT:
Do NOT rebuild the project from the beginning.

The following stages are ALREADY COMPLETED and tested:

1. Dataset preparation
2. Custom CNN
3. Custom CNN evaluation
4. ResNet-50
5. ResNet-50 evaluation
6. CNN + ResNet-50 probability-based Soft Voting Ensemble
7. Ensemble evaluation

The currently trained models are:

models/cnn_best.pth
models/resnet50_best.pth

The current ensemble test result is:

Accuracy: 77.78%
Macro Precision: 80.46%
Macro Recall: 78.27%
Macro F1: 78.41%

These are actual measured results from the untouched test set.

DO NOT fabricate or modify these results.

==================================================
FINAL TRAINED MODEL ARCHITECTURE
==================================================

The trained AI architecture MUST remain:

Custom CNN
+
ResNet-50
↓
Probability-Based Soft Voting Ensemble
↓
Final Prediction

Exactly four classes:

1. normal
2. hole
3. stain
4. weaving_error

Do NOT replace this architecture with YOLO.

Do NOT retrain the models unless I explicitly ask.

==================================================
CURRENT TASK
==================================================

The NEXT task is to implement the FINAL LIVE INSPECTION SYSTEM.

The live system must:

1. Open webcam
2. Capture fabric continuously
3. Analyze the frame
4. Support multiple defects in the same frame
5. Locate defective regions
6. Draw bounding boxes
7. Display defect class
8. Display confidence
9. Play defect-specific audio
10. Show a professional animated GUI
11. Communicate with ESP32
12. Stop conveyor for exactly 1.5 seconds after a confirmed defect
13. Automatically restart conveyor
14. Continue camera inspection

Do NOT modify the trained CNN or ResNet-50 architecture.

==================================================
IMPORTANT TRAINING VS LIVE INFERENCE
==================================================

During training:

Each original image contains only ONE target class.

Examples:

Hole image
→ one hole

Stain image
→ one stain

Weaving error image
→ one weaving error

Normal image
→ no target defect

However, during live camera operation:

ONE CAMERA FRAME MAY CONTAIN MULTIPLE DEFECTS.

Examples:

Hole + Stain

Hole + Weaving Error

Stain + Weaving Error

Hole + Stain + Weaving Error

Therefore, DO NOT classify the entire webcam frame as one single class.

==================================================
LIVE MULTIPLE-DEFECT INFERENCE
==================================================

Use the existing trained:

Custom CNN
+
ResNet-50
↓
Soft Voting Ensemble

For every webcam frame:

Webcam Frame
↓
Generate overlapping regions
↓
Run Custom CNN on each region
↓
Run ResNet-50 on each region
↓
Soft Voting Ensemble
↓
Obtain probabilities
↓
Apply confidence threshold
↓
Remove duplicate detections
↓
Combine detections
↓
Draw bounding boxes
↓
Display final live result

Example:

Region 1 → Normal
Region 2 → Hole
Region 3 → Normal
Region 4 → Stain

Final:

Detected:
Hole
Stain

Another example:

Region 1 → Hole
Region 2 → Stain
Region 3 → Weaving Error

Final:

Detected:
Hole
Stain
Weaving Error

==================================================
OVERLAPPING REGIONS
==================================================

Do NOT use only non-overlapping grid cells.

Use overlapping regions because a defect can cross the boundary between regions.

The following must be configurable:

region_size
stride
overlap

Do NOT blindly choose arbitrary values.

First inspect:

- webcam resolution
- camera distance
- visible fabric area
- expected defect size
- processing speed

Then choose sensible initial values.

Make these values easy to change later.

==================================================
BOUNDING BOXES
==================================================

When a defective region is confirmed:

Draw a bounding box around the detected region.

Display:

DEFECT CLASS
+
CONFIDENCE

Example:

[ bounding box ]

HOLE
Confidence: 94%

For multiple defects:

[ HOLE 94% ]

[ STAIN 89% ]

[ WEAVING ERROR 91% ]

Each detected defect must have its own bounding box.

IMPORTANT:

These are region-based localization boxes.

Do NOT claim pixel-level segmentation.

Do NOT claim that the system is a true object detector.

The current architecture is a classification ensemble being used with overlapping-region inference for localization.

==================================================
DUPLICATE DETECTION REMOVAL
==================================================

The same physical defect can be detected by multiple overlapping regions.

Example:

Region 1 → Hole 91%
Region 2 → Hole 89%
Region 3 → Hole 94%

This is ONE physical hole.

Do NOT display three boxes.

Use an appropriate duplicate-suppression/overlap mechanism.

The final result should approximately contain:

ONE physical defect
→ ONE bounding box
→ ONE defect event

Do not repeatedly trigger the same defect every frame.

==================================================
CONFIDENCE THRESHOLD
==================================================

Do NOT treat the highest probability as automatically being a confirmed defect.

Use a configurable confidence threshold.

Example:

confidence < threshold
→ uncertain / ignore

confidence >= threshold
→ candidate defect

The threshold must be configurable.

Do not tune the threshold using the test set.

Use validation data or controlled live testing when selecting a reasonable threshold.

==================================================
NORMAL FABRIC
==================================================

Normal fabric can contain:

- plain fabric
- patterned fabric
- different colors
- different textures
- normal handloom designs

Pattern does NOT automatically mean stain.

The live system must not simply classify:

pattern = stain

If no defect passes the confidence/detection criteria:

Display:

✓ FABRIC NORMAL

No defect detected.

Do NOT draw a defect box.

Do NOT play an alarm sound.

Do NOT stop the conveyor.

==================================================
DEFECT-SPECIFIC AUDIO ALERTS
==================================================

The system must provide THREE DIFFERENT AUDIO ALERTS.

1. HOLE
→ hole.wav

2. STAIN
→ stain.wav

3. WEAVING ERROR
→ weaving_error.wav

Normal:
→ NO SOUND

Store audio files separately:

sounds/
├── hole.wav
├── stain.wav
└── weaving_error.wav

Use configurable paths.

Do NOT hardcode audio paths throughout the project.

The audio should be short and clearly distinguishable.

Recommended:

Hole:
one distinct beep/pattern

Stain:
different beep/pattern

Weaving Error:
different beep/pattern

The actual audio files may be replaced later without changing the inference code.

==================================================
AUDIO DEBOUNCE / COOLDOWN
==================================================

IMPORTANT:

Do NOT play the same sound continuously for every webcam frame.

Example:

Frame 1 → Hole
Frame 2 → Hole
Frame 3 → Hole
Frame 4 → Hole

This must NOT produce four alarms.

Instead:

Same physical defect
↓
One confirmed defect event
↓
One audio alert

Use appropriate cooldown/debounce/event logic.

After the defect event has been handled, the system can detect a new defect event.

==================================================
ESP32 MOTOR CONTROL
==================================================

ESP32 integration is now part of the final live system.

IMPORTANT:

Do NOT destroy or unnecessarily rewrite the existing ESP32 code.

First inspect the existing ESP32 communication method.

If the existing firmware already supports commands such as:

START
STOP

reuse that communication.

If a small firmware change is necessary to support the required behavior, explain the required change before modifying it.

==================================================
MOTOR BEHAVIOR
==================================================

When a NEW confirmed defect is detected:

Defect detected
↓
Draw bounding box
↓
Display defect name
↓
Display confidence
↓
Play corresponding audio
↓
Send STOP command to ESP32
↓
Motor stops
↓
Wait exactly 1.5 seconds
↓
Send START command
↓
Motor resumes
↓
Continue camera inspection

The motor must stop for approximately/exactly 1.5 seconds as supported by the communication and timing implementation.

After restarting:

Camera capture continues.

AI inference continues.

The system waits for the next confirmed defect.

==================================================
VERY IMPORTANT MOTOR DEBOUNCE
==================================================

If the same defect is detected across many frames:

DO NOT repeatedly send:

STOP
START
STOP
START
STOP
START

for the same physical defect.

Example:

Frame 1 → Hole
Frame 2 → Hole
Frame 3 → Hole
Frame 4 → Hole

Treat this as ONE defect event.

Therefore:

ONE confirmed defect
↓
ONE audio alert
↓
ONE STOP
↓
1.5 seconds
↓
ONE START

Use event/cooldown logic.

==================================================
CAMERA MUST REMAIN RESPONSIVE
==================================================

Do NOT freeze the entire GUI using a blocking:

time.sleep(1.5)

inside the main camera-processing loop.

The application should remain responsive while the motor is stopped.

Prefer non-blocking timing/state management.

For example:

motor_state = RUNNING
motor_stop_until = timestamp

Then:

if defect_confirmed:
    send STOP
    motor_stop_until = current_time + 1.5 seconds

While motor is stopped:

- camera can continue processing if appropriate
- GUI remains responsive
- countdown/status can be displayed

When current time >= motor_stop_until:

send START
motor_state = RUNNING

Adapt this design to the existing project.

==================================================
MULTIPLE DEFECTS + MOTOR
==================================================

If one frame contains:

Hole + Stain + Weaving Error

The system should:

1. Draw all three bounding boxes.
2. Display all three defect names.
3. Display all three confidence values.
4. Trigger the appropriate defect audio alerts according to the event logic.
5. Send ONE STOP command.
6. Stop motor for 1.5 seconds.
7. Send ONE START command.
8. Continue inspection.

Do NOT send three separate STOP commands.

==================================================
PROFESSIONAL / ANIMATED GUI
==================================================

Create a polished industrial-style AI inspection dashboard.

The GUI should NOT look like a basic OpenCV window.

The GUI should include:

1. Live camera panel
2. Bounding boxes
3. Defect labels
4. Confidence values
5. AI model status
6. Camera status
7. ESP32 status
8. Conveyor status
9. Inspection status
10. Detection statistics
11. Recent defect history
12. CNN probabilities
13. ResNet-50 probabilities
14. Ensemble probabilities
15. Start Inspection button
16. Stop Inspection button
17. Settings
18. Model information
19. Audio status
20. Motor status

==================================================
ANIMATED GUI
==================================================

Make the GUI visually impressive but professional.

Use subtle animations such as:

- live status indicator
- pulsing "AI ACTIVE" indicator
- smooth status transitions
- animated detection notification
- animated confidence bars
- smooth counter updates
- defect alert animation
- motor STOP/START status animation
- small loading/model-ready animation where appropriate

Do NOT overuse animations.

The GUI should look like an industrial quality-control application.

Do NOT use distracting animations that reduce performance.

==================================================
MAIN GUI
==================================================

Recommended layout:

HEADER:

HANDLOOM AI INSPECTION SYSTEM

Status:
● SYSTEM ONLINE

LEFT:

LIVE CAMERA

Show:

- fabric frame
- bounding boxes
- defect labels
- confidence

RIGHT:

SYSTEM STATUS

Camera:
CONNECTED

Custom CNN:
READY

ResNet-50:
READY

Ensemble:
READY

ESP32:
CONNECTED / DISCONNECTED

Conveyor:
RUNNING / STOPPED

CENTER/LOWER:

CURRENT DETECTION

Example:

⚠ DEFECT DETECTED

HOLE
Confidence: 94%

Audio:
PLAYING

Motor:
STOPPED

Restart in:
1.2 seconds

==================================================
MODEL PROBABILITY PANEL
==================================================

Show the actual ensemble probabilities.

Example:

Normal          4%
Hole            91%
Stain           3%
Weaving Error   2%

Also optionally show:

CUSTOM CNN

Hole:
87%

RESNET-50

Hole:
95%

ENSEMBLE

Hole:
91%

This visually demonstrates the Soft Voting architecture.

==================================================
INSPECTION STATISTICS
==================================================

Display:

Total Inspected
Normal
Total Defects
Holes
Stains
Weaving Errors

Example:

Total Inspected: 128

Normal: 111
Defects: 17

Hole: 7
Stain: 6
Weaving Error: 4

These counters should update during the live session.

==================================================
DETECTION HISTORY
==================================================

Show recent detections.

Example:

Time       Defect          Confidence

13:42:08   Hole             94%
13:42:15   Stain            89%
13:42:26   Weaving Error    91%

Optionally save the detected frame/image for history.

Do not store unlimited images without a configurable limit.

==================================================
SYSTEM STATUS
==================================================

Show:

Camera:
CONNECTED

Models:
LOADED

CNN:
READY

ResNet:
READY

Ensemble:
READY

ESP32:
CONNECTED

Conveyor:
RUNNING

When defect detected:

AI:
DEFECT DETECTED

Motor:
STOPPED

After 1.5 seconds:

Motor:
RUNNING

==================================================
START / STOP CONTROLS
==================================================

Provide:

[ START INSPECTION ]

[ STOP INSPECTION ]

START should:

- initialize camera
- load models if necessary
- initialize live inference
- show system ready
- begin inspection

STOP should:

- stop live inference
- safely stop/handle conveyor according to existing ESP32 logic
- release camera resources
- update GUI status

==================================================
SETTINGS
==================================================

Provide configurable settings for:

- confidence threshold
- region size
- overlap/stride
- camera resolution
- audio enable/disable
- audio volume if supported
- motor stop duration

Default motor stop duration:

1.5 seconds

Do not hardcode these values throughout the project.

==================================================
MODEL INFORMATION
==================================================

Show:

Architecture:

Custom CNN + ResNet-50

Ensemble:

Soft Voting

Classes:

4

Input:

224 × 224

Device:

CPU / CUDA

Models:

CNN:
cnn_best.pth

ResNet:
resnet50_best.pth

==================================================
IMPORTANT CLASS ORDER
==================================================

The model class mapping MUST remain consistent.

The current ImageFolder class order is:

0 = hole
1 = normal
2 = stain
3 = weaving_error

Do not create a conflicting class order in live inference.

Load the saved class mapping where available.

Do not assume normal = index 0.

==================================================
LIVE PREDICTION FUNCTION
==================================================

Reuse the existing ensemble prediction functionality where possible.

A reusable function should provide:

predicted_class
confidence
class_probabilities

Example:

{
    "class": "hole",
    "confidence": 0.94,
    "probabilities": {
        "hole": 0.94,
        "normal": 0.03,
        "stain": 0.02,
        "weaving_error": 0.01
    }
}

Do not fabricate confidence values.

All confidence values must come from actual model probabilities.

==================================================
PERFORMANCE
==================================================

The application must be optimized for CPU because the current environment may run on CPU.

Automatically use CUDA if available.

Avoid unnecessary model reloads.

Load CNN and ResNet-50 ONCE.

Do not reload models for every region.

Use efficient preprocessing.

Use a reasonable number of overlapping regions.

Do not generate thousands of unnecessary regions per frame.

If needed, resize the camera frame while preserving enough information for defect detection.

==================================================
ERROR HANDLING
==================================================

Handle gracefully:

- camera unavailable
- ESP32 disconnected
- model missing
- audio file missing
- invalid image
- unsupported image format
- inference failure
- communication failure

The GUI should clearly show the problem.

Example:

⚠ ESP32 DISCONNECTED

The AI system may continue detection, but motor control must not be falsely reported as active.

==================================================
IMPORTANT SAFETY BEHAVIOR
==================================================

Never display:

ESP32 CONNECTED

unless the connection is actually confirmed.

Never display:

CONVEYOR RUNNING

unless the application knows the motor is running according to the available communication/state mechanism.

Do not falsely report hardware status.

==================================================
DO NOT MODIFY TRAINED MODELS
==================================================

The existing trained models are:

models/cnn_best.pth
models/resnet50_best.pth

Do NOT retrain them.

Do NOT overwrite them.

Do NOT modify their architecture.

Use them for live inference.

==================================================
DO NOT CHANGE DATASET
==================================================

The model training/evaluation phase is already complete.

Do not modify:

train
validation
test

unless explicitly requested.

Do not use live camera images to retrain automatically.

==================================================
DEVELOPMENT ORDER FOR THIS STAGE
==================================================

Implement the live system incrementally.

STEP A:
Inspect existing project structure and existing live/GUI/ESP32 code.

↓

STEP B:
Inspect existing CNN/ResNet/ensemble prediction functions.

Reuse them.

↓

STEP C:
Implement basic webcam capture.

↓

STEP D:
Load CNN + ResNet-50 once.

↓

STEP E:
Implement ensemble prediction for one image/region.

↓

STEP F:
Test one webcam frame.

↓

STEP G:
Implement configurable overlapping-region generation.

↓

STEP H:
Run ensemble prediction on each region.

↓

STEP I:
Implement confidence filtering.

↓

STEP J:
Implement duplicate suppression.

↓

STEP K:
Implement bounding boxes.

↓

STEP L:
Implement multiple-defect detection.

↓

STEP M:
Implement defect-specific audio.

↓

STEP N:
Implement event/cooldown logic.

↓

STEP O:
Implement ESP32 STOP/START behavior.

↓

STEP P:
Implement exact 1.5-second motor stop duration.

↓

STEP Q:
Implement professional animated GUI.

↓

STEP R:
Integrate all components.

↓

STEP S:
Test complete system.

Do NOT implement everything blindly in one step.

After each major stage, test it before proceeding.

==================================================
TEST SCENARIOS
==================================================

Test the final system with:

1. Normal plain fabric
2. Normal patterned fabric
3. Hole
4. Stain
5. Weaving Error
6. Hole + Stain
7. Hole + Weaving Error
8. Stain + Weaving Error
9. Hole + Stain + Weaving Error

Also test:

10. Different lighting
11. Different camera distances
12. Different fabric positions
13. Different defect sizes
14. Defect crossing region boundaries

For each test verify:

- bounding box
- class
- confidence
- audio
- duplicate suppression
- motor stop
- 1.5-second duration
- motor restart
- continued inspection

==================================================
IMPORTANT FINAL BEHAVIOR
==================================================

NORMAL:

Camera
↓
No confirmed defect
↓
No bounding box
↓
No audio
↓
Conveyor continues
↓
Camera continues

DEFECT:

Camera
↓
Defect detected
↓
Bounding box
↓
Defect name
↓
Confidence
↓
Defect-specific sound
↓
ESP32 STOP
↓
Motor STOP
↓
1.5 seconds
↓
ESP32 START
↓
Motor RUNNING
↓
Continue camera inspection

MULTIPLE DEFECT:

Camera
↓
Hole + Stain + Weaving Error
↓
Three bounding boxes
↓
Three defect labels
↓
Corresponding audio alerts
↓
ONE STOP command
↓
Motor STOP 1.5 seconds
↓
ONE START command
↓
Motor RUNNING
↓
Continue inspection

==================================================
IMPORTANT
==================================================

Do NOT:

- replace CNN + ResNet with YOLO
- retrain the models
- fabricate confidence
- fabricate accuracy
- modify the test results
- create unnecessary crops
- reload models for every region
- play audio every frame
- send repeated STOP commands for the same defect
- freeze the GUI for 1.5 seconds
- falsely report ESP32 connection
- falsely report motor status
- delete working project files
- create duplicate functionality
- unnecessarily rewrite existing code

Reuse existing working code wherever possible.

==================================================
START NOW
==================================================

Start by inspecting my CURRENT project.

Do NOT immediately create the entire system.

First tell me:

1. What live inference code already exists?
2. What GUI code already exists?
3. What ensemble prediction code already exists?
4. What ESP32 communication code already exists?
5. What audio-related code/files already exist?
6. What can be reused?
7. What needs to be created?
8. What files should be modified?
9. Whether any existing functionality conflicts with this specification.

Then implement ONLY the first appropriate live-inference stage.

Wait for my confirmation before making major changes to the next stage.