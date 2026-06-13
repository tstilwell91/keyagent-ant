# KeyAgent-Ant Migration & Long-Term Roadmap

This document outlines the transition of the legacy **AntID Tutor** project into **KeyAgent-Ant**—a taxonomic-key-grounded, agentic, explainable ant identification research platform.

---

## 1. Summary of Legacy AntID Tutor Structure

The legacy structure contains a complete monolithic web application structure with associated scripts:

- **`app.py`**: Monolithic Flask server handling page routing, file uploads, local model inference, chatbot interactions (local Ollama or OpenAI), and basic geospatial mapping.
- **`downloader/`**: Scripts and URLs/CSVs used to download top ant species images (high or medium quality) from AntWeb.
- **`training/`**: Scripts containing models like EfficientNet-B4 and ResNet-18 architectures, along with SLURM job submission scripts.
- **`inference/`**:
  - `genus/`: Inference script and class indices for genus-level identification.
  - `species/`: Inference script and class indices for species-level identification.
- **`explainability/`**: SHAP-based feature importance visualization code and outputs (`exp1_compare_image_0.png`) for model transparency.
- **`models/`**: Folder structures for model metadata and classes (`models/genus/classes.json` and `models/species/classes.json`).
- **`static/` & `templates/`**: Traditional Flask assets (CSS, JS) and HTML views (chat, identify, results, maps, quizzes).
- **`uploads/`**: Runtime destination directory for images uploaded by users.

---

## 2. Model Mismatch Note & Git Policy

> [!WARNING]
> - The legacy `app.py` strictly expects several root-level model files on startup, such as `models/genus_best_model_full.pth`, `models/classes.json`, and `models/genus_metadata.json`.
> - **Large Model Files Must Stay Outside Git:** Large `.pth`, `.pt`, `.ckpt`, or `.safetensors` model weights are gitignored and must never be committed to the repository.
> - As a result, running `app.py` in its current state will raise a `FileNotFoundError`. We are intentionally preserving `app.py` in its original state for now; model serving and deployment configurations will be solved in a subsequent milestone.

---

## 3. Transition from Ollama to Google-Managed Services

The legacy AntID Tutor app used a local Ollama setup running `llama3.2` for chatbot functionality. 

For **KeyAgent-Ant**, the long-term architecture moves entirely toward Google-managed services to build an enterprise-grade, scalable, and highly available agentic framework:

- **Gemini & Vertex AI:** Replace Ollama for grounded explanations, visual question answering, and multi-turn educational coaching.
- **Agent Development Kit (ADK):** Enable code-first agent design, orchestration, and systematic prompt engineering.
- **Cloud Run:** Serverless hosting for the backend API and model/agent service layers.
- **Firebase App Hosting:** Secure, scalable frontend application hosting.
- **Vertex AI Model Registry:** Stable, version-controlled tracking of trained model checkpoints.
- **Cloud Storage:** Durable object storage for image datasets, model checkpoints, and generated SHAP explanation logs.
- **Firestore / BigQuery:** Scalable database logging for predictions, user-study feedback, and research annotations.
- **Secret Manager:** Secure storage of API credentials and keys (ArcGIS, Vertex AI).

---

## 4. Current Work: New `src/antid` Structure

In this first milestone, we have laid a clean, modern, and research-ready foundation *beside* the legacy folders without modifying them:

```
src/
└── antid/
    ├── __init__.py
    └── data/
        ├── __init__.py
        ├── detect_view.py       # Deterministic AntWeb view parser
        ├── build_manifest.py     # Recursive image scanner and registry builder
        ├── build_splits.py       # Reproducible stratified train/val/test splits
        └── validate_dataset.py   # Dataset manifest verification and consistency checks
```

We have also added a unit testing harness under `tests/`:
```
tests/
├── test_detect_view.py
├── test_dataset_manifest.py
└── test_build_splits.py
```

### What is Intentionally Left Intact (Not Migrated Yet):
- **Ollama-related code** in `app.py` remains active and unmodified.
- **Flask routes** and frontend templates remain completely untouched.
- **Model files and server configurations** are not altered.

---

## 5. Next Milestones

We will proceed iteratively following the KeyAgent-Ant research roadmap:

### Milestone 1: Baseline Reproduction
- Set up a clean local model training environment and verify we can reproduce or train the baseline genus/species classifiers on the downloaded AntWeb dataset.

### Milestone 2: Model Evaluation Metrics
- Establish systematic validation and evaluation scripts. Generate confusion matrices, F1-scores, precision, and recall metrics across view types.

### Milestone 3: Taxonomic Trait Schema
- Design a schema and database models for morphological traits (e.g., number of petiole nodes, presence of spines, propodeal spine shape) mapped to specific genera and species.

### Milestone 4: Taxonomic Key Reasoner
- Implement a logic-grounded Taxonomic Key engine that guides users through diagnostic keys, verifying predictions using morphological criteria.

### Milestone 5: Comparative Explainability (XAI)
- Standardize visual (SHAP, Grad-CAM) and symbolic explainability tools to compare classifier focus points against taxonomic key diagnostic traits.

### Milestone 6: Grounded Explanation Agent (ADK & Gemini)
- Design a multi-agent system using the Google ADK and Gemini. Ground the agent's identification tutoring using both the classifier results and the logic of the Taxonomic Key.

### Milestone 7: Google Services Integration
- Port the backend to Cloud Run, migrate the frontend to Firebase Hosting, set up Secret Manager, and connect Firestore for telemetry and prediction logging.

### Milestone 8: AlphaEvolve Policy Optimization
- Apply evolutionary optimization (AlphaEvolve) to dynamically optimize the agent's interaction policies, dialogue steps, and question-asking strategies for human-in-the-loop validation studies.
