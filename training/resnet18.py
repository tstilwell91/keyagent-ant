#!/usr/bin/env python3
"""
Ant Species Classification using PyTorch

This script loads images using a directory structure (each subdirectory corresponds to a species),
trains a CNN model using transfer learning (ResNet18), and performs validation.
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

def train_model(model, dataloaders, criterion, optimizer, num_epochs, device, save_path):
    """
    Trains the model and validates it at each epoch.
    Saves the best model weights to disk.
    """
    since = time.time()
    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    for epoch in range(num_epochs):
        print('Epoch {}/{}'.format(epoch + 1, num_epochs))
        print('-' * 10)

        # Each epoch has a training and a validation phase
        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()  # Set model to training mode
            else:
                model.eval()   # Set model to evaluation mode

            running_loss = 0.0
            running_corrects = 0

            # Iterate over data.
            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)

                # Zero the parameter gradients
                optimizer.zero_grad()

                # Forward pass
                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)

                    # Backward pass and optimize only if in training phase
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            epoch_loss = running_loss / len(dataloaders[phase].dataset)
            epoch_acc = running_corrects.double() / len(dataloaders[phase].dataset)

            print('{} Loss: {:.4f} Acc: {:.4f}'.format(phase.capitalize(), epoch_loss, epoch_acc))

            # Deep copy the model if validation accuracy improved
            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())

        print()

    time_elapsed = time.time() - since
    print('Training complete in {:.0f}m {:.0f}s'.format(time_elapsed // 60, time_elapsed % 60))
    print('Best Validation Acc: {:.4f}'.format(best_acc))

    # Load best model weights and save them
    model.load_state_dict(best_model_wts)
    torch.save(model.state_dict(), save_path)
    print('Best model saved to {}'.format(save_path))
    return model

def main():
    parser = argparse.ArgumentParser(description='PyTorch Ant Species Classification Training')
    parser.add_argument('--data_dir', type=str, required=True,
                        help='Path to dataset root directory (each subfolder is a species label)')
    parser.add_argument('--batch_size', type=int, default=32,
                        help='Input batch size for training (default: 32)')
    parser.add_argument('--epochs', type=int, default=25,
                        help='Number of epochs to train (default: 25)')
    parser.add_argument('--lr', type=float, default=0.001,
                        help='Learning rate (default: 0.001)')
    parser.add_argument('--save_model', type=str, default='best_model.pth',
                        help='Path to save the best model (default: best_model.pth)')
    args = parser.parse_args()

    # Set device to GPU if available
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print("Using device:", device)

    # Define transforms for the training and validation sets
    data_transforms = {
        'train': transforms.Compose([
            transforms.Resize((256, 256)),
            transforms.RandomResizedCrop(224),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225])
        ]),
        'val': transforms.Compose([
            transforms.Resize((256, 256)),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225])
        ]),
    }

    # Load the dataset using ImageFolder
    full_dataset = datasets.ImageFolder(args.data_dir, transform=data_transforms['train'])

    # Split dataset into training and validation sets (80/20 split)
    train_size = int(0.8 * len(full_dataset))
    val_size = len(full_dataset) - train_size
    train_dataset, val_dataset = random_split(full_dataset, [train_size, val_size])

    # For the validation dataset, override the transform to use validation transforms
    val_dataset.dataset.transform = data_transforms['val']

    # Create DataLoaders for training and validation
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=4)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=4)
    dataloaders = {'train': train_loader, 'val': val_loader}

    # Print detected classes
    class_names = full_dataset.classes
    print("Detected classes:", class_names)
    num_classes = len(class_names)

    # Load a pre-trained ResNet18 model and modify the final layer
    model = models.resnet18(pretrained=True)
    num_ftrs = model.fc.in_features
    model.fc = nn.Linear(num_ftrs, num_classes)
    model = model.to(device)

    # Define loss function and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    # Train and validate the model
    model = train_model(model, dataloaders, criterion, optimizer, args.epochs, device, args.save_model)

if __name__ == '__main__':
    main()

