I want to retrain my Handloom Fabric Defect Detection System from the beginning using my CURRENT DATASET ONLY.

IMPORTANT DATASET RULE:

I currently have approximately 250 or more images for each of the four classes:

1. Normal
2. Hole
3. Stain
4. Weaving Error

Some classes may contain MORE than 250 images.

For this training run:

- Use ONLY 250 images from EACH class.
- If a class contains more than 250 images, select exactly 250.
- DO NOT delete the extra images from my original dataset.
- DO NOT modify or permanently remove any original images.
- Simply create/use a controlled training subset of exactly 250 images per class.
- Therefore the base dataset for this experiment must contain exactly:

Normal = 250
Hole = 250
Stain = 250
Weaving Error = 250

Total original images = 1000.

Do NOT use additional datasets.
Do NOT download public datasets.
Do NOT add external images.
Do NOT use the extra images beyond the selected 250 per class for this experiment.

==================================================
MAIN OBJECTIVE
==================================================

Train the complete deep-learning classification pipeline from the beginning using these 1000 original images.

The target is to create an augmented training dataset of approximately 4000 training images in total.

IMPORTANT:

4000 images must NOT mean simply duplicating the same images.

Use realistic augmentation only on TRAINING images.

The original images must remain untouched.

==================================================
DATASET SPLIT RULE
==================================================

FIRST select exactly 250 original images per class.

Then split the ORIGINAL images into:

- Training
- Validation
- Test

before performing augmentation.

DO NOT augment before splitting.

DO NOT allow the same original image or near-duplicate version of the same original image to appear across different splits.

Validation and test images must remain completely untouched.

ONLY training images may be augmented.

The final test set must remain untouched and must be used for the final reported performance.

Do NOT select test images based on whether the model predicts them correctly.

==================================================
TARGET DATASET SIZE
==================================================

From the selected 250 images per class, create approximately 4000 images TOTAL for the training dataset through realistic augmentation.

Aim for approximately:

1000 original images
        ↓
Train/Validation/Test split
        ↓
Training subset
        ↓
Realistic augmentation
        ↓
Approximately 4000 training images TOTAL

Do NOT create thousands of unnecessary crops.

Do NOT artificially inflate the dataset with identical or nearly identical images.

Do NOT augment validation images.

Do NOT augment test images.

==================================================
IMAGE PREPROCESSING
==================================================

Use:

Input size:
224 × 224

Use ImageNet normalization.

Apply appropriate preprocessing consistently to validation and test images.

For training augmentation, use realistic transformations suitable for handloom fabric images.

Possible augmentations may include appropriate:

- small rotations
- horizontal/vertical transformations only if physically valid
- small translations
- scaling
- brightness variation
- contrast variation
- slight color variation
- other realistic transformations

DO NOT use unrealistic transformations that could change the nature of a fabric defect.

Do not introduce artificial defects.

Do not create fake holes, stains, or weaving errors.

==================================================
FOUR CLASSES
==================================================

The system has exactly four classes:

0 → Normal
1 → Hole
2 → Stain
3 → Weaving Error

Do not add or remove classes.

==================================================
MODEL 1 — CUSTOM CNN
==================================================

Build/train the Custom CNN first.

Train it from the beginning using the newly prepared dataset.

Do NOT load an old trained Custom CNN checkpoint.

Do NOT continue training an old model.

This is a completely fresh training run.

Use proper:

- loss function
- optimizer
- learning-rate scheduling if appropriate
- regularization
- dropout where appropriate
- early stopping if appropriate
- best-model checkpointing

Monitor training and validation performance.

Save the best Custom CNN model.

For example:

models/cnn_best.pth

==================================================
CUSTOM CNN EVALUATION
==================================================

After training, evaluate the Custom CNN on the untouched test set.

Generate:

- accuracy
- precision
- recall
- F1-score
- confusion matrix
- per-class performance
- classification report

Do NOT fabricate any result.

All reported results must come from the untouched test set.

==================================================
MODEL 2 — RESNET-50
==================================================

After the Custom CNN has been successfully trained and evaluated, implement ResNet-50.

Use transfer learning appropriately.

Do NOT replace the architecture with YOLO.

Do NOT replace the Custom CNN.

The architecture must remain:

Custom CNN
+
ResNet-50
↓
Soft Voting Ensemble

Train ResNet-50 using the SAME dataset split used for the Custom CNN.

The test set MUST be exactly the same test set.

Save the best ResNet-50 model.

For example:

models/resnet50_best.pth

==================================================
RESNET-50 EVALUATION
==================================================

Evaluate ResNet-50 independently on the same untouched test set.

Generate:

