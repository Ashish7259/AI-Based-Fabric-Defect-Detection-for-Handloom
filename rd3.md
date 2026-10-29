I need you to fix TWO problems in the current LIVE INFERENCE system.

IMPORTANT:
Inspect the existing code first and make the smallest necessary changes.

DO NOT:
- retrain the Custom CNN
- retrain ResNet-50
- change the Soft Voting Ensemble
- change model weights
- change the dataset
- change the training pipeline
- replace the architecture with YOLO
- modify ESP32 code
- rewrite unrelated working code

==================================================
PROBLEM 1 — FALSE POSITIVE + BAD BOUNDING BOX
==================================================

Currently, a normal fabric image can sometimes be predicted as:

STAIN 58%

The current confidence threshold is around 0.55.

This causes a weak prediction such as 58% to be accepted as a confirmed stain.

Also, when the system predicts STAIN, the bounding box is sometimes very large and covers a large part of the inference region instead of the actual stain.

The current localization/refinement appears to use classical image processing such as Lab color difference and Otsu thresholding.

The problem is that normal fabric texture can create artificial regions during thresholding.

DO NOT simply make the box smaller.

DO NOT hardcode coordinates.

DO NOT manually move the box.

The system must determine whether there is actually enough visual evidence for a defect before accepting it.

Implement a better LIVE verification process:

Webcam frame
↓
Overlapping regions
↓
CNN + ResNet-50
↓
Soft Voting
↓
Confidence filtering
↓
Defect verification/localization
↓
Duplicate suppression
↓
Final detection

Make the confidence threshold configurable.

Do not blindly set it to 0.70 just because it is higher.

Use the existing validation/testing information and live behavior to choose a sensible initial threshold.

The threshold must remain configurable in the GUI/settings.

If the ensemble gives a weak prediction such as:

STAIN = 58%

and the region does not contain sufficient evidence of a stain:

→ reject the detection
→ do not draw a defect box
→ do not play the stain sound
→ do not stop the conveyor

If a genuine stain has strong evidence:

→ accept it
→ localize it
→ draw the bounding box
→ display class + confidence
→ trigger the appropriate event

==================================================
BOUNDING BOX LOCALIZATION
==================================================

When a region is classified as a defect, do not automatically use the entire overlapping region as the final bounding box.

Try to refine the box using the actual image content inside the region.

The existing localization/refinement method may use:

- Lab color difference
- brightness/contrast
- texture
- thresholding
- morphology
- contours
- connected components

Use the approach already present in the project where possible.

Improve it so normal fabric texture does not automatically become a defect.

For STAIN specifically:

Do not rely blindly on Otsu thresholding.

Before accepting the extracted stain region, verify that the detected area has meaningful color/brightness deviation from the surrounding fabric.

If no reliable defect region can be found:

→ reject the localization
→ do not draw a large fallback box

For HOLE and WEAVING ERROR, use the appropriate existing localization logic.

Do not use one hardcoded image-processing rule for every defect type if the existing code already handles them separately.

The final bounding box must be in ORIGINAL CAMERA FRAME coordinates.

If the defect is found inside a crop:

local crop coordinates
↓
convert back to original frame coordinates
↓
draw final bounding box

==================================================
PROBLEM 2 — LIVE PREDICTION GETTING STUCK ON ONE CLASS
==================================================

The second problem is that during live inference the system sometimes keeps showing the same class.

Example:

Frame 1 → STAIN
Frame 2 → STAIN
Frame 3 → STAIN

This is normal if the same stain is still visible.

However, if the stain disappears and a hole appears, the system MUST be able to change:

Frame 1 → STAIN
Frame 2 → STAIN
Frame 3 → HOLE
Frame 4 → HOLE

Likewise:

STAIN
↓
HOLE
↓
WEAVING ERROR
↓
NORMAL

must be possible.

Inspect the existing code for:

- cached predictions
- previous prediction state
- temporal smoothing
- majority voting
- cooldown logic
- detection history
- GUI state
- previous bounding boxes
- previous class variables

Find out whether an old prediction is being incorrectly reused for new frames.

Every new webcam frame must be capable of producing a fresh prediction.

The previous prediction must NOT automatically become the current prediction.

==================================================
IMPORTANT DIFFERENCE:
PREDICTION VS EVENT
==================================================

Separate these two concepts.

CURRENT FRAME PREDICTION:

What does the current frame/region contain?

This must update continuously.

EVENT:

Has a NEW physical defect appeared that should trigger:

- audio
- ESP32 STOP
- motor stop timer

These are different.

Example:

Frame 1:
STAIN

Frame 2:
STAIN

Frame 3:
STAIN

The displayed prediction can remain:

STAIN

But the system should NOT play the stain sound or send repeated STOP commands every frame.

Instead:

STAIN detected
↓
One defect event
↓
Play stain sound once
↓
Send ONE STOP
↓
Motor stops
↓
1.5 seconds
↓
Motor restarts

While the same stain remains visible:

STAIN
STAIN
STAIN

Do not repeatedly trigger the event.

If the stain disappears and a new hole appears:

HOLE
↓
New defect event
↓
Play hole sound
↓
Send STOP
↓
1.5 seconds
↓
Motor restarts

