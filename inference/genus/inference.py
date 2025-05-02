#!/usr/bin/env python3
"""
EfficientNet-B4 Ant Genus Classifier Inference Script

This script loads the full model saved via torch.save(model, ...) and predicts the genus
from a test image, using class names loaded from a JSON file.
"""

import argparse
import torch
from torchvision import transforms
from PIL import Image
import json

def load_model(full_model_path, device):
    print(f"Loading model from: {full_model_path}")
    model = torch.load(full_model_path, map_location=device)
    model.to(device)
    model.eval()
    return model

def preprocess_image(image_path):
    print(f"Preprocessing image: {image_path}")
    transform = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])
    ])
    img = Image.open(image_path).convert("RGB")
    return transform(img).unsqueeze(0)  # Add batch dimension

def predict_image(model, img_tensor, device, class_names):
    img_tensor = img_tensor.to(device)
    with torch.no_grad():
        outputs = model(img_tensor)
        probs = torch.nn.functional.softmax(outputs, dim=1)
        confidence, predicted_idx = probs.max(dim=1)
        predicted_class = class_names[predicted_idx.item()]
        return predicted_class, confidence.item()

def main():
    parser = argparse.ArgumentParser(description="EfficientNet-B4 Ant Genus Inference")
    parser.add_argument("--image", required=True, help="Path to input image")
    parser.add_argument("--model", default="genus_best_model_full.pth", help="Path to full saved model")
    parser.add_argument("--classes", default="classes.json", help="Path to JSON file with class names")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Using device:", device)

    # Load class names
    try:
        with open(args.classes, "r") as f:
            class_names = json.load(f)
    except Exception as e:
        print("Could not load class names:", e)
        return

    print(f"Detected {len(class_names)} classes.")
    model = load_model(args.model, device)
    img_tensor = preprocess_image(args.image)
    genus, conf = predict_image(model, img_tensor, device, class_names)
    print(f"Predicted genus: {genus} (confidence: {conf:.4f})")

if __name__ == "__main__":
    main()
