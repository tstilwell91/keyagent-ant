#!/usr/bin/env python3
"""
Ant Species Classification using PyTorch with EfficientNet-B4

This script loads images using a directory structure (each subdirectory corresponds to a species),
applies enhanced data augmentation (including random erasing), fine-tunes a pre-trained EfficientNet-B4 model
by replacing its classifier with custom top layers, and trains/validates the network with a cosine annealing learning rate scheduler.
"""

import argparse
import os
import time
import copy
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms, models
from torch.utils.data import DataLoader, random_split

def train_model(model, dataloaders, criterion, optimizer, scheduler, num_epochs, device, save_path):
    """
    Trains the model and validates it at each epoch.
    Saves the best model weights to disk.
    """
    since = time.time()
    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    for epoch in range(num_epochs):
        print(f'Epoch {epoch+1}/{num_epochs}')
        print('-' * 10)

        # Each epoch has a training and a validation phase
        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()  # set model to training mode
            else:
                model.eval()   # set model to evaluation mode

            running_loss = 0.0
            running_corrects = 0

            # Iterate over data
            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)

                optimizer.zero_grad()

                # Forward pass
                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)

                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            epoch_loss = running_loss / len(dataloaders[phase].dataset)
            epoch_acc = running_corrects.double() / len(dataloaders[phase].dataset)

            print(f'{phase.capitalize()} Loss: {epoch_loss:.4f} Acc: {epoch_acc:.4f}')

        # Step the learning rate scheduler at the end of each epoch
        scheduler.step()

        # Save best model weights based on validation accuracy
        if epoch_acc > best_acc and phase == 'val':
            best_acc = epoch_acc
            best_model_wts = copy.deepcopy(model.state_dict())
            torch.save(best_model_wts, save_path)
            print(f'Best model updated and saved to {save_path}')

        print()

    time_elapsed = time.time() - since
    print(f'Training complete in {time_elapsed//60:.0f}m {time_elapsed % 60:.0f}s')
    print(f'Best Validation Acc: {best_acc:.4f}')

    # load best model weights
    model.load_state_dict(best_model_wts)
    return model

def main():
    parser = argparse.ArgumentParser(description='EfficientNet-B4 Ant Species Classification Training')
    parser.add_argument('--data_dir', type=str, required=False,
                        help='Path to dataset root directory (each subfolder is a species label)')
    parser.add_argument('--split_dir', type=str, default=None,
                        help='Path to dataset split folder containing train.csv and val.csv (bypasses ImageFolder)')
    parser.add_argument('--target_type', type=str, default='species', choices=['species', 'genus'],
                        help='Target label level: species or genus (default: species)')
    parser.add_argument('--image_root', type=str, default='.',
                        help='Root directory for images in split manifests (default: current directory)')
    parser.add_argument('--batch_size', type=int, default=32,
                        help='Batch size for training (default: 32)')
    parser.add_argument('--epochs', type=int, default=25,
                        help='Number of epochs to train (default: 25)')
    parser.add_argument('--lr', type=float, default=0.001,
                        help='Initial learning rate (default: 0.001)')
    parser.add_argument('--save_model', type=str, default='best_model.pth',
                        help='Path to save the best model (default: best_model.pth)')
    parser.add_argument('--save_classes', type=str, default=None,
                        help='Path to save class list JSON in model-index order (default: next to save_model)')
    args = parser.parse_args()

    if not args.data_dir and not args.split_dir:
        parser.error("Either --data_dir or --split_dir must be provided.")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print("Using device:", device)

    # Enhanced data augmentation for training (simulating multi-view and robustness)
    train_transforms = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomResizedCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225]),
        transforms.RandomErasing(p=0.5, scale=(0.02, 0.15), ratio=(0.3, 3.3))
    ])

    val_transforms = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])
    ])

    data_transforms = {'train': train_transforms, 'val': val_transforms}

    # Load dataset using either ManifestDataset adapter or ImageFolder
    if args.split_dir:
        try:
            from antid.training.dataset_adapter import ManifestDataset
        except ImportError:
            import sys
            # Fallback if package is not installed but src is in PYTHONPATH
            sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
            from antid.training.dataset_adapter import ManifestDataset

        print(f"Loading custom splits from: {args.split_dir}")
        train_dataset = ManifestDataset(
            split_file=os.path.join(args.split_dir, 'train.csv'),
            image_root=args.image_root,
            target_type=args.target_type,
            transform=data_transforms['train']
        )
        val_dataset = ManifestDataset(
            split_file=os.path.join(args.split_dir, 'val.csv'),
            image_root=args.image_root,
            target_type=args.target_type,
            transform=data_transforms['val']
        )
        class_names = train_dataset.classes
    else:
        full_dataset = datasets.ImageFolder(args.data_dir, transform=data_transforms['train'])
        train_size = int(0.8 * len(full_dataset))
        val_size = len(full_dataset) - train_size
        train_dataset, val_dataset = random_split(full_dataset, [train_size, val_size])
        val_dataset.dataset.transform = data_transforms['val']
        class_names = full_dataset.classes

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=4)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=4)
    dataloaders = {'train': train_loader, 'val': val_loader}

    num_classes = len(class_names)
    print("Detected classes:", class_names)

    # Load pre-trained EfficientNet-B4 and replace classifier
    model = models.efficientnet_b4(pretrained=True)
    num_features = model.classifier[1].in_features  # EfficientNet-B4 classifier expects 1792 features
    # New classifier: Dropout -> Linear -> ReLU -> Dropout -> Linear (output logits)
    model.classifier = nn.Sequential(
        nn.Dropout(0.3),
        nn.Linear(num_features, 1024),
        nn.ReLU(inplace=True),
        nn.Dropout(0.3),
        nn.Linear(1024, num_classes)
    )
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    # Use cosine annealing LR scheduler with warm restarts
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    # Train and validate the model
    model = train_model(model, dataloaders, criterion, optimizer, scheduler, args.epochs, device, args.save_model)

    # Save class mapping JSON in model-index order
    import json
    if args.save_classes:
        classes_save_path = args.save_classes
    else:
        model_dir, model_name = os.path.split(args.save_model)
        name_no_ext, _ = os.path.splitext(model_name)
        classes_save_path = os.path.join(model_dir, f"{name_no_ext}_classes.json")

    with open(classes_save_path, 'w', encoding='utf-8') as json_f:
        json.dump(class_names, json_f, indent=2)
    print(f"Saved class mapping JSON to: {classes_save_path}")

if __name__ == '__main__':
    main()

