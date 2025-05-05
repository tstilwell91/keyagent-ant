#!/usr/bin/env python3
"""
SHAP Explanation Script for Ant Genus Classification Model.

Loads a pre-trained EfficientNet-B4 model and visualizes SHAP values
to explain predictions on sample images.

Supports two analysis modes for plotting:
1. 'predict_only': Saves individual plots showing the SHAP explanation
   for the PREDICTED class only (using shap.image_plot). Superpixel
   highlighting is NOT applied in this mode's plot.
2. 'compare_pred_true': Saves individual 3-panel plots showing:
   [Original | SHAP for Predicted Class | SHAP for True Class]. If
   superpixel stats are enabled, boundaries are overlaid on the Original panel
   and the top N +/- regions are highlighted with color overlays.

Optionally calculates and prints superpixel-based SHAP statistics
using the '--add_superpixel_stats' flag. This requires scikit-image.
"""

import argparse
import os
import random
import re # Import regex for filename cleaning
import time
from collections import defaultdict
from glob import glob

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, Subset
from torchvision import transforms, models
from PIL import Image
import numpy as np
import shap
# Need explicit import for colormap and plotting
import matplotlib.pyplot as plt

# --- Add scikit-image imports for superpixels ---
try:
    from skimage.segmentation import slic, mark_boundaries # Added mark_boundaries
    from skimage.util import img_as_float
    SKIMAGE_AVAILABLE = True
except ImportError:
    SKIMAGE_AVAILABLE = False
    # Print warning later if needed by args
# --- End skimage imports ---


# --- Constants for ImageNet normalization (used for un-normalizing for display) ---
MEAN = torch.tensor([0.485, 0.456, 0.406])
STD = torch.tensor([0.229, 0.224, 0.225])

# --- Dataset Class ---
# (Dataset class definition remains the same)
class GenusFromSpeciesFolder(Dataset):
    def __init__(self, root_dir, transform=None, extensions=('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp')):
        self.root_dir = root_dir; self.transform = transform; self.extensions = extensions
        self.samples = []; self.genus_to_idx = {}; self.classes = []
        self._make_dataset()
        if not self.classes: raise ValueError(f"No classes found in {root_dir}.")
        if not self.samples: raise ValueError(f"No images found in {root_dir} with {extensions}.")
        print(f"Dataset: Found {len(self.samples)} images across {len(self.classes)} genera.")
    def _make_dataset(self):
        genus_image_map = defaultdict(list)
        if not os.path.isdir(self.root_dir): raise FileNotFoundError(f"Data dir '{self.root_dir}' not found.")
        for species_dir in os.listdir(self.root_dir):
            full_path = os.path.join(self.root_dir, species_dir)
            if not os.path.isdir(full_path): continue
            if "_" not in species_dir: continue
            genus = species_dir.split("_")[0].lower()
            for ext in self.extensions:
                images = glob(os.path.join(full_path, f"*{ext}"))
                if images: genus_image_map[genus].extend(images)
        if not genus_image_map: raise ValueError(f"No genera/images found in subdirs of {self.root_dir}")
        self.classes = sorted(genus_image_map.keys())
        self.genus_to_idx = {g: i for i, g in enumerate(self.classes)}
        for genus, img_paths in genus_image_map.items():
            idx = self.genus_to_idx[genus]
            for path in img_paths: self.samples.append((path, idx))
    def __getitem__(self, idx):
        path, target = self.samples[idx]
        try: image = Image.open(path).convert('RGB')
        except Exception as e:
            print(f"Error loading {path}: {e}. Placeholder.")
            psz = (224, 224); dummy = Image.new('RGB', psz);
            if self.transform:
                try: return self.transform(dummy), target
                except Exception: return torch.zeros(3, psz[0], psz[1]), target
            else: return dummy, target
        if self.transform: image = self.transform(image)
        return image, target
    def __len__(self): return len(self.samples)