- accuracy
- precision
- recall
- F1-score
- confusion matrix
- classification report
- per-class performance

Do not fabricate results.

==================================================
SOFT-VOTING ENSEMBLE
==================================================

After both models are successfully trained and evaluated:

Custom CNN
       +
ResNet-50
       ↓
Probability-based Soft Voting
       ↓
Final Ensemble Prediction

Use the predicted class probabilities from both models.

For equal-weight soft voting:

ensemble_probability =
(CNN_probability + ResNet_probability) / 2

The class with the highest final ensemble probability becomes the ensemble prediction.

Evaluate the ensemble using the SAME untouched test set.

Generate:

- Ensemble accuracy
- Ensemble precision
- Ensemble recall
- Ensemble F1-score
- Confusion matrix
- Classification report
- Per-class results

Do NOT fabricate or manually improve the results.

==================================================
IMPORTANT DATA LEAKAGE RULES
==================================================

Strictly prevent:

- train/test leakage
- validation/test leakage
- duplicate images across splits
- augmented copies of test images
- augmented copies of validation images
- using test images during training
- using test images for hyperparameter tuning
- manually selecting easy test images
- fabricated accuracy
- fabricated confidence values

If duplicate or near-duplicate images are detected, report them and handle them safely without contaminating the test set.

==================================================
LIVE INSPECTION
==================================================

After the models and ensemble are successfully trained and tested, preserve the existing live-inspection architecture.

The final live pipeline should be conceptually:

Camera
↓
Live Frame
↓
Overlapping Regions
↓
Custom CNN + ResNet-50
↓
Soft Voting
↓
Regional Predictions
↓
Confidence Filtering
↓
Duplicate Suppression
↓
Defect Localization
↓
Final Live Result

A live frame MAY contain multiple defects.

Examples:

Hole + Stain

or:

Hole + Stain + Weaving Error

Do NOT force the entire live frame into only one defect class.

Use overlapping regions rather than only non-overlapping grid cells.

Do NOT blindly choose region size, overlap, or stride.

Consider:

- camera resolution
- camera distance
- visible fabric area
- expected defect size
- processing speed

==================================================
LOCALIZATION
==================================================

Remember that the Custom CNN and ResNet-50 are classification models.

They do NOT directly generate bounding boxes.

For live inspection, regional classification can identify suspicious regions and the existing localization/refinement mechanism can be used to estimate the defect bounding box.

Do not falsely claim that CNN or ResNet-50 directly performs object detection.

Improve localization only using genuine image-processing logic and validation.

Do not fabricate bounding boxes.

==================================================
LIVE DETECTION STABILITY
==================================================

Fix the previously observed live-inspection problems.

A new camera frame must actually be processed.

Do NOT reuse stale predictions.

Do NOT allow one previous frame's prediction to remain permanently displayed when the fabric changes.

Ensure that:

Frame N
↓
Prediction N

Frame N+1
↓
Prediction N+1

The live system must correctly transition between:

Normal
Hole
Stain
Weaving Error

without getting permanently stuck on one class.

If multiple defects are present in the same frame, report the detected defect classes appropriately.

Avoid duplicate detections caused by overlapping regions.

Use appropriate temporal/event logic so that the same physical defect moving through consecutive frames does not repeatedly trigger the motor and audio alert unnecessarily.

==================================================
CONFIDENCE AND FALSE POSITIVES
==================================================

Do not assume that a high classification confidence automatically means the localization is correct.

Keep classification and localization logically separate.

Avoid false positives from normal fabric texture.

Do not blindly lower thresholds just to produce more bounding boxes.

Thresholds must be selected based on validation/testing evidence.

The final system must prioritize genuine detection rather than artificially increasing the number of detections.

==================================================
AUDIO ALERTS
==================================================

There are three different defect sounds:

Hole → Sound 1
Stain → Sound 2
Weaving Error → Sound 3

Normal → No defect sound.

Do not repeatedly play the same sound for every consecutive frame containing the same physical defect.

Play the appropriate sound when a NEW confirmed defect event occurs.

==================================================
ESP32 / CONVEYOR CONTROL
==================================================

The existing ESP32 architecture must be preserved.

Do NOT modify the existing ESP32 code unless necessary and explicitly requested.

When a NEW confirmed defect is detected:

AI detects defect
↓
Send stop request to ESP32
↓
ESP32 stops conveyor
↓
Conveyor remains stopped for 1.5 seconds
↓
Conveyor starts again
↓
Live inspection continues

The conveyor must NOT remain permanently stopped.

The camera inspection must continue after the conveyor restarts.

Do not trigger repeated stop commands for the same physical defect across consecutive frames.

The intended stop duration is:

1.5 seconds

