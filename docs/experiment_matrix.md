# KeyAgent-Ant Experiment Matrix & Metric Standards

This document establishes the official experiment matrix and evaluation metrics for the reproducible baseline training runs of **KeyAgent-Ant**.

---

## 1. Standardized Evaluation Metrics

> [!IMPORTANT]
> **Milestone Boundary:** The current milestone focuses strictly on enabling manifest-driven baseline training (loss and simple Top-1 validation accuracy tracking). Full holdout test-set evaluation, confusion matrices, multi-tier frequency-band evaluation, and rich metrics (Top-3/5, Macro/Weighted F1, Balanced Accuracy) are part of the **Next Evaluation Milestone**. The baseline training scripts do *not* automatically generate these rich metrics yet.

To ensure robust taxonomic classification performance and directly address the severe class imbalances of real-world datasets, all experiments must eventually compute and report the following standard metrics on the holdout **test split** once the evaluation suite is developed:

### Core Classification Metrics
*   **Top-1 Accuracy:** The standard fraction of correct predictions where the top-1 predicted class matches the ground-truth label.
*   **Top-3 Accuracy:** Fraction of predictions where the ground-truth class is within the model's top-3 predicted logits.
*   **Top-5 Accuracy:** Fraction of predictions where the ground-truth class is within the model's top-5 predicted logits.
*   **Macro-F1 Score:** Unweighted average of per-class F1-scores. This treats all classes equally, exposing poor performance on rare/long-tail species.
*   **Weighted-F1 Score:** Average of per-class F1-scores weighted by class support (number of true instances).
*   **Balanced Accuracy:** The average of per-class recall scores, equivalent to the macro-average of recall.
*   **Per-Class Recall:** The individual class recall rate ($TP / (TP + FN)$) to identify specific taxonomic weak spots.
*   **Confusion Matrix:** Full $C \times C$ contingency matrix to track inter-species and inter-genus misclassifications.

### Multi-Tier Frequency-Band Evaluation
Species are partitioned into three frequency-based tiers depending on their specimen representation in the unfiltered `v1-original` dataset:
1.  **Head Species (High Abundance):** Species represented by $\ge 25$ unique specimens ($\ge 100$ total images).
2.  **Mid-Frequency Species (Moderate Abundance):** Species represented by $5$ to $24$ unique specimens ($15$ to $99$ total images).
3.  **Tail Species (Low Abundance / Long-Tail):** Species represented by $< 5$ unique specimens ($< 15$ total images).

Separate accuracies and recall rates must be compiled across these tiers to audit whether the model performs adequately on low-support, highly-valuable biological specimens.

---

## 2. Baseline Experiment Matrix

| Experiment | Model Architecture | Label Target | Dataset Variant | Split Style | Expected Metrics & Outputs |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Experiment 1** | EfficientNet-B4 | Genus | `v1-original` | Standard Random Split (80/20 train/val) | - Top-1/3/5 Acc, Macro/Weighted F1<br>- Best checkpoint: `genus_best_model.pth` |
| **Experiment 2** | EfficientNet-B4 | Species | `v1-original` | Standard Random Split (80/20 train/val) | - Top-1/3/5 Acc, Macro/Weighted F1<br>- Multi-tier frequency-band accuracy<br>- Best checkpoint: `species_b4_v1orig_random.pth` |
| **Experiment 3** | EfficientNet-B4 | Species | `v1-specimen-aware` | Specimen-Grouped Split (70/15/15 train/val/test) | - Same metrics as Exp 2<br>- Head/Mid/Tail analysis<br>- Best checkpoint: `species_b4_v1aware_grouped.pth`<br>- *Enables detection of random split leakage inflation.* |
| **Experiment 4** | EfficientNet-B4 | Species | `v2-curated` | Specimen-Grouped Split (70/15/15 train/val/test) | - Same metrics as Exp 3<br>- Confusion matrix analysis<br>- Best checkpoint: `species_b4_v2curated_grouped.pth`<br>- *Evaluates worker-only, view-complete performance.* |
| **Experiment 5** | ResNet18 | Species | `v2-curated` | Specimen-Grouped Split (70/15/15 train/val/test) | - Same metrics as Exp 4<br>- Comparative performance vs. EfficientNet-B4<br>- Best checkpoint: `species_r18_v2curated_grouped.pth` |

