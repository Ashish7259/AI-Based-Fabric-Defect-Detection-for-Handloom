"""
Handloom Fabric Defect Detection System – Dataset Preparation
=============================================================
1.  Map actual folder names to class labels.
2.  Select exactly IMAGES_PER_CLASS images from each class (sorted, first-N).
3.  Detect corrupt / duplicate images.
4.  Stratified split: 70 % train / 15 % val / 15 % test.
5.  Augment ONLY training images → ≈ 4 000 total training images.
6.  Validation and test images remain completely untouched.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from sklearn.model_selection import train_test_split

# ── paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "dataset"
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "outputs" / "reports"

# ── mapping: actual folder name → canonical class label ─────────────────────
FOLDER_TO_CLASS = {
    "Normal": "normal",
    "Hole": "hole",
    "Stain": "stain",
    "Weaving": "weaving_error",
}
CLASSES = list(FOLDER_TO_CLASS.values())           # deterministic order
IMAGES_PER_CLASS = 242                             # smallest class has 242
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

# ── augmentation target ─────────────────────────────────────────────────────
TARGET_TRAIN_TOTAL = 4000                          # ≈ total augmented train set

SEED = 42
random.seed(SEED)
np.random.seed(SEED)


# ─────────────────────────────────────────────────────────────────────────────
# Image helpers
# ─────────────────────────────────────────────────────────────────────────────
def is_valid_image(path: Path) -> bool:
    """Return True if *path* is an intact, non-zero-size image."""
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            w, h = img.size
            return w > 0 and h > 0
    except Exception:
        return False


def compute_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# 1 · Collect & validate images
# ─────────────────────────────────────────────────────────────────────────────
def collect_images() -> Tuple[Dict[str, List[Path]], List[str]]:
    """Return {class_label: [paths]} and a list of issues encountered."""
    grouped: Dict[str, List[Path]] = {c: [] for c in CLASSES}
    issues: List[str] = []

    for folder_name, class_label in FOLDER_TO_CLASS.items():
        folder = DATA_ROOT / folder_name
        if not folder.exists():
            issues.append(f"Missing directory: {folder}")
            continue

        for p in sorted(folder.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in VALID_EXTENSIONS:
                issues.append(f"Skipping non-image: {p.name}")
                continue
            if not is_valid_image(p):
                issues.append(f"Corrupt image: {p.name}")
                continue
            grouped[class_label].append(p)

    return grouped, issues


# ─────────────────────────────────────────────────────────────────────────────
# 2 · Duplicate detection
# ─────────────────────────────────────────────────────────────────────────────
def find_duplicates(grouped: Dict[str, List[Path]]) -> List[Tuple[Path, Path]]:
    seen: Dict[str, Path] = {}
    dupes: List[Tuple[Path, Path]] = []
    for paths in grouped.values():
        for p in paths:
            h = compute_hash(p)
            if h in seen:
                dupes.append((p, seen[h]))
            else:
                seen[h] = p
    return dupes


# ─────────────────────────────────────────────────────────────────────────────
# 3 · Select IMAGES_PER_CLASS per class
# ─────────────────────────────────────────────────────────────────────────────
def select_images(grouped: Dict[str, List[Path]]) -> Dict[str, List[Path]]:
    selected: Dict[str, List[Path]] = {}
    for cls, paths in grouped.items():
        n = min(len(paths), IMAGES_PER_CLASS)
        selected[cls] = paths[:n]  # already sorted
    return selected


# ─────────────────────────────────────────────────────────────────────────────
# 4 · Stratified split  (70 / 15 / 15)
# ─────────────────────────────────────────────────────────────────────────────
def split_dataset(
    selected: Dict[str, List[Path]],
) -> Dict[str, List[Tuple[Path, str]]]:
    splits: Dict[str, List[Tuple[Path, str]]] = {"train": [], "val": [], "test": []}

    for cls, paths in selected.items():
        labels = [cls] * len(paths)
        train_paths, temp_paths = train_test_split(
            paths, test_size=0.30, random_state=SEED, shuffle=True, stratify=labels,
        )
        val_paths, test_paths = train_test_split(
            temp_paths,
            test_size=0.50,
            random_state=SEED,
            shuffle=True,
            stratify=[cls] * len(temp_paths),
        )
        splits["train"].extend([(p, cls) for p in train_paths])
        splits["val"].extend([(p, cls) for p in val_paths])
        splits["test"].extend([(p, cls) for p in test_paths])

    return splits


# ─────────────────────────────────────────────────────────────────────────────
# 5 · Copy originals into split directories
# ─────────────────────────────────────────────────────────────────────────────
def copy_splits(
    splits: Dict[str, List[Tuple[Path, str]]],
) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = {}

    for split_name in ("train", "val", "test"):
        split_dir = DATA_ROOT / split_name
        if split_dir.exists():
            shutil.rmtree(split_dir)

        per_class: Dict[str, int] = {}
        for src, cls in splits[split_name]:
            dst_dir = split_dir / cls
            dst_dir.mkdir(parents=True, exist_ok=True)
            # Prefix filename with class to avoid cross-class name collisions
            dst_name = f"{cls}_{src.name}"
            shutil.copy2(src, dst_dir / dst_name)
            per_class[cls] = per_class.get(cls, 0) + 1
        counts[split_name] = per_class

    return counts


# ─────────────────────────────────────────────────────────────────────────────
# 6 · Realistic augmentation (training images only)
# ─────────────────────────────────────────────────────────────────────────────
def augment_image(img: Image.Image, aug_index: int) -> Image.Image:
    """Apply a deterministic-ish combination of fabric-safe augmentations."""
    rng = random.Random(aug_index)
    out = img.copy()

    # Random rotation (±15°)
    angle = rng.uniform(-15, 15)
    out = out.rotate(angle, resample=Image.BILINEAR, fillcolor=(128, 128, 128))

    # Random horizontal flip
    if rng.random() < 0.5:
        out = out.transpose(Image.FLIP_LEFT_RIGHT)

    # Random vertical flip (fabric can be viewed from either side)
    if rng.random() < 0.3:
        out = out.transpose(Image.FLIP_TOP_BOTTOM)

    # Brightness jitter
    factor = rng.uniform(0.8, 1.2)
    out = ImageEnhance.Brightness(out).enhance(factor)

    # Contrast jitter
    factor = rng.uniform(0.85, 1.15)
    out = ImageEnhance.Contrast(out).enhance(factor)

    # Slight color shift
    factor = rng.uniform(0.9, 1.1)
    out = ImageEnhance.Color(out).enhance(factor)

    # Slight sharpness variation
    factor = rng.uniform(0.8, 1.3)
    out = ImageEnhance.Sharpness(out).enhance(factor)

    # Optional Gaussian blur
    if rng.random() < 0.2:
        out = out.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.3, 1.0)))

    return out


def augment_training_set(train_dir: Path, target_total: int) -> int:
    """Augment images in *train_dir* (in-place) until ≈ target_total images."""
    class_dirs = sorted([d for d in train_dir.iterdir() if d.is_dir()])
    num_classes = len(class_dirs)
    target_per_class = target_total // num_classes

    total_created = 0
    for cls_dir in class_dirs:
        originals = sorted([
            p for p in cls_dir.iterdir()
            if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS
        ])
        n_orig = len(originals)
        n_needed = max(0, target_per_class - n_orig)

        aug_idx = 0
        while aug_idx < n_needed:
            src = originals[aug_idx % n_orig]
            with Image.open(src) as img:
                img = img.convert("RGB")
                aug = augment_image(img, aug_idx + 1000)
                stem = src.stem
                out_name = f"{stem}_aug{aug_idx:04d}.jpg"
                aug.save(cls_dir / out_name, "JPEG", quality=95)
            aug_idx += 1
            total_created += 1

    return total_created


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # 1 · Collect
    print("=" * 60)
    print("STEP 1 -- Collecting images")
    print("=" * 60)
    grouped, issues = collect_images()
    for cls, paths in grouped.items():
        print(f"  {cls}: {len(paths)} images found")
    if issues:
        print(f"\n  Issues ({len(issues)}):")
        for iss in issues[:20]:
            print(f"    - {iss}")
        if len(issues) > 20:
            print(f"    ... and {len(issues) - 20} more")

    # 2 · Duplicates
    print("\n" + "=" * 60)
    print("STEP 2 -- Checking for duplicates")
    print("=" * 60)
    dupes = find_duplicates(grouped)
    if dupes:
        print(f"  Found {len(dupes)} duplicate(s):")
        for a, b in dupes[:10]:
            print(f"    - {a.name}  <->  {b.name}")
    else:
        print("  No duplicates found [OK]")

    # 3 · Select
    print("\n" + "=" * 60)
    print(f"STEP 3 -- Selecting {IMAGES_PER_CLASS} images per class")
    print("=" * 60)
    selected = select_images(grouped)
    for cls, paths in selected.items():
        print(f"  {cls}: {len(paths)} selected")
    total_selected = sum(len(v) for v in selected.values())
    print(f"  Total selected: {total_selected}")

    # 4 · Split
    print("\n" + "=" * 60)
    print("STEP 4 -- Splitting into train / val / test")
    print("=" * 60)
    splits = split_dataset(selected)

    # 5 · Copy
    counts = copy_splits(splits)
    for split_name, per_class in counts.items():
        total = sum(per_class.values())
        print(f"  {split_name}: {total} total  ->  {per_class}")

    # Verify no overlap — use full source paths (not just basenames, since
    # different classes can legitimately share the same filename)
    split_files: Dict[str, set] = {}
    for sn in ("train", "val", "test"):
        split_files[sn] = {str(p) for p, _ in splits[sn]}
    for a, b in [("train", "val"), ("train", "test"), ("val", "test")]:
        overlap = split_files[a] & split_files[b]
        assert len(overlap) == 0, f"DATA LEAK: {len(overlap)} files in both {a} and {b}"
    print("  [OK] No overlap between splits")

    # 6 · Augment training set
    print("\n" + "=" * 60)
    print(f"STEP 5 -- Augmenting training set to ~{TARGET_TRAIN_TOTAL} images")
    print("=" * 60)
    train_dir = DATA_ROOT / "train"
    train_before = sum(1 for _ in train_dir.rglob("*") if _.is_file())
    n_aug = augment_training_set(train_dir, TARGET_TRAIN_TOTAL)
    train_after = sum(1 for _ in train_dir.rglob("*") if _.is_file())
    print(f"  Training images before augmentation: {train_before}")
    print(f"  Augmented images created:            {n_aug}")
    print(f"  Training images after augmentation:  {train_after}")

    # Per-class counts after augmentation
    print("\n  Per-class counts (after augmentation):")
    for cls_dir in sorted(train_dir.iterdir()):
        if cls_dir.is_dir():
            n = sum(1 for f in cls_dir.iterdir() if f.is_file())
            print(f"    {cls_dir.name}: {n}")

    # 7 · Save summary
    final_counts = {}
    for split_name in ("train", "val", "test"):
        sd = DATA_ROOT / split_name
        final_counts[split_name] = {}
        for cls_dir in sorted(sd.iterdir()):
            if cls_dir.is_dir():
                final_counts[split_name][cls_dir.name] = sum(
                    1 for f in cls_dir.iterdir() if f.is_file()
                )

    summary = {
        "images_per_class_selected": IMAGES_PER_CLASS,
        "total_selected": total_selected,
        "classes": CLASSES,
        "split_counts": final_counts,
        "augmentation_target": TARGET_TRAIN_TOTAL,
        "duplicates_found": len(dupes),
        "issues": issues,
        "seed": SEED,
    }
    summary_path = REPORTS_DIR / "dataset_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("DONE [OK]")
    print("=" * 60)
    print(f"  Summary saved to {summary_path}")


if __name__ == "__main__":
    main()
