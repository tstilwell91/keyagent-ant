# KeyAgent-Ant: Specimen Coverage Audit

This report presents a specimen-level coverage audit of the legacy AntID Tutor dataset, utilizing the physical specimen identifier (`catalog_number`) from the AntWeb-derived CSV (`downloader/Sup_top97species_Qmed_def_info.csv`). 

Traditional deep-learning approaches in myrmecology suffer from severe validation leakage when splits are created randomly at the image level. This audit establishes the baseline metrics needed to transition KeyAgent-Ant to a mathematically rigorous, specimen-aware split regimen and analyzes the taxonomical, view, and caste characteristics of our data.

---

## Executive Summary

> [!NOTE]
> While our image-level dataset appears heavily populated with **10,295 images**, it is grounded in only **3,465 unique physical specimens**. Evaluating model performance on an image-level split leads to severe "specimen-leakage" (e.g., training on the dorsal view and testing on the head view of the exact same physical ant), which artificially inflates validation accuracy.

### Global Dataset Metrics
| Metric | Count | Percentage of Total | Notes |
| :--- | :---: | :---: | :--- |
| **Total Rows (Image Records)** | 10,295 | 100.0% | Core dataset size |
| **Unique Binomial Species** | 97 | — | Lock-step taxonomic coverage |
| **Unique Physical Specimens** | 3,465 | 33.66% | Based on unique `catalog_number` |
| **Complete Tri-View Specimens (3 views)** | 3,380 | **97.55%** of specimens | Crucial for tri-view fusion models |
| **Two-View Specimens (2 views)** | 70 | 2.02% of specimens | Incomplete specimen profile |
| **One-View Specimens (1 view)** | 15 | 0.43% of specimens | Incomplete specimen profile |
| **Partial Specimens (1 or 2 views)** | 85 | **2.45%** of specimens | Total incomplete physical records |

### Global Caste Distribution
| Caste Group | Image Count | Percentage of Total | Notes |
| :--- | :---: | :---: | :--- |
| **Worker** | 8,443 | **82.01%** | Core taxonomic key target |
| **Queen** | 1,216 | 11.81% | Sexual caste; introduces severe morphological shift |
| **Male** | 636 | 6.18% | Sexual caste; look drastically different (wasp-like) |

### Species-Level Cohorts
* **Worker-Only Species:** **14 species** (only worker images exist)
* **Mixed-Caste Species:** **83 species** (workers, queens, and/or males are mixed together)
* **Species Missing Entire Views:** **0 species** (every single one of the 97 species has at least one dorsal, head, and profile view)
* **Species with Weak Tri-View Support (< 20 specimens):** **2 species** (`camponotus_christi` with 18, and `camponotus_rufoglaucus` with 19)

---

## Specimen-Aware Split Feasibility

To transition from an image-level split to a rigorous **specimen-aware split** (where all images of a physical specimen are grouped into the same partition), each species must contain enough unique specimens to populate train, validation, and test subsets.

The mathematical minimum to support a specimen-aware train/val/test (T/V/T) split is **3 unique specimens** (1 train, 1 val, 1 test).

> [!IMPORTANT]
> **Every single one of the 97 species in our dataset supports a complete specimen-aware train/val/test split.** 
> The absolute weakest species in our dataset, `camponotus_christi`, possesses **18 unique specimens** (yielding 18 complete tri-views). This is far above the mathematical minimum, meaning we can partition our dataset without downgrading any species to "train/val only" or excluding them entirely.

### Species Specimen Counts Cohorts
* **Fewer than 5 specimens:** **0 species** (0.0%)
* **Fewer than 10 specimens:** **0 species** (0.0%)
* **Fewer than 25 specimens:** **20 species** (20.6%) — *Listed in detail below*
* **25 or more specimens:** **77 species** (79.4%) — *Strongly supported cohorts*

### Weak Specimen Cohort (20 Species with < 25 Unique Specimens)
These 20 species represent our "long tail." When performing specimen-aware splitting, these species must be split carefully (e.g., 60% Train / 20% Val / 20% Test) to ensure at least 3-4 specimens are available for validation and testing.