---

## 3. Experiment Configuration Details

### Experiment 1: Genus-Level Baseline
*   **Target:** `genus` (lowercase strings, 42 classes)
*   **Dataset Path:** `data/splits/v1_original/`
*   **CLI Invocation:**
    ```bash
    PYTHONPATH=src python training/EfficientNet-B4.py \
        --split_dir data/splits/v1_original \
        --target_type genus \
        --image_root . \
        --save_model genus_best_model.pth
    ```

### Experiment 2: Species-Level Random Baseline
*   **Target:** `species` (capitalized binomials, 97 classes)
*   **Dataset Path:** `data/splits/v1_original/`
*   **CLI Invocation:**
    ```bash
    PYTHONPATH=src python training/EfficientNet-B4.py \
        --split_dir data/splits/v1_original \
        --target_type species \
        --image_root . \
        --save_model species_b4_v1orig_random.pth
    ```

### Experiment 3: Species-Level Specimen-Aware Baseline (Leakage-Free)
*   **Target:** `species` (97 classes)
*   **Dataset Path:** `data/splits/v1_specimen_aware/`
*   **CLI Invocation:**
    ```bash
    PYTHONPATH=src python training/EfficientNet-B4.py \
        --split_dir data/splits/v1_specimen_aware \
        --target_type species \
        --image_root . \
        --save_model species_b4_v1aware_grouped.pth
    ```

### Experiment 4: Species-Level Curated Baseline
*   **Target:** `species` (97 classes, worker caste only, tri-view complete, capped representation)
*   **Dataset Path:** `data/splits/v2_curated/`
*   **CLI Invocation:**
    ```bash
    PYTHONPATH=src python training/EfficientNet-B4.py \
        --split_dir data/splits/v2_curated \
        --target_type species \
        --image_root . \
        --save_model species_b4_v2curated_grouped.pth
    ```

### Experiment 5: ResNet-18 Curated Baseline
*   **Target:** `species` (97 classes)
*   **Dataset Path:** `data/splits/v2_curated/`
*   **CLI Invocation:**
    ```bash
    PYTHONPATH=src python training/resnet18.py \
        --split_dir data/splits/v2_curated \
        --target_type species \
        --image_root . \
        --save_model species_r18_v2curated_grouped.pth
    ```

---

## 4. Next Evaluation Milestone

The current training scripts track and report:
- Training loss
- Validation loss
- Validation Top-1 accuracy

To evaluate models on the holdout `test.csv` splits and generate the standardized metrics described in Section 1, the **Next Evaluation Milestone** will introduce:
1.  **A dedicated offline evaluation script (`inference/evaluate_model.py`):**
    - Load any saved PyTorch model checkpoint (e.g., `.pth` files) and its corresponding class mapping JSON (e.g., `_classes.json`).
    - Load the holdout test manifest (`test.csv`).
    - Run inference on the test split.
2.  **Rich Metrics Generation:**
    - Compute Top-1, Top-3, and Top-5 accuracy.
    - Compute Macro-F1, Weighted-F1, and Balanced Accuracy.
    - Generate a confusion matrix saved as a CSV/image artifact.
    - Partition test-set performance into Head, Mid, and Tail categories based on specimen counts to audit long-tail accuracy.
3.  **Comparative Analysis:**
    - Enable cross-model comparisons (e.g., comparing ResNet18 vs. EfficientNet-B4 baseline on `v2-curated`).
    - Output LaTeX and markdown tables suitable for publication.
