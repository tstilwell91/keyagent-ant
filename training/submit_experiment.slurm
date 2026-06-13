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