| # | Species Binomial | Unique Specimens | Total Images | Complete Tri-Views | Caste Summary |
| :-: | :--- | :---: | :---: | :---: | :--- |
| 1 | `camponotus_christi` | **18** | 54 | 18 | worker:39, queen:12, male:3 |
| 2 | `camponotus_rufoglaucus` | **20** | 59 | 19 | worker:59 (worker-only) |
| 3 | `camponotus_bonariensis` | **22** | 66 | 22 | worker:66 (worker-only) |
| 4 | `camponotus_hova` | **22** | 65 | 21 | worker:56, male:3, queen:6 |
| 5 | `camponotus_planus` | **23** | 68 | 22 | worker:53, queen:9, male:6 |
| 6 | `carebara_diversa` | **23** | 69 | 23 | worker:63, male:3, queen:3 |
| 7 | `iridomyrmex_anceps` | **23** | 69 | 23 | worker:63, queen:6 |
| 8 | `kalathomyrmex_emeryi` | **23** | 69 | 23 | worker:60, queen:6, male:3 |
| 9 | `mystrium_mirror` | **23** | 69 | 23 | queen:21, worker:36, male:12 |
| 10 | `nylanderia_madagascarensis` | **23** | 69 | 23 | worker:42, queen:12, male:15 |
| 11 | `pseudomyrmex_gracilis` | **23** | 69 | 23 | worker:45, queen:15, male:9 |
| 12 | `technomyrmex_vitiensis` | **23** | 68 | 22 | worker:36, queen:20, male:12 |
| 13 | `azteca_alfari` | **24** | 68 | 21 | worker:45, queen:20, male:3 |
| 14 | `colobopsis_vitrea` | **24** | 72 | 24 | worker:48, queen:24 |
| 15 | `crematogaster_gerstaeckeri` | **24** | 72 | 24 | worker:72 (worker-only) |
| 16 | `eciton_burchellii` | **24** | 72 | 24 | worker:60, male:12 |
| 17 | `monomorium_subopacum` | **24** | 70 | 22 | queen:6, male:10, worker:54 |
| 18 | `pheidole_caffra` | **24** | 72 | 24 | worker:69, queen:3 |
| 19 | `polyrhachis_dives` | **24** | 71 | 23 | worker:50, queen:21 |
| 20 | `zasphinctus_imbecilis` | **24** | 69 | 21 | worker:69 (worker-only) |

---

## Taxon Rankings and Metrics

To evaluate species-level representation, we rank the 97 species using the five primary technical metrics.

### Ranking A: Total Image Count
Represents raw class balance. Under standard training pipelines, this severe imbalance (Max:Min image count of **12.43:1**) causes classifiers to overpredict dominant classes.

* **Top 10 Strongest (A):**
  1. `camponotus_maculatus` (671 images)
  2. `pheidole_megacephala` (386 images)
  3. `tetramorium_sericeiventre` (210 images)
  4. `hypoponera_punctatissima` (190 images)
  5. `dorylus_nigricans` (183 images)
  6. `solenopsis_geminata` (160 images)
  7. `diacamma_rugosum` (157 images)
  8. `tetramorium_simillimum` (157 images)
  9. `pheidole_indica` (153 images)
  10. `cardiocondyla_emeryi` (144 images)
* **Bottom 10 Weakest (A):**
  88. `mystrium_mirror` (69 images)
  89. `nylanderia_madagascarensis` (69 images)
  90. `pseudomyrmex_gracilis` (69 images)
  91. `zasphinctus_imbecilis` (69 images)
  92. `azteca_alfari` (68 images)
  93. `camponotus_planus` (68 images)
  94. `technomyrmex_vitiensis` (68 images)
  95. `camponotus_bonariensis` (66 images)
  96. `camponotus_hova` (65 images)
  97. `camponotus_rufoglaucus` (59 images)
  98. `camponotus_christi` (54 images)

