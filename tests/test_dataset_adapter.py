import os
import csv
import pytest
from pathlib import Path
from PIL import Image
from antid.training.dataset_adapter import ManifestDataset

# Conditional imports/mocks for PyTorch-less environments
try:
    from torchvision import transforms
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    class MockTensor:
        def __init__(self, shape):
            self.shape = shape
    class MockCompose:
        def __init__(self, transforms_list):
            pass
        def __call__(self, img):
            return MockTensor((3, 50, 50))
    class MockResize:
        def __init__(self, size):
            pass
    class MockToTensor:
        pass
    class mock_transforms:
        Compose = MockCompose
        Resize = MockResize
        ToTensor = MockToTensor
    transforms = mock_transforms
    class mock_torch:
        Tensor = MockTensor
    torch = mock_torch

@pytest.fixture
def mock_dataset_split(tmp_path):
    # Create mock split directory structure
    split_dir = tmp_path / "splits" / "mock_variant"
    split_dir.mkdir(parents=True, exist_ok=True)
    
    # Create mock images directory
    image_root = tmp_path / "raw_images"
    image_root.mkdir(parents=True, exist_ok=True)
    
    # Setup some mock ant images
    species_dir = image_root / "data" / "raw" / "images" / "amblyopone_australis"
    species_dir.mkdir(parents=True, exist_ok=True)
    
    # Create actual tiny mock images
    img_data = Image.new('RGB', (100, 100), color='red')
    img1_path = species_dir / "casent01_d.jpg"
    img2_path = species_dir / "casent01_h.jpg"
    img_data.save(img1_path)
    img_data.save(img2_path)
    
    # Define test samples (CSV format)
    samples = [
        {
            "image_path": "data/raw/images/amblyopone_australis/casent01_d.jpg",
            "genus": "Amblyopone",
            "species": "australis",
            "split": "train"
        },
        {
            "image_path": "data/raw/images/amblyopone_australis/casent01_h.jpg",
            "genus": "Amblyopone",
            "species": "australis",
            "split": "train"
        }
    ]
    
    # Write train.csv
    train_file = split_dir / "train.csv"
    with open(train_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image_path", "genus", "species", "split"])
        writer.writeheader()
        for s in samples:
            writer.writerow(s)
            
    # Write manifest_with_splits.csv in same folder
    manifest_file = split_dir / "manifest_with_splits.csv"
    with open(manifest_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image_path", "genus", "species", "split"])
        writer.writeheader()
        for s in samples:
            writer.writerow(s)

    return train_file, image_root

def test_manifest_dataset_species_mode(mock_dataset_split):
    train_file, image_root = mock_dataset_split
    
    # Instantiate dataset in species mode
    dataset = ManifestDataset(
        split_file=train_file,
        image_root=image_root,
        target_type="species"
    )
    
    # Verify properties
    assert len(dataset) == 2
    assert dataset.classes == ["Amblyopone australis"]
    assert dataset.class_to_idx == {"Amblyopone australis": 0}
    assert dataset.targets == [0, 0]
    
    # Load a sample
    img, label = dataset[0]
    assert isinstance(img, Image.Image)
    assert label == 0
    assert img.size == (100, 100)

def test_manifest_dataset_genus_mode(mock_dataset_split):
    train_file, image_root = mock_dataset_split
    
    # Instantiate dataset in genus mode
    dataset = ManifestDataset(
        split_file=train_file,
        image_root=image_root,
        target_type="genus"
    )
    
    # Verify properties (genus label should be lowercase)
    assert len(dataset) == 2
    assert dataset.classes == ["amblyopone"]
    assert dataset.class_to_idx == {"amblyopone": 0}
    assert dataset.targets == [0, 0]
    
    img, label = dataset[1]
    assert label == 0

def test_manifest_dataset_with_transforms(mock_dataset_split):
    train_file, image_root = mock_dataset_split
    
    # Define a simple transform
    transform = transforms.Compose([
        transforms.Resize((50, 50)),
        transforms.ToTensor()
    ])
    
    dataset = ManifestDataset(
        split_file=train_file,
        image_root=image_root,
        target_type="species",
        transform=transform
    )
    
    img, label = dataset[0]
    if HAS_TORCH:
        # Loaded image is now an actual PyTorch Tensor of size (3, 50, 50)
        assert isinstance(img, torch.Tensor)
    else:
        # Mocked tensor
        assert isinstance(img, MockTensor)
    assert img.shape == (3, 50, 50)

def test_manifest_dataset_out_of_bounds(mock_dataset_split):
    train_file, image_root = mock_dataset_split
    dataset = ManifestDataset(train_file, image_root, target_type="species")
    
    with pytest.raises(IndexError):
        _ = dataset[2]
        
    with pytest.raises(IndexError):
        _ = dataset[-1]

def test_manifest_dataset_invalid_target_type(mock_dataset_split):
    train_file, image_root = mock_dataset_split
    with pytest.raises(ValueError):
        _ = ManifestDataset(train_file, image_root, target_type="invalid_target")


def test_class_reference_mapping_train_val(tmp_path, capsys):
    # Create split directory
    split_dir = tmp_path / "splits"
    split_dir.mkdir()
    
    # Create mock images directory
    image_root = tmp_path / "raw_images"
    image_root.mkdir()
    
    # Write train.csv (has both species)
    train_file = split_dir / "train.csv"
    with open(train_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image_path", "genus", "species", "split"])
        writer.writeheader()
        writer.writerow({"image_path": "a.jpg", "genus": "Amblyopone", "species": "australis", "split": "train"})
        writer.writerow({"image_path": "b.jpg", "genus": "Camponotus", "species": "pennsylvanicus", "split": "train"})
        
    # Write val.csv (only has Amblyopone)
    val_file = split_dir / "val.csv"
    with open(val_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image_path", "genus", "species", "split"])
        writer.writeheader()
        writer.writerow({"image_path": "a.jpg", "genus": "Amblyopone", "species": "australis", "split": "val"})

    # Case A: Rely on manifest_with_splits.csv automatically
    manifest_file = split_dir / "manifest_with_splits.csv"
    with open(manifest_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image_path", "genus", "species", "split"])
        writer.writeheader()
        writer.writerow({"image_path": "a.jpg", "genus": "Amblyopone", "species": "australis", "split": "train"})
        writer.writerow({"image_path": "b.jpg", "genus": "Camponotus", "species": "pennsylvanicus", "split": "train"})

    train_ds = ManifestDataset(train_file, image_root, target_type="species")
    val_ds = ManifestDataset(val_file, image_root, target_type="species")
    
    # Val dataset should have both classes even though val.csv only contains one, preventing index drift!
    assert train_ds.classes == val_ds.classes
    assert train_ds.classes == ["Amblyopone australis", "Camponotus pennsylvanicus"]
    assert train_ds.class_to_idx == val_ds.class_to_idx
    assert val_ds.class_to_idx == {"Amblyopone australis": 0, "Camponotus pennsylvanicus": 1}

    # Case B: Explicit class_reference_file parameter
    custom_ref_file = tmp_path / "custom_classes.csv"
    with open(custom_ref_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image_path", "genus", "species", "split"])
        writer.writeheader()
        writer.writerow({"image_path": "a.jpg", "genus": "Amblyopone", "species": "australis", "split": "train"})
        writer.writerow({"image_path": "b.jpg", "genus": "Camponotus", "species": "pennsylvanicus", "split": "train"})
        writer.writerow({"image_path": "c.jpg", "genus": "Pheidole", "species": "dentata", "split": "train"})

    val_ds_custom = ManifestDataset(val_file, image_root, target_type="species", class_reference_file=custom_ref_file)
    assert val_ds_custom.classes == ["Amblyopone australis", "Camponotus pennsylvanicus", "Pheidole dentata"]
    assert val_ds_custom.class_to_idx["Pheidole dentata"] == 2

    # Case C: manifest_with_splits.csv is missing and no class_reference_file is provided (warning triggered)
    manifest_file.unlink() # remove it
    
    capsys.readouterr() # clear buffers
    val_ds_local = ManifestDataset(val_file, image_root, target_type="species")
    captured = capsys.readouterr()
    
    assert "WARNING: No class_reference_file specified" in captured.out
    assert val_ds_local.classes == ["Amblyopone australis"] # index drift happens without reference


def test_resolve_image_path(tmp_path):
    from antid.training.dataset_adapter import resolve_image_path
    
    # Setup some directory paths
    image_root = tmp_path / "raw_images"
    image_root.mkdir()
    
    # 1. Test absolute path (should return directly)
    abs_path = tmp_path / "some_abs_image.jpg"
    assert resolve_image_path(abs_path, image_root) == abs_path
    
    # 2. Test relative path with no prefixes (does not exist, returns default candidates[0])
    rel_path = "subdir/ant.jpg"
    assert resolve_image_path(rel_path, image_root) == image_root / rel_path
    
    # 3. Test relative path with explicit strip_prefix (where stripped path exists)
    prefixed_path = "prefix_to_strip/subdir/ant.jpg"
    target_path = image_root / "subdir/ant.jpg"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.touch()
    
    # If the stripped file exists, resolve_image_path should find and return it
    resolved = resolve_image_path(prefixed_path, image_root, strip_prefix="prefix_to_strip")
    assert resolved == target_path
    
    # 4. Test common fallbacks (e.g. data/raw/images/)
    fallback_rel = "data/raw/images/my_ant/view.jpg"
    fallback_target = image_root / "my_ant/view.jpg"
    fallback_target.parent.mkdir(parents=True, exist_ok=True)
    fallback_target.touch()
    
    resolved_fallback = resolve_image_path(fallback_rel, image_root)
    assert resolved_fallback == fallback_target
    
    # 5. Test another fallback (e.g. data/raw/antweb_subset/)
    fallback_subset = "data/raw/antweb_subset/another_ant/view.jpg"
    subset_target = image_root / "another_ant/view.jpg"
    subset_target.parent.mkdir(parents=True, exist_ok=True)
    subset_target.touch()
    
    resolved_subset = resolve_image_path(fallback_subset, image_root)
    assert resolved_subset == subset_target


def test_resolve_image_path_legacy_suffix_fallbacks(tmp_path):
    from antid.training.dataset_adapter import resolve_image_path
    
    image_root = tmp_path / "raw_images"
    image_root.mkdir()
    
    # Let's create a directory for an ant species
    ant_dir = image_root / "amblyopone_australis"
    ant_dir.mkdir()
    
    exact_path_rel = "amblyopone_australis/casent0280654_d.jpg"
    exact_path_full = image_root / exact_path_rel
    
    suffix_med_full = ant_dir / "casent0280654_d_1_med.jpg"
    suffix_high_full = ant_dir / "casent0280654_d_1_high.jpg"
    suffix_low_full = ant_dir / "casent0280654_d_1_low.jpg"
    suffix_one_full = ant_dir / "casent0280654_d_1.jpg"
    
    # Case 1: Prioritize exact-match if it exists
    suffix_med_full.touch()
    exact_path_full.touch()
    
    assert resolve_image_path(exact_path_rel, image_root) == exact_path_full
    
    # Clean up exact path to test fallbacks
    exact_path_full.unlink()
    
    # Case 2: Med suffix fallback (exists)
    assert resolve_image_path(exact_path_rel, image_root) == suffix_med_full
    
    # Clean up med suffix
    suffix_med_full.unlink()
    
    # Case 3: High suffix fallback
    suffix_high_full.touch()
    assert resolve_image_path(exact_path_rel, image_root) == suffix_high_full
    suffix_high_full.unlink()
    
    # Case 4: Low suffix fallback
    suffix_low_full.touch()
    assert resolve_image_path(exact_path_rel, image_root) == suffix_low_full
    suffix_low_full.unlink()
    
    # Case 5: _1 suffix fallback
    suffix_one_full.touch()
    assert resolve_image_path(exact_path_rel, image_root) == suffix_one_full
    suffix_one_full.unlink()
    
    # Case 6: Fallback to base candidate if absolutely none of them exist
    assert resolve_image_path(exact_path_rel, image_root) == exact_path_full
    
    # Case 7: Absolute path fallbacks
    abs_path = tmp_path / "casent0000000_h.jpg"
    abs_path_med = tmp_path / "casent0000000_h_1_med.jpg"
    abs_path_med.touch()
    
    # Should resolve to the existing med suffix file even when absolute base does not exist
    assert resolve_image_path(abs_path, image_root) == abs_path_med
    abs_path_med.unlink()
