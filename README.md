# Ant Genus Identification and Learning Platform

An interactive web application that combines computer vision and language models to help students identify ant genus and explore myrmecology.

## Features

- **Ant Genus Identification**: Upload an ant image to predict its genus using a trained EfficientNet-B4 CNN model.
- **AI Chatbot (AntTutor)**: Ask questions and receive detailed, natural language answers about ant biology and behavior.
- **Species Mapping**: (Optional) Plot sightings on a map (ArcGIS support available).
- **Interactive Quizzes**: Learn more about ants through built-in educational quizzes.

## Requirements

- Python 3.8+
- PyTorch
- Flask
- torchvision (with `efficientnet_b4` weights)
- An LLM provider:
  - **Ollama** (default): Must be installed locally. [Download Ollama](https://ollama.com/)
    - Required model: `llama3.2`
      ```
      ollama run llama3.2
      ```
  - **OpenAI**: Requires an OpenAI API key

## Setup
1. Clone this repository:
   ```
   git clone https://github.com/yourusername/ant-id-tutor.git
   cd ant-id-tutor
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory and configure your API keys and LLM provider:
   ```
   # LLM Provider: choose "ollama" (default) or "openai"
   LLM_PROVIDER=ollama

   # Required only if using OpenAI
   OPENAI_API_KEY=your_openai_api_key

   # Optional: For map features
   ARCGIS_API_KEY=your_arcgis_api_key
   ```

4. Start the app:
   ```
   python app.py
   ```

5. Open [http://localhost:5002](http://localhost:5002) in your browser.

## Project Structure

- `/static`: CSS, JS, and logo assets
- `/templates`: HTML UI (Flask Jinja templates)
- `/models`: Trained CNN weights, class list, and genus metadata
- `/uploads`: Temporary storage for uploaded user images

## Model Files

Copy the contents of the `models/genus/` folder into the `models/` directory:

- `genus_best_model_full.pth`: Trained EfficientNet-B4 model
- `classes.json`: List of genus labels (lowercase)
- `genus_metadata.json`: Descriptions, habitats, and facts per genus

