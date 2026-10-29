"""
Handloom Fabric Defect Detection System – ResNet-50 Training
============================================================
Transfer learning from ImageNet weights.
Phase 1 (freeze):    Train only FC head.
Phase 2 (fine-tune): Unfreeze layer4 + FC with lower LR.
Uses label smoothing, cosine-annealing LR, class-weighted loss,
gradient clipping, and early stopping.
Trains completely from scratch — no prior checkpoint is loaded.
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
# pyrefly: ignore [missing-import]
import torch
# pyrefly: ignore [missing-import]
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
# pyrefly: ignore [missing-import]
from torch.utils.data import DataLoader
# pyrefly: ignore [missing-import]
from torchvision import transforms
# pyrefly: ignore [missing-import]
from torchvision.models import ResNet50_Weights, resnet50

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
from preprocessing import create_dataloaders

# ── paths ───────────────────────────────────────────────────────────────────
DATA_ROOT = ROOT / "dataset"
MODELS_DIR = ROOT / "models"
PLOTS_DIR = ROOT / "outputs" / "plots"
REPORTS_DIR = ROOT / "outputs" / "reports"

# ── hyper-parameters ────────────────────────────────────────────────────────
IMAGE_SIZE = 224
BATCH_SIZE = 16
FREEZE_EPOCHS = 5            # phase 1 — only FC head
FINE_TUNE_EPOCHS = 20        # phase 2 — layer4 + FC
FREEZE_LR = 1e-3
FINE_TUNE_LR = 1e-5
WEIGHT_DECAY = 1e-4
LABEL_SMOOTHING = 0.1
EARLY_STOP_PATIENCE = 5
SEED = 42

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)


def seed_everything(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


# ─────────────────────────────────────────────────────────────────────────────
# Data loaders
# ─────────────────────────────────────────────────────────────────────────────
def build_dataloaders() -> Tuple[Dict[str, DataLoader], List[str]]:
    """Build dataloaders using preprocessing module"""
    loaders, classes, counts = create_dataloaders(DATA_ROOT, batch_size_train=BATCH_SIZE)
    return loaders, classes


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
# Model
# ─────────────────────────────────────────────────────────────────────────────
def build_model(num_classes: int, device: torch.device) -> nn.Module:
    model = resnet50(weights=ResNet50_Weights.DEFAULT)
    # Replace FC with dropout + linear
    model.fc = nn.Sequential(
        nn.Dropout(p=0.4),
        nn.Linear(model.fc.in_features, num_classes),
    )
    # Freeze everything except FC
    for name, param in model.named_parameters():
        if not name.startswith("fc"):
            param.requires_grad = False
    return model.to(device)


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
    # Get class counts from dataset labels
    class_counts = np.bincount(loaders["train"].dataset.labels, minlength=num_classes)
    class_counts = np.clip(class_counts, 1, None)
    weights = torch.tensor(
        (class_counts.max() / class_counts).astype(np.float32), dtype=torch.float32
    )
    criterion = nn.CrossEntropyLoss(
        weight=weights.to(device), label_smoothing=LABEL_SMOOTHING
    )

    total_epochs = FREEZE_EPOCHS + FINE_TUNE_EPOCHS
    train_losses, val_losses, train_accs, val_accs = [], [], [], []

    best_val_loss = float("inf")
    best_state = None
    patience_counter = 0

    # Phase 1 optimizer (FC only)
    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=FREEZE_LR, weight_decay=WEIGHT_DECAY,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=FREEZE_EPOCHS)

    for epoch in range(total_epochs):
        # ── phase transition ─────────────────────────────────────────────
        if epoch == FREEZE_EPOCHS:
            # Unfreeze layer4 + FC
            for param in model.layer4.parameters():
                param.requires_grad = True
            for param in model.fc.parameters():
                param.requires_grad = True
            optimizer = torch.optim.AdamW(
                filter(lambda p: p.requires_grad, model.parameters()),
                lr=FINE_TUNE_LR, weight_decay=WEIGHT_DECAY,
            )
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=FINE_TUNE_EPOCHS,
            )
            patience_counter = 0
            best_val_loss = float("inf")
            print("── Phase 2: Fine-tuning layer4 + FC ──")

        fine_tune = epoch >= FREEZE_EPOCHS
        phase_label = "fine-tune" if fine_tune else "freeze"

        # ── train ────────────────────────────────────────────────────────
        model.train()
        running_loss, correct, total = 0.0, 0, 0
        for images, labels in loaders["train"]:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            if fine_tune:
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
            for images, labels in loaders["val"]:
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

        scheduler.step()

        lr_now = optimizer.param_groups[0]["lr"]
        print(
            f"Epoch {epoch + 1:3d}/{total_epochs} [{phase_label:9s}] │ "
            f"train_loss={train_loss:.4f}  val_loss={val_loss:.4f} │ "
            f"train_acc={train_acc:.4f}  val_acc={val_acc:.4f} │ lr={lr_now:.2e}"
        )

        # ── early stopping ───────────────────────────────────────────────
        if val_loss < best_val_loss - 1e-4:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        elif fine_tune:
            patience_counter += 1
            if patience_counter >= EARLY_STOP_PATIENCE:
                print(f"Early stopping at epoch {epoch + 1}.")
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    return train_losses, val_losses, train_accs, val_accs


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
        for images, labels in loader:
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
    axes[0].axvline(FREEZE_EPOCHS - 0.5, color="gray", ls="--", lw=1, label="fine-tune starts")
    axes[0].set_title("ResNet-50 – Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(ta, label="train_acc")
    axes[1].plot(va, label="val_acc")
    axes[1].axvline(FREEZE_EPOCHS - 0.5, color="gray", ls="--", lw=1)
    axes[1].set_title("ResNet-50 – Accuracy")
    axes[1].set_xlabel("Epoch")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "resnet50_training_curves.png", dpi=150)
    plt.close(fig)


def save_confusion_matrix(cm: np.ndarray, classes: List[str]) -> None:
    plt.figure(figsize=(7, 6))
    plt.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    plt.title("ResNet-50 – Confusion Matrix")
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
    plt.savefig(PLOTS_DIR / "resnet50_confusion_matrix.png", dpi=150)
    plt.close()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    seed_everything()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    loaders, classes = build_dataloaders()
    print(f"Classes: {classes}")
    for name, loader in loaders.items():
        print(f"  {name}: {len(loader.dataset)} images")

    model = build_model(num_classes=len(classes), device=device)
    total_params = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  Total params: {total_params:,}  |  Trainable (phase 1): {trainable:,}")

    tl, vl, ta, va = train_model(model, loaders, classes, device)
    save_plots(tl, vl, ta, va)

    print("\n" + "=" * 60)
    print("Evaluating on TEST set")
    print("=" * 60)
    metrics, cm, report = evaluate_model(model, loaders["test"], classes, device)
    save_confusion_matrix(cm, classes)

    # Save model
    torch.save(model.state_dict(), MODELS_DIR / "resnet50_best.pth")
    (MODELS_DIR / "resnet50_classes.json").write_text(
        json.dumps(classes, indent=2), encoding="utf-8"
    )

    # Save reports
    (REPORTS_DIR / "resnet50_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    with open(REPORTS_DIR / "resnet50_classification_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\nTest Metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")
    print(f"\nConfusion Matrix:\n{cm}")
    print(f"\nModel saved to {MODELS_DIR / 'resnet50_best.pth'}")
    print(f"Plots saved to {PLOTS_DIR}")
    print(f"Reports saved to {REPORTS_DIR}")


if __name__ == "__main__":
    main()