"""
Handloom Fabric Defect Detection System – Soft-Voting Ensemble
==============================================================
Loads both trained models (Custom CNN + ResNet-50), performs
probability-based soft voting on the untouched test set,
and reports all metrics.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from torch.utils.data import DataLoader
from torchvision import transforms
from torchvision.models import resnet50

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
from scripts.train_cnn import FabricCNN, ImageFolderWithPaths

# ── paths ───────────────────────────────────────────────────────────────────
DATA_ROOT = ROOT / "dataset"
MODELS_DIR = ROOT / "models"
PLOTS_DIR = ROOT / "outputs" / "plots"
REPORTS_DIR = ROOT / "outputs" / "reports"

BATCH_SIZE = 16
SEED = 42

os.makedirs(PLOTS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)


def seed_everything(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


# ─────────────────────────────────────────────────────────────────────────────
# Data loader (same transform as val/test — no augmentation)
# ─────────────────────────────────────────────────────────────────────────────
def build_dataloaders() -> Tuple[Dict[str, DataLoader], List[str]]:
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    test_ds = ImageFolderWithPaths(DATA_ROOT / "test", transform=transform)
    classes = test_ds.classes
    loaders = {
        "test": DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0),
    }
    return loaders, classes


# ─────────────────────────────────────────────────────────────────────────────
# Model loaders — architectures MUST match the training scripts exactly
# ─────────────────────────────────────────────────────────────────────────────
def build_cnn_model(num_classes: int, device: torch.device) -> nn.Module:
    """Load the Custom CNN with the same architecture as train_cnn.py."""
    model = FabricCNN(num_classes=num_classes).to(device)
    state = torch.load(MODELS_DIR / "cnn_best.pth", map_location=device, weights_only=True)
    model.load_state_dict(state)
    model.eval()
    return model


def build_resnet_model(num_classes: int, device: torch.device) -> nn.Module:
    """Load ResNet-50 with the same head as train_resnet50.py."""
    model = resnet50(weights=None)
    model.fc = nn.Sequential(
        nn.Dropout(0.4),
        nn.Linear(model.fc.in_features, num_classes),
    )
    state = torch.load(MODELS_DIR / "resnet50_best.pth", map_location=device, weights_only=True)
    model.load_state_dict(state)
    model = model.to(device)
    model.eval()
    return model


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────
def compute_metrics(y_true: List[int], y_pred: List[int]) -> Dict[str, float]:
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision_macro": precision_score(y_true, y_pred, average="macro", zero_division=0),
        "recall_macro": recall_score(y_true, y_pred, average="macro", zero_division=0),
        "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Ensemble evaluation
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_ensemble(
    cnn: nn.Module,
    resnet: nn.Module,
    loader: DataLoader,
    classes: List[str],
    device: torch.device,
) -> Tuple[Dict[str, float], np.ndarray, dict]:
    cnn.eval()
    resnet.eval()
    y_true, y_pred = [], []

    with torch.no_grad():
        for images, labels, _ in loader:
            images = images.to(device)
            cnn_prob = torch.softmax(cnn(images), dim=1).cpu().numpy()
            res_prob = torch.softmax(resnet(images), dim=1).cpu().numpy()
            # Equal-weight soft voting
            ensemble_prob = (cnn_prob + res_prob) / 2.0
            pred = ensemble_prob.argmax(axis=1)
            y_true.extend(labels.tolist())
            y_pred.extend(pred.tolist())

    metrics = compute_metrics(y_true, y_pred)
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(classes))))
    report = classification_report(
        y_true, y_pred,
        labels=list(range(len(classes))),
        target_names=classes,
        output_dict=True,
        zero_division=0,
    )
    return metrics, cm, report


# ─────────────────────────────────────────────────────────────────────────────
# Plots
# ─────────────────────────────────────────────────────────────────────────────
def save_confusion_matrix(cm: np.ndarray, classes: List[str]) -> None:
    plt.figure(figsize=(7, 6))
    plt.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    plt.title("Soft-Voting Ensemble – Confusion Matrix")
    plt.colorbar()
    ticks = np.arange(len(classes))
    plt.xticks(ticks, classes, rotation=45, ha="right")
    plt.yticks(ticks, classes)
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            plt.text(
                j, i, cm[i, j], ha="center", va="center",
                color="white" if cm[i, j] > thresh else "black",
            )
    plt.ylabel("True label")
    plt.xlabel("Predicted label")
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "ensemble_confusion_matrix.png", dpi=150)
    plt.close()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    seed_everything()
    device = get_device()
    print(f"Device: {device}")

    loaders, classes = build_dataloaders()
    print(f"Classes: {classes}")
    print(f"  Test set: {len(loaders['test'].dataset)} images")

    print("Loading Custom CNN …")
    cnn = build_cnn_model(num_classes=len(classes), device=device)
    print("Loading ResNet-50 …")
    resnet_model = build_resnet_model(num_classes=len(classes), device=device)

    print("\n" + "=" * 60)
    print("Soft-Voting Ensemble — Evaluating on TEST set")
    print("=" * 60)
    metrics, cm, report = evaluate_ensemble(cnn, resnet_model, loaders["test"], classes, device)
    save_confusion_matrix(cm, classes)

    # Save reports
    (REPORTS_DIR / "ensemble_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    with open(REPORTS_DIR / "ensemble_classification_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\nEnsemble Metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")
    print(f"\nConfusion Matrix:\n{cm}")
    print(f"\nPlots saved to {PLOTS_DIR}")
    print(f"Reports saved to {REPORTS_DIR}")


if __name__ == "__main__":
    main()