==================================================
WEB DASHBOARD
==================================================

Preserve and improve the existing dashboard rather than destroying the current working interface.

The live GUI should clearly show:

- Camera feed
- Current prediction
- Confidence
- Bounding box
- Defect type
- Detection status
- Motor status
- Inspection status
- Detection history
- Statistics
- Audio alert status

Use a professional and modern interface suitable for a college project demonstration.

If animations are added, keep them meaningful and smooth.

Do not add unnecessary animations that reduce performance.

==================================================
PROJECT STRUCTURE
==================================================

FIRST inspect my existing project.

Do NOT blindly create a new project.

Do NOT delete existing working files.

Reuse existing scripts and folders wherever possible.

Preferred structure:

project/
│
├── dataset/
│   ├── original/
│   │   ├── normal/
│   │   ├── hole/
│   │   ├── stain/
│   │   └── weaving_error/
│   │
│   ├── train/
│   ├── val/
│   └── test/
│
├── models/
│   ├── cnn_best.pth
│   └── resnet50_best.pth
│
├── scripts/
│   ├── prepare_dataset.py
│   ├── train_cnn.py
│   ├── evaluate_cnn.py
│   ├── train_resnet50.py
│   ├── evaluate_resnet50.py
│   └── ensemble.py
│
├── outputs/
│   ├── plots/
│   └── reports/
│
├── requirements.txt
│
└── README.md

This is only a preferred structure.

Reuse my actual project structure wherever possible.

==================================================
DEVELOPMENT ORDER
==================================================

Follow this order strictly:

STEP 1
Inspect existing project.

STEP 2
Inspect current dataset.

STEP 3
Select exactly 250 images from EACH of the four classes.

If a class has more than 250:
→ use only 250 for this experiment
→ do not delete the remaining images.

STEP 4
Check for:

- corrupt images
- duplicates
- near-duplicates
- wrong labels
- suspicious processed images
- unsuitable images

STEP 5
Split the selected ORIGINAL images into:

Train
Validation
Test

before augmentation.

STEP 6
Augment TRAINING images only to approximately 4000 TOTAL training images.

STEP 7
Train Custom CNN FROM SCRATCH.

STEP 8
Evaluate Custom CNN.

STOP AND REPORT RESULTS.

STEP 9
Train ResNet-50.

STEP 10
Evaluate ResNet-50.

STOP AND REPORT RESULTS.

STEP 11
Implement/evaluate Soft-Voting Ensemble.

STOP AND REPORT FINAL ENSEMBLE RESULTS.

STEP 12
Verify live webcam inference.

STEP 13
Verify overlapping-region multiple-defect inference.

STEP 14
Verify bounding-box localization.

STEP 15
Verify audio alerts.

STEP 16
Verify ESP32 conveyor control.

STEP 17
Verify 1.5-second motor stop and automatic restart.

STEP 18
Verify complete live demonstration workflow.

==================================================
MOST IMPORTANT REQUIREMENTS
==================================================

1. Start training from scratch.
2. Use exactly 250 original images per class for this experiment.
3. Do not delete images beyond the selected 250.
4. Total selected original images = 1000.
5. Generate approximately 4000 training images through realistic augmentation.
6. Only training images may be augmented.
7. Validation and test images must remain untouched.
8. Input size = 224 × 224.
9. Use ImageNet normalization.
10. Exactly four classes.
11. Custom CNN first.
12. ResNet-50 second.
13. Soft-voting ensemble after both models.
14. Use probability-based soft voting.
15. Use the same untouched test set for all models.
16. Do not fabricate results.
17. Do not use YOLO.
18. Do not create thousands of unnecessary crops.
19. Preserve the existing project.
20. Live inference must support multiple defects through overlapping regions.
21. Do not allow stale predictions.
22. Do not repeatedly trigger the same physical defect.
23. Three different sounds for the three defect types.
24. Confirmed defect → ESP32 → conveyor stops for 1.5 seconds → conveyor restarts.
25. Do not modify ESP32 code unnecessarily.
26. Keep classification and localization logically separate.
27. The final reported metrics must come from the untouched test set.

START WITH DATASET INSPECTION AND PREPARATION.

Before modifying anything, inspect my existing project and report:

1. Current folder structure
2. Current dataset structure
3. Number of images in each class
4. Which 250 images will be selected from each class
5. Duplicate/corrupt/suspicious image findings
6. Existing scripts that can be reused
7. Existing models/checkpoints
8. Existing preprocessing
9. Existing training configuration
10. Existing live inference and ESP32 integration

Do not start ResNet-50, ensemble, live multi-defect inference, or ESP32 modifications until the required previous stages are successfully completed.