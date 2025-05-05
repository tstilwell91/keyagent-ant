#!/usr/bin/env python3
"""
Generate species-level dataset statistics and save image distribution chart.
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

def collect_species_stats(data_dir):
    species_stats = defaultdict(lambda: {'specimens': set(), 'images': 0, 'views': defaultdict(int)})
    total_files = 0

    for species_folder in os.listdir(data_dir):
        full_path = os.path.join(data_dir, species_folder)
        if not os.path.isdir(full_path):
            continue

        species = species_folder.lower()
        for fname in os.listdir(full_path):
            if not fname.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp')):
                continue

            total_files += 1
            specimen_id = "_".join(fname.split("_")[:2])
            species_stats[species]['specimens'].add(specimen_id)
            species_stats[species]['images'] += 1

            view = get_view_type(fname)
            if view:
                species_stats[species]['views'][view] += 1

    return species_stats, total_files

def summarize_stats(species_stats, total_files):
    total_species = len(species_stats)
    total_specimens = sum(len(v['specimens']) for v in species_stats.values())
    total_dorsal = sum(v['views']['dorsal'] for v in species_stats.values())
    total_head = sum(v['views']['head'] for v in species_stats.values())
    total_profile = sum(v['views']['profile'] for v in species_stats.values())
    min_files_per_species = min(v['images'] for v in species_stats.values())

    print("\\begin{table}[H]")
    print("\\centering")
    print("\\begin{tabular}{ll}")
    print("\\hline")
    print("\\textbf{Metric} & \\textbf{Value} \\\\")
    print("\\hline")
    print(f"Total number of species & {total_species} \\\\")
    print(f"Total number of specimens & {total_specimens} \\\\")
    print(f"\\quad Dorsal views & {total_dorsal} \\\\")
    print(f"\\quad Head views & {total_head} \\\\")
    print(f"\\quad Profile views & {total_profile} \\\\")
    print(f"Total number of image files & {total_files} \\\\")
    print(f"Minimum number of files per species & {min_files_per_species} \\\\")
    print("\\hline")
    print("\\end{tabular}")
    print("\\caption{Summary of species-level dataset derived from AntWeb}")
    print("\\label{tab:antweb_species_summary}")
    print("\\end{table}")

def save_species_pie_chart(species_stats, output_file="species_image_distribution.png", top_n=15):
    sorted_stats = sorted(species_stats.items(), key=lambda x: x[1]['images'], reverse=True)
    labels = [k for k, _ in sorted_stats[:top_n]]
    sizes = [v['images'] for _, v in sorted_stats[:top_n]]

    if len(sorted_stats) > top_n:
        other_count = sum(v['images'] for _, v in sorted_stats[top_n:])
        labels.append("Other")
        sizes.append(other_count)

    plt.figure(figsize=(10, 10))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
    plt.title("Image Count per Species (Top {})".format(top_n))
    plt.axis('equal')
    plt.tight_layout()
    plt.savefig(output_file)
    print(f"Saved pie chart as {output_file}")

def save_species_bar_chart(species_stats, output_file="species_image_bar.png", top_n=30):
    import matplotlib.pyplot as plt

    sorted_stats = sorted(species_stats.items(), key=lambda x: x[1]['images'], reverse=True)[:top_n]
    species_names = [s.replace("_", " ") for s, _ in sorted_stats]
    image_counts = [v['images'] for _, v in sorted_stats]

    plt.figure(figsize=(12, 8))
    bars = plt.barh(species_names, image_counts)
    plt.xlabel("Image Count")
    plt.title(f"Top {top_n} Species by Image Count")
    plt.gca().invert_yaxis()
    plt.tight_layout()
    plt.savefig(output_file)
    print(f"Saved bar chart as {output_file}")

if __name__ == "__main__":
    data_dir = "../training_data"  # update path if needed
    species_stats, total_files = collect_species_stats(data_dir)
    summarize_stats(species_stats, total_files)
    save_species_pie_chart(species_stats)
    save_species_bar_chart(species_stats)

