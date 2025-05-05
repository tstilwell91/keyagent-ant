#!/bin/bash

#SBATCH -p gpu --gres gpu:1
#SBATCH --output=enb4-64-100-0005-%j.txt

module load container_env pytorch-gpu/2.5.1

crun -p ~/envs/myrmecid python explain_shap_super.py \
    --model_path ./genus_best_model.pth \
    --data_dir ../training_data \
    --output_file ./shap_output/exp1 \
    --num_explain 25 \
    --analysis_mode compare_pred_true \
    --add_superpixel_stats \
    --num_superpixels 75 \
    --top_n_superpixels 3
