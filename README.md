# Ant Genus Identification and Learning Platform

An interactive web application that combines computer vision and language models to help students identify ant genus and explore myrmecology.

## Features

* **Ant Genus Identification**: Upload an ant image to predict its genus using a trained EfficientNet-B4 CNN model.
* **AI Chatbot (AntTutor)**: Ask questions and receive detailed, natural language answers about ant biology and behavior.
* **Species Mapping**: (Optional) Plot sightings on a map (ArcGIS support available).
* **Interactive Quizzes**: Learn more about ants through built-in educational quizzes.

## Requirements

* Python 3.8+
* PyTorch
* Flask
* torchvision (with `efficientnet_b4` weights) 
* An LLM provider:

  * **Ollama** (default): Must be installed locally. [Download Ollama](https://ollama.com/)

    * Required model: `llama3.2`

      ```bash
      ollama run llama3.2
      ```
  * **OpenAI**: Requires an OpenAI API key

## Setup

1. Clone this repository:

   ```bash
   git clone https://github.com/tstilwell91/cs895_project_ants.git
   cd cs895_project_ants
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory and configure your API keys and LLM provider:

   ```bash
   # LLM Provider: choose "ollama" (default) or "openai"
   LLM_PROVIDER=ollama

   # Required only if using OpenAI
   OPENAI_API_KEY=your_openai_api_key

   # Optional: For map features
   ARCGIS_API_KEY=your_arcgis_api_key
   ```

4. Copy the local model files from `models/genus/` to `models/`:

   ```bash
   cp models/genus/* models/
   ```

5. Start the app:

   ```bash
   python app.py
   ```

6. Open [http://localhost:5002](http://localhost:5002) in your browser.

## Project Structure

* `/static`: CSS, JS, and logo assets
* `/templates`: HTML UI (Flask Jinja templates)
* `/models`: Trained CNN weights, class list, and genus metadata
* `/uploads`: Temporary storage for uploaded user images

## Model Files

You can use the genus classification model in one of two ways:

1. **Local model files**: Copy the contents of the `models/genus/` folder into the `models/` directory:

   * `genus_best_model_full.pth`: Trained EfficientNet-B4 model
   * `classes.json`: List of genus labels (lowercase)
   * `genus_metadata.json`: Descriptions, habitats, and facts per genus

2. **Hugging Face model repository**:
   The same model is also hosted at [huggingface.co/tstilwel/antID-tutor-genus](https://huggingface.co/tstilwel/antID-tutor-genus) for easy access or integration into external pipelines.

   Example code to load model from Hugging Face:

   ```python
   from huggingface_hub import hf_hub_download
   import torch

   # Download model file from repo
   model_path = hf_hub_download(repo_id="tstilwel/antID-tutor-genus", filename="genus_best_model_full.pth")

   # Load the model
   model = torch.load(model_path, map_location="cpu")
   model.eval()
   ```

## Testing Inference Locally

To test the trained CNN model on a local system outside the web application, you can run the standalone inference script:

### Steps

1. Navigate to the `inference/genus/` folder:

   ```bash
   cd inference/genus
   ```

2. (Optional) If using a GPU node or container environment on the ODU Wahab cluster, allocate a GPU:

   ```bash
   salloc -p gpu --gres gpu:1
   module load container_env pytorch-gpu/2.5.1
   ```

3. Run the inference script. The model can be found in the `models/genus/` folder or downloaded from Hugging Face:

   ```bash
   crun -p ~/envs/myrmecid python inference.py \
     --image casent0901862_h_1_med.jpg \
     --model genus_best_model_full.pth \
     --classes classes.json
   ```

### Expected Output

The script will:

* Load the CNN model
* Preprocess the image
* Output the predicted ant genus and confidence score

Example:

```
Using device: cuda
Detected 42 classes.
Loading model from: genus_best_model_full.pth
Preprocessing image: casent0901862_h_1_med.jpg
Predicted genus: polyrhachis (confidence: 1.0000)
```

Note: You may see a `FutureWarning` from PyTorch regarding `torch.load`. This is expected and safe when using your own model checkpoints.

