"""
Handloom Fabric Defect Detection System – Custom CNN Training
=============================================================
Deeper 6-block CNN (64→128→256→512) with BatchNorm, Dropout,
label smoothing, cosine-annealing LR, class-weighted loss,
and early stopping.  Trains from scratch on the prepared dataset.
"""
from __future__ import annotations

import json
import os
import random
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
from torchvision import datasets, transforms

# ── paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "dataset"
MODELS_DIR = ROOT / "models"
PLOTS_DIR = ROOT / "outputs" / "plots"
REPORTS_DIR = ROOT / "outputs" / "reports"

# ── hyper-parameters ────────────────────────────────────────────────────────
IMAGE_SIZE = 224
BATCH_SIZE = 16
EPOCHS = 25
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-4
LABEL_SMOOTHING = 0.1
EARLY_STOP_PATIENCE = 8
SEED = 42

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

import sys
# Import preprocessing module
sys.path.insert(0, str(Path(__file__).parent))
from preprocessing import create_dataloaders

def seed_everything(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


# ─────────────────────────────────────────────────────────────────────────────
# Model – deeper CNN with 6 conv blocks
# ─────────────────────────────────────────────────────────────────────────────
class FabricCNN(nn.Module):
    """
    6-block CNN progressing 64 → 128 → 256 → 512 channels.
    Each block: Conv3×3 → BN → ReLU → Conv3×3 → BN → ReLU → MaxPool.
    Global average pool → FC(512→256) → Dropout → FC(256→num_classes).
    """

    def __init__(self, num_classes: int = 4) -> None:
        super().__init__()
        self.features = nn.Sequential(
            # Block 1  (3 → 64)
            nn.Conv2d(3, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            # Block 2  (64 → 128)
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.Conv2d(128, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            # Block 3  (128 → 256)
            nn.Conv2d(128, 256, 3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Conv2d(256, 256, 3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            # Block 4  (256 → 512)
            nn.Conv2d(256, 512, 3, padding=1),
            nn.BatchNorm2d(512),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Linear(512, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.35),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.pool(x).flatten(1)
        return self.classifier(x)


# ─────────────────────────────────────────────────────────────────────────────
# Dataset utilities
# ─────────────────────────────────────────────────────────────────────────────
class ImageFolderWithPaths(datasets.ImageFolder):
    """ImageFolder that also returns the file path for each sample."""

    def __getitem__(self, index: int):
        sample, target = super().__getitem__(index)
        path = self.samples[index][0]
        return sample, target, path


def build_dataloaders() -> Tuple[Dict[str, DataLoader], Dict[str, datasets.ImageFolder], List[str]]:
    train_transform = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.85, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(p=0.2),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.10, hue=0.02),
        transforms.RandomAffine(degrees=0, translate=(0.05, 0.05)),
        transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 1.0)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        transforms.RandomErasing(p=0.1, scale=(0.02, 0.08)),
    ])
    val_test_transform = transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    train_ds = ImageFolderWithPaths(DATA_ROOT / "train", transform=train_transform)
    val_ds   = ImageFolderWithPaths(DATA_ROOT / "val",   transform=val_test_transform)
    test_ds  = ImageFolderWithPaths(DATA_ROOT / "test",  transform=val_test_transform)

    loaders = {
        "train": DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0),
        "val":   DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False, num_workers=0),
        "test":  DataLoader(test_ds,  batch_size=BATCH_SIZE, shuffle=False, num_workers=0),
    }
    classes = train_ds.classes
    return loaders, train_ds, classes