Therefore:

PREDICTION STATE
and
DEFECT EVENT STATE

must be handled separately.

==================================================
BOUNDING BOX RESET
==================================================

Every live frame must start with the current frame's detections.

Do not permanently reuse old bounding boxes.

If a previous stain disappears:

Old stain box
→ REMOVE

If a new hole appears:

New hole box
→ DRAW

If no confirmed defect exists:

→ remove defect boxes
→ show NORMAL/NO CONFIRMED DEFECT
→ do not play sound
→ do not trigger ESP32

==================================================
MULTIPLE DEFECTS
==================================================

The live frame can contain:

Hole + Stain

or:

Hole + Stain + Weaving Error

Therefore the system must support multiple unique defects.

Example:

Region 1 → Hole
Region 2 → Hole
Region 3 → Stain
Region 4 → Normal

After duplicate suppression:

ONE Hole
ONE Stain

Final GUI:

Detected:
Hole
Stain

Do NOT count overlapping patches as separate physical defects.

==================================================
DUPLICATE SUPPRESSION
==================================================

Overlapping regions may detect the same physical defect multiple times.

Example:

Region 1 → Hole 91%
Region 2 → Hole 87%
Region 3 → Hole 94%

These represent ONE physical hole.

Final:

Hole × 1

not:

Hole × 3

Use IoU/spatial overlap or an appropriate duplicate-suppression method.

Only FINAL UNIQUE detections should:

- receive bounding boxes
- increase defect counters
- trigger audio
- trigger ESP32 motor stop

==================================================
AUDIO
==================================================

Keep the existing three defect-specific sounds:

Hole → hole.wav
Stain → stain.wav
Weaving Error → weaving_error.wav

Normal → no sound

Do not play sound for weak/rejected predictions.

Do not play the same sound every frame.

One confirmed NEW defect event:

→ one appropriate audio alert

==================================================
ESP32
==================================================

DO NOT modify the existing ESP32 code.

The current ESP32 is responsible for motor control.

When a NEW confirmed defect event occurs:

Defect
↓
ONE STOP request
↓
Motor stops
↓
1.5 seconds
↓
Motor restarts
↓
Continue inspection

Do not send repeated STOP commands for the same physical defect.

Do not send separate STOP commands for every overlapping region.

==================================================
GUI
==================================================

The GUI must show the CURRENT detection state.

Example:

STAIN
58%

If 58% is rejected because it is weak/uncertain:

Show:

UNCERTAIN
or
NORMAL

Do not show:

STAIN DETECTED

Do not draw a defect box.

If a genuine stain is confirmed:

Show:

STAIN
Confidence: XX%

and draw the refined bounding box around the detected region.

If a new hole appears:

Remove the previous stain box and show:

HOLE
Confidence: XX%

with the new bounding box.

The GUI counters must represent UNIQUE DEFECT EVENTS/PHYSICAL DEFECTS, not raw patch predictions.

==================================================
DEBUG INFORMATION
==================================================

During testing, add useful debug information such as:

Raw regions: 12
Accepted predictions: 4
Unique detections: 1

Current frame prediction:
STAIN 58%

Localization:
REJECTED / ACCEPTED

Event:
NEW / EXISTING / NONE

This will help diagnose the live system.

==================================================
TEST CASES
==================================================

After making the changes, test at least:

TEST 1:
Normal fabric

Expected:
No defect
No box
No sound
No ESP32 stop

TEST 2:
Normal patterned fabric

Expected:
Do not automatically classify pattern as stain.

TEST 3:
One genuine stain

Expected:
One stain box
One stain event
One stain sound
One ESP32 stop
Motor stops 1.5 seconds
Motor restarts

TEST 4:
Same stain remains visible for several frames

Expected:
Prediction remains STAIN if appropriate,
but sound/ESP32 stop must NOT trigger every frame.

TEST 5:
Stain disappears and hole appears

Expected:

STAIN
↓
HOLE

Previous stain box disappears.

New hole box appears.

Hole sound plays.

New motor-stop event occurs.

TEST 6:
One hole detected by several overlapping regions

Expected:

Raw detections > 1

Final:

ONE HOLE

ONE BOX

ONE EVENT

TEST 7:
Hole + Stain

Expected:

ONE hole box
ONE stain box

Both classes displayed.

Appropriate audio/event handling.

TEST 8:
Hole + Stain + Weaving Error

Expected:

Three unique detections.

Three boxes.

Correct classes.

No duplicate boxes caused by overlapping regions.

==================================================
IMPORTANT
==================================================

Do not artificially increase confidence.

Do not change 58% into a higher number.

Do not fabricate results.

Do not hide false positives simply by forcing the GUI to display NORMAL.

The goal is to make the live system genuinely more reliable.

First inspect the existing live inference code and explain:

1. Why the normal fabric is being classified as STAIN 58%.
2. Why the bounding box becomes very large.
3. Why the previous class may persist between frames.
4. Where prediction state is stored.
5. Where event state is stored.
6. Where bounding boxes are generated.
7. Where defect counters are updated.

Then implement the smallest necessary changes to solve BOTH problems.

Do not rewrite unrelated working code.

After implementation, run the live test and show me the actual results.