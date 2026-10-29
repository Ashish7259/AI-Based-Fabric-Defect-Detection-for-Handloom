from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import torch
from PIL import Image
from torchvision import transforms

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"

try:
    from scripts.ensemble import build_cnn_model, build_resnet_model
except ImportError:  # pragma: no cover - fallback for direct execution
    import sys

    sys.path.append(str(ROOT))
    from scripts.ensemble import build_cnn_model, build_resnet_model


def load_class_names() -> List[str]:
    classes_path = MODELS_DIR / "resnet50_classes.json"
    if classes_path.exists():
        return json.loads(classes_path.read_text(encoding="utf-8"))
    return ["hole", "normal", "stain", "weaving_error"]


def build_transform() -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


def load_models(device: torch.device) -> Tuple[torch.nn.Module, torch.nn.Module, List[str]]:
    classes = load_class_names()
    cnn_model = build_cnn_model(num_classes=len(classes), device=device)
    resnet_model = build_resnet_model(num_classes=len(classes), device=device)
    return cnn_model, resnet_model, classes


def predict_single_image(image_path: Path, device: torch.device | None = None) -> Dict[str, object]:
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    image = Image.open(image_path).convert("RGB")
    transform = build_transform()
    tensor = transform(image).unsqueeze(0).to(device)

    cnn_model, resnet_model, classes = load_models(device)
    cnn_model.eval()
    resnet_model.eval()

    with torch.inference_mode():
        cnn_logits = cnn_model(tensor)
        resnet_logits = resnet_model(tensor)

    cnn_probs = torch.softmax(cnn_logits, dim=1)[0].cpu().tolist()
    resnet_probs = torch.softmax(resnet_logits, dim=1)[0].cpu().tolist()
    ensemble_probs = [(cnn + resnet) / 2.0 for cnn, resnet in zip(cnn_probs, resnet_probs)]

    class_scores = {cls: float(score) for cls, score in zip(classes, ensemble_probs)}
    predicted_class = max(class_scores, key=class_scores.get)
    predicted_confidence = class_scores[predicted_class]

    return {
        "image_path": str(image_path),
        "predicted_class": predicted_class,
        "confidence": predicted_confidence,
        "classes": classes,
        "cnn_probabilities": {cls: float(score) for cls, score in zip(classes, cnn_probs)},
        "resnet_probabilities": {cls: float(score) for cls, score in zip(classes, resnet_probs)},
        "ensemble_probabilities": class_scores,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ensemble inference on a single image")
    parser.add_argument("image_path", type=Path, help="Path to an image file")
    args = parser.parse_args()

    if not args.image_path.exists():
        raise FileNotFoundError(f"Image not found: {args.image_path}")

    result = predict_single_image(args.image_path)
    print(f"Image: {result['image_path']}")
    print(f"Predicted class: {result['predicted_class']}")
    print(f"Confidence: {result['confidence']:.4f}")
    print("Ensemble probabilities:")
    for cls, score in result["ensemble_probabilities"].items():
        print(f"  {cls}: {score:.4f}")


if __name__ == "__main__":
    main()
