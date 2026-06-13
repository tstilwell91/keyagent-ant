# HPC Training Plan & Portability Guide

This document details the hardware, storage, and software requirements for executing reproducible **KeyAgent-Ant** training baselines on High-Performance Computing (HPC) clusters utilizing the Slurm workload manager.

> [!IMPORTANT]
> **Milestone Boundary:** The current milestone focuses strictly on enabling manifest-driven baseline training (loss and simple Top-1 validation accuracy tracking). Full holdout test-set evaluation, confusion matrices, multi-tier frequency-band evaluation, and rich metrics (Top-3/5, Macro/Weighted F1, Balanced Accuracy) are part of the **Next Evaluation Milestone**. The baseline training scripts do *not* automatically generate these rich metrics yet.

---

## 1. Resource & Storage Estimations

The proposed baseline experiments are highly optimized for portability and resource efficiency. The resource footprints per single training job are outlined below:

### Expected Compute & GPU Requirements
*   **GPU Type:** Any modern NVIDIA GPU with Tensor Cores (e.g., Tesla T4, V100, RTX 3090, RTX 4090, A100, or H100).
*   **VRAM Demand:**
    *   **ResNet-18:** $\approx 4\text{ GB}$ minimum (batch size 32).
    *   **EfficientNet-B4:** $\approx 8\text{ GB}$ minimum (batch size 32).
*   **CPU Allocation:** 4 physical cores per GPU (essential for fast data loader multiprocessing workers).
*   **System RAM:** $16\text{ GB}$ to $32\text{ GB}$ allocation.

### Expected Dataset & Checkpoint Sizes
*   **Dataset Disk Footprint:**
    *   **v1-original / v1-specimen-aware:** $\approx 10,211\text{ images}$ ($\approx 1.5\text{ GB}$ tarball, $\approx 2.0\text{ GB}$ uncompressed).
    *   **v2-curated:** $\approx 6,993\text{ images}$ ($\approx 1.0\text{ GB}$ tarball, $\approx 1.3\text{ GB}$ uncompressed).
*   **Model Checkpoint Footprint:**
    *   **ResNet-18:** $\approx 45\text{ MB}$ per `.pth` file.
    *   **EfficientNet-B4:** $\approx 75\text{ MB}$ per `.pth` file.
*   **Total Project Workspace Directory Storage:** $\approx 10\text{ GB}$ is sufficient to hold the codebase, compressed datasets, logs, and a full suite of 5 best-model checkpoints.

---

## 2. Cluster Portability Guidelines

To run robustly on any academic or research GPU cluster without modifying code, adhere to the following directory layout and environment design:

### A. Data Staging on Node-Local Scratch
Never load images directly over shared network filesystems (NFS, Lustre, or GPFS) during training, as this degrades file-I/O performance and causes network congestion. Instead, use node-local scratch storage (usually referenced as `$SLURM_TMPDIR` or `/scratch`):

1.  Keep the compressed image dataset as a single `.tar` archive in your home or project directory.
2.  At the start of the Slurm job, copy and unpack the archive directly into local scratch.
3.  Point the `--image_root` parameter of the training script to this scratch folder.

### B. Decoupled Environments
We recommend utilizing a standalone container engine (**Apptainer/Singularity**) or a pre-built virtual environment to package PyTorch, Torchvision, and Pillow:
*   Pre-download standard pre-trained weights from PyTorch Hub (e.g. `efficientnet_b4` and `resnet18`) and cache them in your cluster's home folder (`~/.cache/torch/hub/checkpoints/`) before running jobs on nodes without external internet access.

---

## 3. Portable Slurm Submission Template

The template submission script is already provided in this repository under [submit_experiment.slurm](file:///Users/tstilwel/Documents/phd/cs895_genai/2026/KeyAgent-Ant/keyagent-ant/training/submit_experiment.slurm). It is designed to run any of the experiments from our matrix:

```bash
#!/bin/bash
#SBATCH --job-name=antid-baseline
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=12:00:00
#SBATCH --output=logs/exp-%j.out
#SBATCH --error=logs/exp-%j.err

# Exit on any error
set -e

# --- 1. SETUP PATHS ---
PROJECT_DIR="${SLURM_SUBMIT_DIR:-$PWD}"
DATASET_TAR="${PROJECT_DIR}/data/raw/images.tar" # Path to compressed image archive
LOCAL_SCRATCH="${SLURM_TMPDIR:-/tmp/antid_scratch}" # Node-local fast scratch directory

echo "Starting job ${SLURM_JOB_ID} on $(hostname) at $(date)"
echo "Project directory: ${PROJECT_DIR}"
echo "Local scratch: ${LOCAL_SCRATCH}"

# --- 2. ENVIRONMENT ACTIVATION ---
# Load default PyTorch container or virtual environment (portable cluster setup)
if command -v module &> /dev/null; then
    module load python/3.10
    module load pytorch-gpu/2.1.0 || echo "Using custom virtualenv instead of cluster module"
fi

cd "${PROJECT_DIR}"
source .venv/bin/activate

# --- 3. STAGE DATASET TO FAST SCRATCH ---
echo "Staging image data to local scratch..."
mkdir -p "${LOCAL_SCRATCH}"
if [ -f "${DATASET_TAR}" ]; then
    tar -xf "${DATASET_TAR}" -C "${LOCAL_SCRATCH}"
    IMAGE_ROOT="${LOCAL_SCRATCH}"
else
    echo "Warning: images.tar not found! Falling back to local workspace images (Slow I/O)."
    IMAGE_ROOT="${PROJECT_DIR}"
fi

# --- 4. EXECUTE TRAINING RUN ---
# Example: Running Experiment 4 (EfficientNet-B4, Species, v2-curated)
# Simply swap out arguments here or override via command line parameters!
echo "Launching training script..."
export PYTHONPATH="${PROJECT_DIR}/src"

python training/EfficientNet-B4.py \
    --split_dir data/splits/v2_curated \
    --target_type species \
    --image_root "${IMAGE_ROOT}" \
    --epochs 25 \
    --batch_size 32 \
    --lr 0.001 \
    --save_model "checkpoints/species_b4_v2curated_grouped.pth"

# --- 5. CLEANUP ---
echo "Training finished. Cleaning up local scratch..."
rm -rf "${LOCAL_SCRATCH}"
echo "Job completed successfully at $(date)"
```
