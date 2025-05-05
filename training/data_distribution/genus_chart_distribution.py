#!/usr/bin/env python3
"""
Generate genus-level dataset statistics and save image distribution chart.
"""

import os
from collections import defaultdict
import matplotlib.pyplot as plt

def get_view_type(filename):
    if '_d_' in filename:
        return 'dorsal'
    elif '_h_' in filename:
        return 'head'
    elif '_p_' in filename:
        return 'profile'
    return None

def collect_genus_stats(data_dir):
    genus_stats = defaultdict(lambda: {'specimens': set(), 'images': 0, 'views': defaultdict(int)})
    total_files = 0

    for species_folder in os.listdir(data_dir):
        full_path = os.path.join(data_dir, species_folder)
        if not os.path.isdir(full_path) or "_" not in species_folder:
            continue

        genus = species_folder.split('_')[0].lower()
        for fname in os.listdir(full_path):
            if not fname.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp')):
                continue

            total_files += 1
            specimen_id = "_".join(fname.split("_")[:2])
            genus_stats[genus]['specimens'].add(specimen_id)
            genus_stats[genus]['images'] += 1

            view = get_view_type(fname)
            if view:
                genus_stats[genus]['views'][view] += 1

    return genus_stats, total_files

def summarize_stats(genus_stats, total_files):
    total_genus = len(genus_stats)
    total_specimens = sum(len(v['specimens']) for v in genus_stats.values())
    total_dorsal = sum(v['views']['dorsal'] for v in genus_stats.values())
    total_head = sum(v['views']['head'] for v in genus_stats.values())
    total_profile = sum(v['views']['profile'] for v in genus_stats.values())
    min_files_per_genus = min(v['images'] for v in genus_stats.values())

    print("\\begin{table}[H]")
    print("\\centering")
    print("\\begin{tabular}{ll}")
    print("\\hline")
    print("\\textbf{Metric} & \\textbf{Value} \\\\")
    print("\\hline")
    print(f"Total number of genera & {total_genus} \\\\")
    print(f"Total number of specimens & {total_specimens} \\\\")
    print(f"\\quad Dorsal views & {total_dorsal} \\\\")
    print(f"\\quad Head views & {total_head} \\\\")
    print(f"\\quad Profile views & {total_profile} \\\\")
    print(f"Total number of image files & {total_files} \\\\")
    print(f"Minimum number of files per genus & {min_files_per_genus} \\\\")
    print("\\hline")
    print("\\end{tabular}")
    print("\\caption{Summary of genus-level dataset derived from AntWeb}")
    print("\\label{tab:antweb_genus_summary}")
    print("\\end{table}")

def save_genus_pie_chart(genus_stats, output_file="genus_image_distribution.png", top_n=15):
    # Sort and take top N genera by number of images
    sorted_stats = sorted(genus_stats.items(), key=lambda x: x[1]['images'], reverse=True)
    labels = [k for k, _ in sorted_stats[:top_n]]
    sizes = [v['images'] for _, v in sorted_stats[:top_n]]
    
    # Aggregate others if more than top_n
    if len(sorted_stats) > top_n:
        other_count = sum(v['images'] for _, v in sorted_stats[top_n:])
        labels.append("Other")
        sizes.append(other_count)

    # Plot pie chart
    plt.figure(figsize=(10, 10))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
    plt.title("Image Count per Genus (Top {})".format(top_n))
    plt.axis('equal')
    plt.tight_layout()
    plt.savefig(output_file)
    print(f"Saved pie chart as {output_file}")

if __name__ == "__main__":
    data_dir = "../training_data"  # adjust as needed
    genus_stats, total_files = collect_genus_stats(data_dir)
    summarize_stats(genus_stats, total_files)
    save_genus_pie_chart(genus_stats)

