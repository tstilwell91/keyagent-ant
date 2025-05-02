#!/usr/bin/env python3
"""
Simple Inference Script for Ant Classification

This script loads a saved PyTorch model from best_model.pth, applies the necessary image
transformations, and predicts the class of a provided test image using the combined genus and species names.
"""

import argparse
import torch
from torchvision import models, transforms
from PIL import Image
import json

def load_model(model_path, num_classes, device):
    """
    Loads the ResNet18 model with a modified final layer and the saved weights.
    """
    model = models.resnet18(pretrained=False)
    num_ftrs = model.fc.in_features
    model.fc = torch.nn.Linear(num_ftrs, num_classes)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()  # set to evaluation mode
    return model

def predict_image(model, image_path, device, transform, class_names):
    """
    Loads and preprocesses the image, then makes a prediction with the model.
    """
    image = Image.open(image_path).convert("RGB")
    image = transform(image)
    image = image.unsqueeze(0).to(device)  # add batch dimension
    with torch.no_grad():
        outputs = model(image)
        _, preds = torch.max(outputs, 1)
    predicted_class = class_names[preds.item()]
    return predicted_class

def main():
    parser = argparse.ArgumentParser(description="Ant Classifier Inference")
    parser.add_argument("--image", type=str, required=True, help="Path to the test image")
    parser.add_argument("--model", type=str, default="best_model.pth", help="Path to the saved model file")
    parser.add_argument("--classes", type=str, default="classes.json", help="Path to JSON file containing combined class names")
    args = parser.parse_args()

    # Set device to GPU if available, otherwise CPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Using device:", device)

    # Load class names from JSON file
    try:
        with open(args.classes, "r") as f:
            class_names = json.load(f)
    except Exception as e:
        print("Could not load class names from JSON. Error:", e)
        return

    num_classes = len(class_names)
    print("Detected {} classes.".format(num_classes))

    # Define image transformations (should match those used during training)
    transform = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])
    ])

    # Load the model
    model = load_model(args.model, num_classes, device)

    # Run inference on the test image
    prediction = predict_image(model, args.image, device, transform, class_names)
    print("Predicted class:", prediction)

if __name__ == "__main__":
    main()

