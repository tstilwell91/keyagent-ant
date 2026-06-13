# Holdout Evaluation Summary: EfficientNet-B4 Species Classification

| Dataset | Test Examples | Top-1 | Top-3 | Top-5 | Macro-F1 | Weighted-F1 | Balanced Accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 original | 1513 | 0.7548 | 0.9081 | 0.9511 | 0.7433 | 0.7493 | 0.7373 |
| v1 specimen-aware | 1474 | 0.7218 | 0.8955 | 0.9369 | 0.7046 | 0.7145 | 0.6974 |
| v2 curated | 981 | 0.7268 | 0.8838 | 0.9450 | 0.7239 | 0.7213 | 0.7265 |

## Interpretation

The v1-original image-level split achieves the highest Top-1 accuracy, but this split is expected to benefit from specimen leakage because different views of the same physical specimen may appear across train/test partitions.

The v1 specimen-aware split provides a stricter leakage-free baseline and drops to 0.7218 Top-1 accuracy and 0.6974 balanced accuracy.

The v2 curated dataset achieves 0.7268 Top-1 accuracy and 0.7265 balanced accuracy. This is notable because v2 curated uses fewer test images but improves over v1 specimen-aware on Top-1, Macro-F1, and Balanced Accuracy. This suggests that worker-only filtering, tri-view completeness, class capping, and specimen-aware partitioning improve fair species-level generalization.

## Current conclusion

EfficientNet-B4 species classification does not collapse under the curated v2 dataset. The curated dataset appears to recover and slightly improve fair holdout performance compared with the leakage-free v1 specimen-aware split.

## Caveats

These results are from one training seed and one architecture. Next steps should include ResNet18 comparison, multiple seeds, confusion-matrix review, and per-species error analysis.
