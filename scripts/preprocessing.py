"""
Data Preprocessing Module for Handloom Fabric Defect Detection

Handles:
- Image normalization (ImageNet stats)
- Resizing and augmentation
- PyTorch DataLoader creation
- Training/validation/test split handling
"""

import os
import cv2
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image
import json
from pathlib import Path


# ImageNet normalization statistics
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# Dataset configuration
IMG_SIZE = 224
BATCH_SIZE_TRAIN = 16
BATCH_SIZE_VAL = 32
BATCH_SIZE_TEST = 32
NUM_WORKERS = 0  # Set to 0 for Windows compatibility


class FabricDefectDataset(Dataset):
    """Custom PyTorch Dataset for Fabric Defect images"""
    
    def __init__(self, img_dir, class_names=None, transform=None):
        """
        Args:
            img_dir: Path to directory containing class subdirectories
            class_names: List of class names (auto-detected if None)
            transform: torchvision transforms to apply
        """
        self.img_dir = Path(img_dir)
        self.transform = transform
        
        # Auto-detect classes from subdirectories
        if class_names is None:
            self.classes = sorted([d.name for d in self.img_dir.iterdir() 
                                 if d.is_dir() and not d.name.startswith('.')])
        else:
            self.classes = class_names
            
        self.class_to_idx = {cls: i for i, cls in enumerate(self.classes)}
        self.images = []
        self.labels = []
        
        # Load image paths and labels
        for class_name in self.classes:
            class_dir = self.img_dir / class_name
            if not class_dir.exists():
                print(f"Warning: Class directory not found: {class_dir}")
                continue
                
            for img_file in class_dir.glob("*.jpg"):
                self.images.append(str(img_file))
                self.labels.append(self.class_to_idx[class_name])
        
        print(f"Loaded {len(self.images)} images from {len(self.classes)} classes")
        for cls, idx in self.class_to_idx.items():
            count = sum(1 for l in self.labels if l == idx)
            print(f"  {cls}: {count} images")
    
    def __len__(self):
        return len(self.images)
    
    def __getitem__(self, idx):
        img_path = self.images[idx]
        label = self.labels[idx]
        
        # Load image
        img = Image.open(img_path).convert('RGB')
        
        # Apply transforms
        if self.transform:
            img = self.transform(img)
        
        return img, label
    
    def get_class_names(self):
        return self.classes
    
    def get_class_counts(self):
        """Return count of images per class"""
        counts = {}
        for cls, idx in self.class_to_idx.items():
            counts[cls] = sum(1 for l in self.labels if l == idx)
        return counts


def get_train_transforms():
    """Training augmentation pipeline"""
    return transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomVerticalFlip(p=0.5),
        transforms.RandomRotation(degrees=15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.RandomAffine(degrees=0, translate=(0.1, 0.1)),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)
    ])


def get_val_transforms():
    """Validation/Test pipeline (no augmentation)"""
    return transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)
    ])


