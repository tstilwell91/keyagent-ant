#!/bin/bash

#SBATCH -p gpu --gres gpu:1
#SBATCH --output=resnet18_32_25_001-%j.txt

module load container_env pytorch-gpu/2.5.1

crun -p ~/envs/myrmecid python myrmecID.py --data_dir training_data --batch_size 32 --epochs 25 --lr 0.001