# ─────────────────────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────────────────────
def train_model(
    model: nn.Module,
    loaders: Dict[str, DataLoader],
    classes: List[str],
    device: torch.device,
) -> Tuple[List[float], List[float], List[float], List[float]]:
    num_classes = len(classes)
    class_counts = np.bincount(loaders["train"].dataset.targets, minlength=num_classes)
    class_counts = np.clip(class_counts, 1, None)
    weights = torch.tensor(
        (class_counts.max() / class_counts).astype(np.float32), dtype=torch.float32
    )
    criterion = nn.CrossEntropyLoss(
        weight=weights.to(device), label_smoothing=LABEL_SMOOTHING
    )

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=10, T_mult=2
    )

    best_val_loss = float("inf")
    best_state = None
    patience_counter = 0

    train_losses, val_losses, train_accs, val_accs = [], [], [], []

    for epoch in range(EPOCHS):
        # ── train ────────────────────────────────────────────────────────
        model.train()
        running_loss, correct, total = 0.0, 0, 0
        for images, labels, _ in loaders["train"]:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()

            running_loss += loss.item() * images.size(0)
            correct += (outputs.argmax(1) == labels).sum().item()
            total += labels.size(0)

        train_loss = running_loss / total
        train_acc = correct / total
        train_losses.append(train_loss)
        train_accs.append(train_acc)

        # ── validate ─────────────────────────────────────────────────────
        model.eval()
        vloss, vcorrect, vtotal = 0.0, 0, 0
        with torch.no_grad():
            for images, labels, _ in loaders["val"]:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                loss = criterion(outputs, labels)
                vloss += loss.item() * images.size(0)
                vcorrect += (outputs.argmax(1) == labels).sum().item()
                vtotal += labels.size(0)

        val_loss = vloss / vtotal
        val_acc = vcorrect / vtotal
        val_losses.append(val_loss)
        val_accs.append(val_acc)

        scheduler.step(epoch + val_loss / 10)  # fractional epoch for warm restarts

        lr_now = optimizer.param_groups[0]["lr"]
        print(
            f"Epoch {epoch + 1:3d}/{EPOCHS} │ "
            f"train_loss={train_loss:.4f}  val_loss={val_loss:.4f} │ "
            f"train_acc={train_acc:.4f}  val_acc={val_acc:.4f} │ lr={lr_now:.2e}"
        )

        # ── early stopping ───────────────────────────────────────────────
        if val_loss < best_val_loss - 1e-4:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= EARLY_STOP_PATIENCE:
                print(f"Early stopping at epoch {epoch + 1}.")
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    return train_losses, val_losses, train_accs, val_accs


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
# Evaluation
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_model(
    model: nn.Module,
    loader: DataLoader,
    classes: List[str],
    device: torch.device,
) -> Tuple[Dict[str, float], np.ndarray, dict]:
    model.eval()
    y_true, y_pred = [], []
    with torch.no_grad():
        for images, labels, _ in loader:
            images, labels = images.to(device), labels.to(device)
            pred = model(images).argmax(1)
            y_true.extend(labels.cpu().tolist())
            y_pred.extend(pred.cpu().tolist())

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
def save_plots(tl, vl, ta, va) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].plot(tl, label="train_loss")
    axes[0].plot(vl, label="val_loss")
    axes[0].set_title("Custom CNN – Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(ta, label="train_acc")
    axes[1].plot(va, label="val_acc")
    axes[1].set_title("Custom CNN – Accuracy")
    axes[1].set_xlabel("Epoch")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "cnn_training_curves.png", dpi=150)
    plt.close(fig)


def save_confusion_matrix(cm: np.ndarray, classes: List[str]) -> None:
    plt.figure(figsize=(7, 6))
    plt.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    plt.title("Custom CNN – Confusion Matrix")
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
    plt.savefig(PLOTS_DIR / "cnn_confusion_matrix.png", dpi=150)
    plt.close()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    seed_everything()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    loaders, ds_map, classes = build_dataloaders()
    print(f"Classes: {classes}")
    for name, loader in loaders.items():
        print(f"  {name}: {len(loader.dataset)} images")

    model = FabricCNN(num_classes=len(classes)).to(device)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"  Model parameters: {total_params:,}")

    tl, vl, ta, va = train_model(model, loaders, classes, device)
    save_plots(tl, vl, ta, va)

    print("\n" + "=" * 60)
    print("Evaluating on TEST set")
    print("=" * 60)
    metrics, cm, report = evaluate_model(model, loaders["test"], classes, device)
    save_confusion_matrix(cm, classes)

    # Save model
    torch.save(model.state_dict(), MODELS_DIR / "cnn_best.pth")
    # Save class order
    (MODELS_DIR / "cnn_classes.json").write_text(
        json.dumps(classes, indent=2), encoding="utf-8"
    )

    # Save reports
    (REPORTS_DIR / "cnn_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    with open(REPORTS_DIR / "cnn_classification_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\nTest Metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")
    print(f"\nConfusion Matrix:\n{cm}")
    print(f"\nModel saved to {MODELS_DIR / 'cnn_best.pth'}")
    print(f"Plots saved to {PLOTS_DIR}")
    print(f"Reports saved to {REPORTS_DIR}")


if __name__ == "__main__":
    main()
