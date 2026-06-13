# Baseline Integration & Reproduction Plan

This report details the inspection of the legacy training stack for the **AntID Tutor** project, analyzes its architectural requirements, and establishes a plan to connect it to the new, leakage-free dataset infrastructure of **KeyAgent-Ant**.

---

## 1. Legacy Training Stack Inspection

### Primary Training Entry Points
We discovered two primary training scripts in the `training/` directory:
1. **`training/EfficientNet-B4.py`**: Custom fine-tuning of a pre-trained EfficientNet-B4 model with deep classifier layers (Dropout, Linear, ReLU, Dropout, Linear). Includes enhanced augmentations like RandomErasing and a CosineAnnealingLR scheduler.
2. **`training/resnet18.py`**: Standard transfer learning utilizing a pre-trained ResNet-18 model, modifying only the final fully connected layer (`model.fc`) to match the number of classes.

Both scripts share a unified interface:
```bash
python <script.py> --data_dir <path> --batch_size <int> --epochs <int> --lr <float> --save_model <path>
```

### Classification Targets (Genus vs. Species)
- **Legacy Behavior:** The training scripts themselves are target-agnostic. They instantiate a PyTorch `torchvision.datasets.ImageFolder` on `--data_dir`, which detects classes based on physical subdirectories on disk.
- **Genus Models:** The legacy model deployed in the Flask app (under `models/genus/`) classifies ants into **42 unique genus classes**.
- **Species Models:** No dedicated species training script exists; the original species classification was designed to run by passing a directory of species binomial folders to the same training entry points.
- **View-Specific Training:** **No view-specific training paths exist** in the legacy scripts. Both scripts treat all dorsal (`_d`), head (`_h`), and profile (`_p`) views as independent training samples under the respective taxon.

### Legacy Data Schema & Assumptions
*   **Expected Dataset Structure:** An `ImageFolder` structure where images are grouped into physical subfolders corresponding directly to class names:
    ```
    data_dir/
    ├── taxon_A/
    │   ├── img1.jpg
    │   └── img2.jpg
    └── taxon_B/
        ├── img3.jpg
        └── img4.jpg
    ```
*   **Split Mechanism:** The legacy scripts perform a standard **on-the-fly random split** using `torch.utils.data.random_split` with an 80/20 train/val ratio. This leads to **specimen leakage** because different views of the same physical specimen can end up split across training and validation sets, inflating validation accuracy artificially.
*   **Expected Class Mapping Structure:** Read from `.classes` of the loaded dataset. In the updated pipeline, we export a JSON list of class names (e.g., `model_classes.json` next to `--save_model`) in model-index order to guarantee stable, reproducible mappings for inference and Flask app integration.
*   **Expected Checkpoint Outputs:** A PyTorch state dictionary serialized as a `.pth` file containing the weights of the best epoch based on validation accuracy (e.g., `best_model.pth`), along with its class-index mapping JSON (e.g., `best_model_classes.json`).
*   **Expected Evaluation Outputs:** Console standard output logs indicating loss and accuracy for train and val phases at each epoch.
    > [!IMPORTANT]
    > **Milestone Boundary:** The current baseline reproduction scripts only support training-time and validation-time loss and Top-1 accuracy tracking. Full test-set evaluation on the holdout `test.csv` manifests and the generation of advanced metrics (Top-3/5, macro-F1, balanced accuracy, confusion matrices, and frequency-band evaluations) are part of the **Next Evaluation Milestone**.

---

## 2. Technical Integration Approach

To allow these training scripts to consume our newly generated manifests and splits without rewrite, we implement a **Dataset Adapter Layer** that replaces `ImageFolder` when structured split directories are provided.

### The Adapter Blueprint (`ManifestDataset`)
The `ManifestDataset` will load split files (`train.csv`, `val.csv`, `test.csv`) directly. Its class mapping is resolved alphabetically across all classes present in the split directory, ensuring consistent index alignment between splits.

```
+------------------+     +------------------------+     +-------------------+
|    train.csv     | --> |                        | --> |   Train Dataloader|
+------------------+     |                        |     +-------------------+
                         |    ManifestDataset     |
+------------------+     |  (mimics ImageFolder)  |     +-------------------+
|     val.csv      | --> |                        | --> |    Val Dataloader |
+------------------+     +------------------------+     +-------------------+
```

---

## 3. HPC Execution Considerations

Transitioning from local Mac development to the final execution target (HPC GPU cluster running Slurm) requires structural modularity and robust file references.

### 1. Data Locality & Staging
Image datasets should not be parsed over slow shared network filesystems (NFS) during training loops. On HPC clusters, it is best practice to:
- Copy the image archive (tarball) to the fast local scratch directory of the compute node (e.g., `$SLURM_TMPDIR` or `/scratch`).
- Extract the archive in parallel.
- Point the training command (`--image_root`) directly to this local scratch path.

### 2. Environment Portability
HPC cluster environments often run with restricted internet access. To ensure portability:
- Use container environments (Apptainer/Singularity) or a locked virtual environment (`requirements.txt`).
- Pre-download the pre-trained EfficientNet-B4 and ResNet-18 weights (via Torchaudio/Torchvision cache directories) and map them to `~/.cache/torch/hub/checkpoints/` before running offline jobs.

### 3. Execution Security & Policies
- **Checkpointing:** Implement saving of checkpoints to the user's home or project directory, never to transient scratch space.
- **Resource Limits:** Standardize resource allocations in the Slurm submit templates, estimating memory requirements at 4 CPUs and 16-32 GB of RAM per GPU.