def create_dataloaders(data_dir, batch_size_train=BATCH_SIZE_TRAIN, 
                       batch_size_val=BATCH_SIZE_VAL, batch_size_test=BATCH_SIZE_TEST):
    """
    Create PyTorch DataLoaders for train/val/test splits
    
    Args:
        data_dir: Parent directory containing 'train', 'val', 'test' subdirectories
        batch_size_train: Batch size for training
        batch_size_val: Batch size for validation
        batch_size_test: Batch size for testing
    
    Returns:
        dict with keys 'train', 'val', 'test' containing DataLoader objects
        dict with class names
        dict with sample counts per split
    """
    data_dir = Path(data_dir)
    
    # Check directory structure
    required_splits = ['train', 'val', 'test']
    for split in required_splits:
        if not (data_dir / split).exists():
            raise FileNotFoundError(f"Missing split directory: {data_dir / split}")
    
    # Get class names from train split
    train_classes = sorted([d.name for d in (data_dir / 'train').iterdir() 
                           if d.is_dir() and not d.name.startswith('.')])
    
    print("\n" + "="*60)
    print("CREATING DATA LOADERS")
    print("="*60)
    
    # Training dataset with augmentation
    print("\nTrain split:")
    train_dataset = FabricDefectDataset(
        data_dir / 'train',
        class_names=train_classes,
        transform=get_train_transforms()
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size_train,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=True
    )
    
    # Validation dataset without augmentation
    print("\nVal split:")
    val_dataset = FabricDefectDataset(
        data_dir / 'val',
        class_names=train_classes,
        transform=get_val_transforms()
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size_val,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=True
    )
    
    # Test dataset without augmentation
    print("\nTest split:")
    test_dataset = FabricDefectDataset(
        data_dir / 'test',
        class_names=train_classes,
        transform=get_val_transforms()
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size_test,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=True
    )
    
    dataloaders = {
        'train': train_loader,
        'val': val_loader,
        'test': test_loader
    }
    
    counts = {
        'train': train_dataset.get_class_counts(),
        'val': val_dataset.get_class_counts(),
        'test': test_dataset.get_class_counts()
    }
    
    print("\n" + "="*60)
    print("DATA LOADER SUMMARY")
    print("="*60)
    print(f"Train batches: {len(train_loader)} (batch_size={batch_size_train})")
    print(f"Val batches: {len(val_loader)} (batch_size={batch_size_val})")
    print(f"Test batches: {len(test_loader)} (batch_size={batch_size_test})")
    print(f"\nClass names: {train_classes}")
    print(f"Total samples: {len(train_dataset) + len(val_dataset) + len(test_dataset)}")
    
    return dataloaders, train_classes, counts


def get_data_info(data_dir):
    """Get information about dataset without loading"""
    data_dir = Path(data_dir)
    
    info = {}
    for split in ['train', 'val', 'test']:
        split_dir = data_dir / split
        if not split_dir.exists():
            continue
        
        classes = sorted([d.name for d in split_dir.iterdir() if d.is_dir()])
        info[split] = {}
        
        for cls in classes:
            cls_dir = split_dir / cls
            count = len(list(cls_dir.glob("*.jpg")))
            info[split][cls] = count
    
    return info


def save_preprocessing_config(output_dir, img_size=IMG_SIZE, 
                             mean=IMAGENET_MEAN, std=IMAGENET_STD):
    """Save preprocessing configuration for inference"""
    config = {
        'image_size': img_size,
        'normalization_mean': mean,
        'normalization_std': std,
        'transforms': {
            'resize': img_size,
            'normalize': {
                'mean': mean,
                'std': std
            }
        }
    }
    
    output_path = Path(output_dir) / 'preprocessing_config.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=4)
    
    print(f"Saved preprocessing config to {output_path}")
    return output_path


if __name__ == '__main__':
    # Example usage
    data_dir = 'dataset'
    
    if os.path.exists(data_dir):
        print("Dataset Information:")
        info = get_data_info(data_dir)
        for split, classes in info.items():
            print(f"\n{split.upper()}:")
            total = sum(classes.values())
            for cls, count in classes.items():
                print(f"  {cls}: {count}")
            print(f"  Total: {total}")
        
        # Try to create dataloaders if dataset exists
        if all((Path(data_dir) / split).exists() for split in ['train', 'val', 'test']):
            print("\n\nCreating DataLoaders...")
            dataloaders, class_names, counts = create_dataloaders(data_dir)
            
            # Test with a batch
            print("\nTesting train loader with first batch:")
            batch_imgs, batch_labels = next(iter(dataloaders['train']))
            print(f"Batch shape: {batch_imgs.shape}")
            print(f"Batch labels: {batch_labels}")
            print(f"Image stats - Min: {batch_imgs.min():.3f}, Max: {batch_imgs.max():.3f}, Mean: {batch_imgs.mean():.3f}")
            
            # Save config
            save_preprocessing_config('outputs')
    else:
        print(f"Dataset directory '{data_dir}' not found!")
        print("Run prepare_dataset.py first")
