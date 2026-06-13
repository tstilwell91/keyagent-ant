import os
import csv
from pathlib import Path
from PIL import Image

try:
    import torch
    from torch.utils.data import Dataset
except ImportError:
    # Lightweight mock for local test environment where PyTorch is not installed
    class Dataset:
        pass


def resolve_image_path(image_path, image_root, strip_prefix=None):
    """
    Resolves an image path against an image root with fallback prefix stripping
    and legacy AntWeb downloader suffix fallbacks.
    
    Args:
        image_path (str or Path): The raw image path from the CSV manifest.
        image_root (str or Path): The root directory under which raw images are stored.
        strip_prefix (str, optional): Explicit prefix to strip from image_path if present.
        
    Returns:
        Path: The resolved absolute or root-relative Path.
    """
    image_path_str = str(image_path).strip()
    p = Path(image_path_str)
    if p.is_absolute():
        if p.exists():
            return p
        # Try legacy suffix fallbacks for absolute path
        for suffix in ["_1_med", "_1_high", "_1_low", "_1"]:
            cand = p.parent / f"{p.stem}{suffix}{p.suffix}"
            if cand.exists():
                return cand
        return p

    image_root = Path(image_root)
    candidates = []

    # 1. Try raw relative path directly
    candidates.append(image_root / p)

    # 2. Try explicit strip_prefix if provided
    if strip_prefix:
        strip_prefix_str = str(strip_prefix)
        norm_path = image_path_str.replace('\\', '/')
        norm_prefix = strip_prefix_str.replace('\\', '/')
        if norm_path.startswith(norm_prefix):
            stripped = norm_path[len(norm_prefix):].lstrip('/')
            candidates.append(image_root / Path(stripped))

    # 3. Try common fallback prefixes
    fallbacks = [
        "data/raw/images/",
        "data/raw/antweb_subset/",
        "data/raw/",
    ]
    norm_path = image_path_str.replace('\\', '/')
    for fb in fallbacks:
        if norm_path.startswith(fb):
            stripped = norm_path[len(fb):].lstrip('/')
            candidates.append(image_root / Path(stripped))

    # Find first exact-match candidate that actually exists on disk
    for cand in candidates:
        if cand.exists():
            return cand

    # If no exact match exists, try legacy suffix fallbacks for each candidate in order of preference
    for cand in candidates:
        for suffix in ["_1_med", "_1_high", "_1_low", "_1"]:
            legacy_cand = cand.parent / f"{cand.stem}{suffix}{cand.suffix}"
            if legacy_cand.exists():
                return legacy_cand

    # Fallback to the first candidate (which is image_root / p) if none exist
    return candidates[0]


class ManifestDataset(Dataset):
    """
    A PyTorch Dataset adapter that consumes manifest-driven CSV splits
    and mimics the torchvision.datasets.ImageFolder interface.
    """
    def __init__(self, split_file, image_root, target_type='species', transform=None, class_reference_file=None, strip_prefix=None):
        """
        Args:
            split_file (str or Path): Path to the train.csv, val.csv, or test.csv split file.
            image_root (str or Path): Root directory under which raw images are stored.
            target_type (str): Target label type, either 'species' or 'genus'.
            transform (callable, optional): Optional transform to be applied on a sample.
            class_reference_file (str or Path, optional): Path to reference CSV containing the complete set of classes.
            strip_prefix (str, optional): Explicit prefix to strip from image paths.
        """
        self.split_file = Path(split_file)
        self.image_root = Path(image_root)
        self.target_type = target_type.strip().lower()
        self.transform = transform
        self.class_reference_file = Path(class_reference_file) if class_reference_file is not None else None
        self.strip_prefix = strip_prefix

        if self.target_type not in ['genus', 'species']:
            raise ValueError(f"target_type must be 'genus' or 'species', got '{target_type}'")

        if not self.split_file.exists():
            raise FileNotFoundError(f"Split file not found: {split_file}")

        # Read samples from split file
        self.samples = []
        with open(self.split_file, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('image_path') and row.get('genus') and row.get('species'):
                    self.samples.append(row)

        # Build consistent, sorted class list using the specified reference file,
        # or manifest_with_splits.csv if available, or fallback to the split file itself.
        is_split_local = False
        if self.class_reference_file is not None:
            ref_file = self.class_reference_file
        else:
            manifest_with_splits = self.split_file.parent / "manifest_with_splits.csv"
            if manifest_with_splits.exists():
                ref_file = manifest_with_splits
            else:
                ref_file = self.split_file
                is_split_local = True

        if is_split_local:
            print(
                f"WARNING: No class_reference_file specified and manifest_with_splits.csv not found at "
                f"{self.split_file.parent}. Using split file {self.split_file} as class reference. "
                "Class mapping is split-local and may result in inconsistent index mapping across train/val/test splits if some classes are missing."
            )

        if not ref_file.exists():
            raise FileNotFoundError(f"Class reference file not found: {ref_file}")

        unique_classes = set()
        with open(ref_file, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cls_name = self._get_class_name(row)
                if cls_name:
                    unique_classes.add(cls_name)

        self.classes = sorted(list(unique_classes))
        self.class_to_idx = {cls: idx for idx, cls in enumerate(self.classes)}

        # Populate ImageFolder-compatible fields: imgs, targets, samples
        self.imgs = []
        self.targets = []
        for row in self.samples:
            cls_name = self._get_class_name(row)
            target_idx = self.class_to_idx[cls_name]
            self.targets.append(target_idx)

            # Resolve image path dynamically with fallback support
            rel_path = row['image_path'].strip()
            full_path = resolve_image_path(rel_path, self.image_root, strip_prefix=self.strip_prefix)
            self.imgs.append((str(full_path), target_idx))

    def _get_class_name(self, row):
        genus = row.get('genus', '').strip()
        species = row.get('species', '').strip()
        if not genus or not species:
            return None
        
        if self.target_type == 'genus':
            # Genus classification expects lowercase string labels
            return genus.lower()
        elif self.target_type == 'species':
            # Species classification expects capitalized binomial names, e.g. "Amblyopone australis"
            return f"{genus.capitalize()} {species.lower()}"
        return None

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        if idx < 0 or idx >= len(self.samples):
            raise IndexError("Index out of bounds")

        img_path, target_idx = self.imgs[idx]

        # Load image via PIL to match torchvision.datasets.ImageFolder behavior
        try:
            img = Image.open(img_path).convert('RGB')
        except Exception as e:
            raise IOError(f"Failed to load image at {img_path}: {e}")

        if self.transform is not None:
            img = self.transform(img)

        return img, target_idx