### Ranking B: Total Unique Specimens
Represents the true diversity of unique genomes/biological specimens. This is the core bottleneck for specimen-aware splits. The true specimen-level imbalance ratio is **12.44:1**.

* **Top 10 Strongest (B):**
  1. `camponotus_maculatus` (224 specimens)
  2. `pheidole_megacephala` (130 specimens)
  3. `tetramorium_sericeiventre` (70 specimens)
  4. `hypoponera_punctatissima` (64 specimens)
  5. `dorylus_nigricans` (62 specimens)
  6. `solenopsis_geminata` (54 specimens)
  7. `diacamma_rugosum` (53 specimens)
  8. `tetramorium_simillimum` (53 specimens)
  9. `pheidole_indica` (51 specimens)
  10. `cardiocondyla_emeryi` (48 specimens)
* **Bottom 10 Weakest (B):**
  88. `nylanderia_madagascarensis` (23 specimens)
  89. `pseudomyrmex_gracilis` (23 specimens)
  90. `technomyrmex_vitiensis` (23 specimens)
  91. `azteca_alfari` (24 specimens)
  92. `colobopsis_vitrea` (24 specimens)
  93. `crematogaster_gerstaeckeri` (24 specimens)
  94. `eciton_burchellii` (24 specimens)
  95. `monomorium_subopacum` (24 specimens)
  96. `pheidole_caffra` (24 specimens)
  97. `polyrhachis_dives` (24 specimens)
  98. `zasphinctus_imbecilis` (24 specimens)
  99. `camponotus_bonariensis` (22 specimens)
  100. `camponotus_hova` (22 specimens)
  101. `camponotus_rufoglaucus` (20 specimens)
  102. `camponotus_christi` (18 specimens)

### Ranking C: Complete Tri-View Specimen Count
The absolute number of specimens with all three views (`d`, `h`, `p`). Tri-view models require these clean triplets.

* **Top 10 Strongest (C):**
  1. `camponotus_maculatus` (223 tri-views)
  2. `pheidole_megacephala` (126 tri-views)
  3. `tetramorium_sericeiventre` (70 tri-views)
  4. `hypoponera_punctatissima` (62 tri-views)
  5. `dorylus_nigricans` (60 tri-views)
  6. `solenopsis_geminata` (52 tri-views)
  7. `diacamma_rugosum` (51 tri-views)
  8. `pheidole_indica` (51 tri-views)
  9. `tetramorium_simillimum` (51 tri-views)
  10. `cardiocondyla_emeryi` (48 tri-views)
* **Bottom 10 Weakest (C):**
  88. `monomorium_subopacum` (22 tri-views)
  89. `technomyrmex_vitiensis` (22 tri-views)
  90. `azteca_alfari` (21 tri-views)
  91. `camponotus_hova` (21 tri-views)
  92. `pheidole_biconstricta` (21 tri-views)
  93. `zasphinctus_imbecilis` (21 tri-views)
  94. `camponotus_rufoglaucus` (19 tri-views)
  95. `camponotus_christi` (18 tri-views)

### Ranking D: Specimen Completeness Percentage
The percentage of unique specimens that contain all three standard views. A low percentage indicates a high amount of incomplete specimen metadata.

* **Top 20 Strongest (D - 100.00% complete):**
  1. `tetramorium_sericeiventre` (70/70)
  2. `pheidole_indica` (51/51)
  3. `cardiocondyla_emeryi` (48/48)
  4. `crematogaster_ranavalonae` (43/43)
  5. `pheidole_fervens` (43/43)
  6. `monomorium_floricola` (42/42)
  7. `anochetus_madagascarensis` (39/39)
  8. `tapinoma_melanocephalum` (38/38)
  9. `technomyrmex_pallipes` (38/38)
  10. `tetramorium_lanuginosum` (38/38)
  11. `pheidole_variabilis` (37/37)
  12. `pheidole_sculpturata` (36/36)
  13. `camponotus_grandidieri` (35/35)
  14. `crematogaster_castanea` (35/35)
  15. `camponotus_quadrimaculatus` (34/34)
  16. `lepisiota_capensis` (34/34)
  17. `dorylus_kohli` (33/33)
  18. `pheidole_nodus` (33/33)
  19. `platythyrea_parallela` (33/33)
  20. `mystrium_rogeri` (32/32)
