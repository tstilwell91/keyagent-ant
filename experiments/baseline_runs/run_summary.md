# Baseline Run Summary

| Run | Job ID | Dataset / Split | Model | Epochs | Best Val Acc | Final Train Acc | Final Val Acc | Notes |
|---|---:|---|---|---:|---:|---:|---:|---|
| Smoke B4 v2 | 5745354 | v2 curated | EfficientNet-B4 | 1 | 0.2779 | 0.1053 | 0.2779 | Smoke test only; proves pipeline/classes load |
| B4 species pair | 5745363 | v1 specimen-aware | EfficientNet-B4 | 25 | 0.7358 | 0.8632 | 0.7314 | Main baseline comparison run |
| B4 v2 curated | 5745393 | v2 curated | EfficientNet-B4 | 25 | 0.7221 | 0.8700 | 0.7176 | Curated worker/tri-view dataset run |