# --- Helper Function to Un-normalize and Format Images ---
# (Remains the same)
def format_shap_image(tensor_image):
    img = tensor_image.clone().cpu()
    mean_r = MEAN.view(-1, 1, 1); std_r = STD.view(-1, 1, 1)
    img = torch.clamp(img * std_r + mean_r, 0, 1)
    return img.permute(1, 2, 0).numpy()

# --- Helper Function for Manual SHAP Overlay Plotting ---
# (Remains the same)
def plot_shap_overlay(ax, shap_vals_hwc, image_hwc, title):
    shap_heatmap_signed = np.sum(shap_vals_hwc, axis=2)
    max_abs_val = np.percentile(np.abs(shap_heatmap_signed), 99.9)
    if max_abs_val < 1e-6: max_abs_val = 1e-6
    ax.imshow(image_hwc)
    im_overlay = ax.imshow(shap_heatmap_signed, cmap='coolwarm',
                           vmin=-max_abs_val, vmax=max_abs_val, alpha=0.6)
    ax.set_title(title, fontsize=10); ax.axis('off')
    plt.colorbar(im_overlay, ax=ax, fraction=0.046, pad=0.04) # Adjust colorbar size


# --- Main Explanation Function ---
def run_shap_explanation(args):
    # --- Check for skimage if superpixel stats are requested ---
    if args.add_superpixel_stats and not SKIMAGE_AVAILABLE:
        print("\n" + "="*60)
        print("ERROR: --add_superpixel_stats requires scikit-image, but it was not found.")
        print("       Please install it ('pip install scikit-image') and try again.")
        print("="*60 + "\n")
        exit(1)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    print(f"Selected Analysis Mode: {args.analysis_mode}")
    if args.add_superpixel_stats: print("Superpixel stats enabled.")

    # --- 1. Define Transforms ---
    input_size = args.input_size
    data_transforms = transforms.Compose([
        transforms.Resize((input_size + 32, input_size + 32)),
        transforms.CenterCrop(input_size), transforms.ToTensor(),
        transforms.Normalize(MEAN.tolist(), STD.tolist())])

    # --- 2. Load Dataset ---
    print(f"Loading dataset structure from: {args.data_dir}")
    try:
        full_dataset_info = GenusFromSpeciesFolder(args.data_dir, transform=None)
        class_names = full_dataset_info.classes; num_classes = len(class_names)
        print(f"Found {num_classes} classes ({len(full_dataset_info.samples)} images total).")
    except Exception as e: print(f"Error initializing dataset: {e}"); return

    # --- 3. Define Model Architecture ---
    print(f"Defining model architecture (EfficientNet-B4) for {num_classes} classes...")
    model = models.efficientnet_b4(weights=None)
    num_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3,inplace=True), nn.Linear(num_features, 1024), nn.ReLU(inplace=True),
        nn.Dropout(p=0.3,inplace=True), nn.Linear(1024, num_classes))

    # --- 4. Load Trained Weights ---
    print(f"Loading trained model weights from: {args.model_path}")
    if not os.path.exists(args.model_path): raise FileNotFoundError(f"{args.model_path} not found")
    try: model.load_state_dict(torch.load(args.model_path, map_location=device, weights_only=True))
    except Exception as e:
        print(f"Warn: load weights_only=True failed ({e}). Trying weights_only=False.")
        try: model.load_state_dict(torch.load(args.model_path, map_location=device, weights_only=False))
        except Exception as le: print(f"Error loading state_dict: {le}"); return
    model = model.to(device); model.eval()

    # --- 5. Prepare DataLoaders for SHAP ---
    all_indices = list(range(len(full_dataset_info)))
    random.shuffle(all_indices)
    num_total_samples = len(all_indices)
    num_background = min(args.num_background, num_total_samples)
    background_indices = all_indices[:num_background]
    remaining_indices = all_indices[num_background:]
    num_explain = min(args.num_explain, len(remaining_indices))
    explain_indices = remaining_indices[:num_explain]

    if len(explain_indices) < args.num_explain: print(f"Warn: Using {len(explain_indices)} explain images.")
    if not explain_indices: print("Error: No images available to explain."); return
    if not background_indices: print("Error: No background images selected."); return

    background_subset = Subset(full_dataset_info, background_indices)
    explain_subset = Subset(full_dataset_info, explain_indices)

    class TransformedSubset(Dataset): # Simplified definition
        def __init__(self, subset, transform): self.subset=subset; self.transform=transform; self.input_size=(224, 224)
        def __getitem__(self, index):
            path, target = self.subset.dataset.samples[self.subset.indices[index]]
            try: image = Image.open(path).convert('RGB')
            except Exception as e: print(f"Error loading {path}: {e}. Placeholder."); dummy = Image.new('RGB', self.input_size); return self.transform(dummy), target
            if self.transform: image = self.transform(image)
            return image, target
        def __len__(self): return len(self.subset)

    background_dataset_transformed = TransformedSubset(background_subset, data_transforms)
    explain_dataset_transformed = TransformedSubset(explain_subset, data_transforms)

    shap_batch_size = min(args.batch_size, 8); print(f"Using batch size {shap_batch_size} for SHAP data.")
    background_loader = DataLoader(background_dataset_transformed, batch_size=shap_batch_size, shuffle=False, num_workers=args.num_workers)
    explain_loader = DataLoader(explain_dataset_transformed, batch_size=shap_batch_size, shuffle=False, num_workers=args.num_workers)

    # --- Load all data into tensors ---
    print("Loading background data batches...")
    try: background_data_batches = [batch[0].to(device) for batch in background_loader]
    except Exception as e: print(f"Error loading background batches: {e}"); return
    if not background_data_batches: print("Error: No background data loaded."); return
    background_data = torch.cat(background_data_batches, dim=0)

    print("Loading explanation data batches...")
    explain_data_list, explain_labels_list = [], []
    try:
        for batch in explain_loader: explain_data_list.append(batch[0].to(device)); explain_labels_list.append(batch[1])
    except Exception as e: print(f"Error loading explanation batches: {e}"); return
    if not explain_data_list: print("Error: No explanation data loaded."); return
    explain_data = torch.cat(explain_data_list, dim=0)
    explain_labels = torch.cat(explain_labels_list, dim=0).cpu().numpy()

    num_explain_actual = explain_data.shape[0]
    print(f"Using {background_data.shape[0]} background images.")
    print(f"Explaining {num_explain_actual} foreground images.")

    # --- 6. Run SHAP ---
    explainer = shap.GradientExplainer(model, background_data)
    print("Calculating SHAP values (this may take some time)...")
    start_time = time.time()
    shap_values_np = explainer.shap_values(explain_data)
    end_time = time.time(); print(f"SHAP finished in {end_time - start_time:.2f} sec.")

    # --- 7. Prepare Data for Plotting (Common Steps) ---
    with torch.no_grad():
        outputs = model(explain_data)
        probabilities = torch.softmax(outputs, dim=1)
        predicted_indices = torch.argmax(probabilities, dim=1).cpu().numpy()
    explain_data_numpy_unnormalized = np.array([format_shap_image(img_tensor) for img_tensor in explain_data])

    # --- Process SHAP NumPy Array (Common Step) ---
    print(f"DEBUG: Type of shap_values_np: {type(shap_values_np)}")
    if isinstance(shap_values_np, list):
        try: shap_values_np = np.array(shap_values_np).transpose(1, 2, 3, 4, 0) # N,C,H,W,Cls
        except Exception as e: print(f"Error converting SHAP list to array: {e}"); return
    elif isinstance(shap_values_np, np.ndarray): print(f"DEBUG: SHAP values shape: {shap_values_np.shape}")
    else: print("Error: Unexpected SHAP type."); return
    expected_shape = (num_explain_actual, 3, input_size, input_size, num_classes)
    if shap_values_np.shape != expected_shape: print(f"Error: SHAP shape {shap_values_np.shape} != {expected_shape}"); return
    print(f"DEBUG: SHAP stats: min={np.min(shap_values_np):.2f}, max={np.max(shap_values_np):.2f}, mean={np.mean(shap_values_np):.2g}")
    if np.isnan(shap_values_np).any(): print("Warning: NaN in SHAP values.")

    # --- Transpose SHAP values for easier plotting access (N, H, W, C, Classes) ---
    try: shap_values_transposed = shap_values_np.transpose(0, 2, 3, 1, 4) # N, H, W, C, Classes
    except Exception as e: print(f"Error transposing SHAP: {e}"); return
    print(f"DEBUG: Plotting SHAP shape: {shap_values_transposed.shape}")

    # --- 8. Plotting & Statistics Section (Mode Dependent) ---
    base_output_filename, output_extension = None, ".png"
    if args.output_file:
        base, ext = os.path.splitext(args.output_file)
        if ext: output_extension = ext; base_output_filename = base
        else: base_output_filename = args.output_file
        base_output_filename = re.sub(r'_N\d+$|_image_\d+$|_compare_\d+$|_pred_only_\d+$', '', base_output_filename) # More cleaning


    # --- Main Loop ---
    print(f"\n--- Starting Explanation Loop for {num_explain_actual} Images ---")
    for i in range(num_explain_actual):
        print(f"--- Processing Image {i+1}/{num_explain_actual} ---")
        pred_idx = predicted_indices[i]
        true_idx = explain_labels[i]
        original_image = explain_data_numpy_unnormalized[i] # Shape (H, W, C)

        # Get SHAP values for predicted class (always needed)
        if pred_idx >= shap_values_transposed.shape[-1] or true_idx >= shap_values_transposed.shape[-1]:
            print(f"  Error: Index out of bounds (Pred: {pred_idx}, True: {true_idx}). Skipping.")
            continue
        shap_vals_pred_hwc = shap_values_transposed[i, :, :, :, pred_idx] # Shape (H, W, C)

        # Initialize variables for optional steps
        segments_map = None
        top_pos_ids = []
        top_neg_ids = []

        # --- Superpixel Statistics (Optional) ---
        if args.add_superpixel_stats:
            print(f"  Calculating Superpixel Stats (Predicted Class: {class_names[pred_idx]})...")
            try:
                image_float = img_as_float(original_image)
                start_seg = time.time()
                segments = slic(image_float, n_segments=args.num_superpixels,
                                compactness=10, sigma=1, start_label=1, channel_axis=-1)
                segments_map = segments # <-- Store the generated map
                print(f"    Generated {segments.max()} superpixels in {time.time()-start_seg:.2f} sec.")

                superpixel_shap_means = {}
                for seg_id in np.unique(segments_map):
                    mask = (segments_map == seg_id)
                    if np.sum(mask) == 0: continue
                    shap_in_region = shap_vals_pred_hwc[mask]
                    shap_sum_per_pixel = np.sum(shap_in_region, axis=1)
                    mean_shap = np.mean(shap_sum_per_pixel)
                    superpixel_shap_means[seg_id] = mean_shap

                if superpixel_shap_means:
                    sorted_superpixels = sorted(superpixel_shap_means.items(), key=lambda item: item[1])
                    n_top = min(args.top_n_superpixels, len(sorted_superpixels))

                    print(f"    Top {n_top} Negative Superpixels (RegionID: MeanSHAP):")
                    # Store negative IDs
                    top_neg_ids = []
                    for k in range(n_top):
                         if k < len(sorted_superpixels):
                              region_id = sorted_superpixels[k][0]
                              mean_val = sorted_superpixels[k][1]
                              print(f"      {region_id}: {mean_val:.4f}")
                              top_neg_ids.append(region_id) # Store ID

                    print(f"    Top {n_top} Positive Superpixels (RegionID: MeanSHAP):")
                    # Store positive IDs
                    top_pos_ids = []
                    for k in range(n_top):
                        idx_to_access = -(k + 1)
                        if abs(idx_to_access) <= len(sorted_superpixels):
                             region_id = sorted_superpixels[idx_to_access][0]
                             mean_val = sorted_superpixels[idx_to_access][1]
                             print(f"      {region_id}: {mean_val:.4f}")
                             top_pos_ids.append(region_id) # Store ID
                else: print("    No superpixel means calculated.")

            except Exception as seg_err:
                print(f"    Error during superpixel analysis: {seg_err}")
                segments_map = None # Ensure segments map is None if error occurs
        # --- End Superpixel Statistics ---


        # --- Plotting based on analysis_mode ---
        fig = None
        filename = None
        try:
            if args.analysis_mode == 'predict_only':
                print(f"  Generating 'predict_only' plot for image {i}...")
                plot_labels_predict_only = np.array([f"True: {class_names[true_idx]}\nPred: {class_names[pred_idx]} (P={probabilities[i, pred_idx]:.2f})"])
                current_shap_vals = shap_vals_pred_hwc[np.newaxis, ...]
                current_pixel_vals = original_image[np.newaxis, ...]

                fig = plt.figure()
                shap.image_plot(shap_values=current_shap_vals,
                                pixel_values=current_pixel_vals,
                                labels=plot_labels_predict_only.tolist(),
                                show=False)
                # Note: Superpixel highlighting not applied here as shap.image_plot is used.
                if base_output_filename:
                    filename = f"{base_output_filename}_pred_only_image_{i}{output_extension}"


            elif args.analysis_mode == 'compare_pred_true':
                print(f"  Generating 'compare_pred_true' plot for image {i}...")
                shap_vals_true_hwc = shap_values_transposed[i, :, :, :, true_idx]
                fig, axes = plt.subplots(1, 3, figsize=(18, 6))

                # Panel 1: Original Image (with boundaries & optional highlighting)
                axes[0].imshow(original_image)
                plot_title = "Original Image"
                if args.add_superpixel_stats and segments_map is not None:
                    try:
                        img_display = img_as_float(original_image)
                        marked_image = mark_boundaries(img_display, segments_map, color=(1, 1, 0), mode='thick') # Yellow boundaries
                        axes[0].imshow(marked_image) # Re-draw image with boundaries
                        plot_title += " (Superpixels Marked)"

                        # --- Add Highlighting Overlay ---
                        if top_pos_ids or top_neg_ids: # Check if there are IDs to highlight
                            positive_highlight_mask = np.isin(segments_map, top_pos_ids)
                            negative_highlight_mask = np.isin(segments_map, top_neg_ids)
                            # Define RGBA colors (ensure alpha is reasonable, e.g., 0.3-0.4)
                            pos_color = np.array([0, 1, 0, 0.35]) # Green semi-transparent
                            neg_color = np.array([1, 0, 1, 0.35]) # Magenta semi-transparent
                            # Create overlay image
                            highlight_overlay = np.zeros((*segments_map.shape, 4)) # RGBA
                            highlight_overlay[positive_highlight_mask] = pos_color
                            highlight_overlay[negative_highlight_mask] = neg_color
                            # Plot overlay
                            axes[0].imshow(highlight_overlay)
                            plot_title += " + Top N +/- regions" # Update title further
                        # --- End Highlighting Overlay ---

                    except Exception as mark_err:
                         print(f"    Warning: Failed to mark boundaries/highlight: {mark_err}")
                         axes[0].imshow(original_image) # Fallback
                axes[0].set_title(plot_title)
                axes[0].axis('off')

                # Panel 2: SHAP Overlay for Predicted Class
                pred_title = f"Predicted: {class_names[pred_idx]} (P={probabilities[i, pred_idx]:.2f})"
                plot_shap_overlay(axes[1], shap_vals_pred_hwc, original_image, pred_title)

                # Panel 3: SHAP Overlay for True Class
                true_title = f"True: {class_names[true_idx]}"
                plot_shap_overlay(axes[2], shap_vals_true_hwc, original_image, true_title)

                # Overall title
                is_correct = "CORRECT" if pred_idx == true_idx else "INCORRECT"
                fig.suptitle(f"Image {i} - Prediction: {is_correct}", fontsize=14, y=1.02)
                try: plt.tight_layout(rect=[0, 0.03, 1, 0.98])
                except Exception: pass

                if base_output_filename:
                    filename = f"{base_output_filename}_compare_image_{i}{output_extension}"

            else: # Should not happen
                 print(f"Error: Unknown analysis_mode '{args.analysis_mode}'")
                 continue

            # Save the figure if a filename was determined
            if base_output_filename and filename and fig:
                print(f"  Saving plot to {filename}...")
                plt.savefig(filename, bbox_inches='tight', dpi=150)
                print(f"  Plot saved.")
            elif not base_output_filename:
                 print("  Plot not saved (no --output_file specified).")

        except Exception as plot_err:
            print(f"  Error during plotting/saving for image {i}: {plot_err}")
        finally:
            # Ensure figure is closed regardless of errors
            if fig: plt.close(fig)
            else: plt.close('all') # Close potentially lingering figures

    print("\n--- Finished processing all images ---")
    print("--- Explanation Script Finished ---")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SHAP Explanation Script for Ant Genus Classifier with Superpixel Analysis')

    # --- Arguments ---
    parser.add_argument('--model_path', type=str, required=True, help='Path to model state_dict (.pth)')
    parser.add_argument('--data_dir', type=str, required=True, help='Path to root dataset directory')
    parser.add_argument('--output_file', type=str, default=None, help='Optional base path/filename for saving outputs.')
    parser.add_argument('--num_explain', type=int, default=8, help='Number of images to explain (default: 8)')
    parser.add_argument('--num_background', type=int, default=50, help='Number of background images (default: 50)')
    parser.add_argument('--input_size', type=int, default=224, help='Model input image size (default: 224)')
    parser.add_argument('--batch_size', type=int, default=16, help='DataLoader batch size (default: 16)')
    parser.add_argument('--num_workers', type=int, default=0, help='DataLoader workers (default: 0)')
    parser.add_argument('--analysis_mode', type=str, default='predict_only',
                        choices=['predict_only', 'compare_pred_true'],
                        help="Plotting mode: 'predict_only' or 'compare_pred_true' (default: predict_only)")
    # --- New Superpixel Arguments ---
    parser.add_argument('--add_superpixel_stats', action='store_true',
                        help='Calculate and print mean SHAP per superpixel for predicted class. Enables highlighting in compare_pred_true mode.')
    parser.add_argument('--num_superpixels', type=int, default=50,
                        help='Approximate number of superpixels for stats (default: 50)')
    parser.add_argument('--top_n_superpixels', type=int, default=5,
                        help='Number of top +/- superpixels to print stats for AND highlight (default: 5)')
    # --- End Arguments ---

    args = parser.parse_args()

    # Print skimage warning if needed and not caught earlier
    if args.add_superpixel_stats and not SKIMAGE_AVAILABLE:
         print("\nERROR: Superpixel analysis requested but scikit-image is not available.\n")
         exit(1)

    # Basic input validation
    if not os.path.exists(args.model_path): print(f"Error: Model file not found: {args.model_path}"); exit(1)
    if not os.path.isdir(args.data_dir): print(f"Error: Data directory not found: {args.data_dir}"); exit(1)
    if args.num_explain <= 0: print(f"Error: --num_explain must be > 0"); exit(1)
    if args.num_background <= 0: print(f"Warning: --num_background should be > 0");

    run_shap_explanation(args)