* **Bottom 10 Weakest (D):**
  88. `strumigenys_louisianae` (93.75%)
  89. `bothroponera_cambouei` (94.29%)
  90. `camponotus_atriceps` (94.29%)
  91. `gnamptogenys_striatula` (94.44%)
  92. `camponotus_variegatus` (94.59%)
  93. `camponotus_irritans` (94.74%)
  94. `aphaenogaster_swammerdami` (94.87%)
  95. `camponotus_rufoglaucus` (95.00%)
  96. `camponotus_hova` (95.45%)
  97. `pheidole_pallidula` (95.56%)
  98. `pheidole_parva` (95.56%)
  99. `monomorium_subopacum` (91.67%)
  100. `pheidole_mooreorum` (91.67%)
  101. `pheidole_susannae` (88.46%)
  102. `azteca_alfari` (87.50%)
  103. `zasphinctus_imbecilis` (87.50%)
  104. `monomorium_exiguum` (83.78%)
  105. `pheidole_biconstricta` (**80.77%**)

### Ranking E: Image-to-Specimen Ratio
The average number of images per physical specimen. Since the maximum possible views are 3 (`d`, `h`, `p`), an ideal ratio is exactly **3.00**.

> [!TIP]
> **54 out of 97 species (55.67%) have an image-to-specimen ratio of exactly 3.00**, representing perfect tri-view records for every single specimen in those classes.
> 
> The absolute lowest ratio is **2.69** (`pheidole_biconstricta`), which corresponds to the same class having the lowest specimen completeness percentage (80.77%). This mathematically proves that our dataset is exceptionally complete, with only minor "missing view" pockets in a tiny subset of species.

---

## Caste and View Distribution Analysis

### Caste Confounding Factor
Ants exhibit severe phenotypic polymorphism. Queens are massive and have wing scars/ovipositors, while males possess completely different body plans (including large compound eyes and standard wasp-like wings) that bear no resemblance to worker ants. 

Traditional identification keys are written exclusively for the **worker caste**. Training classifiers on mixed-caste data forces models to develop general representations that try to align males, queens, and workers under a single species label, drastically reducing taxonomic evaluation quality.

* **Caste Balance:** Workers represent **82.01%** (8,443 images) of the dataset. Queens (11.81%) and males (6.18%) introduce substantial morphologic noise.
* **Mixed Caste Ubiquity:** **83 out of 97 species** (85.56%) suffer from mixed caste records.
* **Worker-Only Filtering Feasibility:** 
  If we filter the entire dataset to the `worker` caste only:
  - We retain **8,443 images** (82.01% of total).
  - We retain **2,840 physical specimens** (81.96% of total).
  - We preserve **2,775 complete tri-view specimens** (82.10% of total).
  - The minimum worker specimen count per species drops to **12** (found in `mystrium_mirror` and `technomyrmex_vitiensis`).
  - Because 12 specimens can easily support a 60/20/20 train/val/test split (e.g., 8 train, 2 val, 2 test specimens), **worker-only filtering is 100% mathematically feasible across all 97 species with zero exclusions.**

### View Coverage Completeness
At the species level, dorsal, head, and profile anatomical coverage is **100% complete**. No species is missing any of the three views. 

At the individual physical specimen level, our metadata exhibits an extremely tight completeness profile:
* **Complete Tri-Views (3 views):** 3,380 physical specimens (97.55%)
* **Worker-Only Complete Tri-Views:** 2,775 physical specimens (97.71%)

This demonstrates that view completeness is already at an exceptionally high standard. The primary barrier to baseline reproduction and evaluation is not view coverage, but **specimen leakage** and **caste morphological shifts**.
