import os
import uuid
import numpy as np
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models, transforms
from dotenv import load_dotenv
import openai
import requests
from geopy.geocoders import Nominatim
import json
from datetime import datetime

# Load environment variables
load_dotenv()

# Define LLM provider
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
if LLM_PROVIDER not in ["ollama", "openai"]:
    raise ValueError(f"Unsupported LLM_PROVIDER: '{LLM_PROVIDER}'. Must be 'ollama' or 'openai'.")

# Initialize OpenAI client if needed
openai.api_key = os.getenv("OPENAI_API_KEY")
if LLM_PROVIDER == "openai" and not openai.api_key:
    raise EnvironmentError("OPENAI_API_KEY is not set but LLM_PROVIDER is 'openai'. Please set it in your .env file.")

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}

# Initialize ArcGIS API key
arcgis_api_key = os.getenv('ARCGIS_API_KEY')

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Load model
def load_model():
    full_model_path = os.path.join("models", "genus_best_model_full.pth")
    print(f"Loading model from: {full_model_path}")
    model = torch.load(full_model_path, map_location="cpu", weights_only=False)
    model.eval()
    print("Model loaded and set to eval mode.")
    return model

model = load_model()

# Load class names
with open(os.path.join("models", "classes.json")) as f:
    class_names = json.load(f)
print(f"Loaded {len(class_names)} class names.")

# Load genus metadata
with open(os.path.join("models", "genus_metadata.json")) as f:
    genus_metadata = json.load(f)

# Preprocess image for the model
def preprocess_image(image_path):
    print(f"Preprocessing image: {image_path}")
    img = Image.open(image_path).convert("RGB")
    transform = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    return transform(img).unsqueeze(0)

# LLM response functions
def get_ollama_response(prompt):
    try:
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "llama3.2",
            "prompt": f"You are an expert myrmecologist (ant scientist) named AntTutor. Provide accurate, educational information about ants in a friendly, engaging manner. Keep responses concise but informative.\n\nUser: {prompt}\n\nAntTutor:",
            "stream": False
        }
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            return response.json().get("response", "I'm sorry, I couldn't generate a response.")
        return f"Ollama error: status code {response.status_code}"
    except Exception as e:
        print(f"Ollama exception: {e}")
        return "Ollama is unavailable. Please try again later."

def get_openai_response(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert myrmecologist (ant scientist) named AntTutor. Provide accurate, educational information about ants in a friendly, engaging manner. Keep responses concise but informative."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI exception: {e}")
        return "OpenAI is unavailable. Please try again later."

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/identify', methods=['GET', 'POST'])
def identify():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            print(f"Saved uploaded image to: {filepath}")

            img_tensor = preprocess_image(filepath)
            with torch.no_grad():
                logits = model(img_tensor)
                print(f"Logits: {logits}")
                probs = F.softmax(logits, dim=1)
                print(f"Probabilities: {probs}")
                confidence, idx = probs.max(dim=1)
                predicted_idx = idx.item()
                confidence = confidence.item()
                top_probs, top_idxs = probs[0].topk(3)

            species_name = class_names[predicted_idx]
            top_predictions = [(class_names[i], round(p.item(), 4)) for i, p in zip(top_idxs, top_probs)]
            print(f"Predicted class index: {predicted_idx}, name: {species_name}, confidence: {confidence:.4f}")

            warning_message = "" if confidence > 0.8 else "This prediction has low confidence. Consider submitting another image for verification."

            genus_info = genus_metadata.get(species_name.lower(), {})

            session['identification_results'] = {
                'filename': filename,
                'species_name': species_name,
                'common_name': species_name,
                'confidence': confidence,
                'description': genus_info.get('description', ''),
                'habitat': genus_info.get('habitat', ''),
                'distribution': genus_info.get('distribution', ''),
                'facts': genus_info.get('facts', []),
                'top_predictions': top_predictions,
                'confidence_warning': warning_message
            }
            return redirect(url_for('results'))
    return render_template('identify.html')

@app.route('/results')
def results():
    results = session.get('identification_results', None)
    if not results:
        return redirect(url_for('identify'))
    return render_template('results.html', results=results)

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.method == 'POST':
        user_message = request.form.get('message', '')
        if user_message:
            if LLM_PROVIDER == "openai":
                response = get_openai_response(user_message)
            else:
                response = get_ollama_response(user_message)
            return jsonify({'response': response})
    return render_template('chat.html')

@app.route('/map')
def map_view():
    return render_template('map.html', api_key=arcgis_api_key)

@app.route('/add_observation', methods=['POST'])
def add_observation():
    data = request.json
    lat = data.get('latitude')
    lng = data.get('longitude')
    species = data.get('species')
    notes = data.get('notes')
    return jsonify({
        'success': True,
        'message': f'Added observation of {species} at coordinates ({lat}, {lng})'
    })

@app.route('/quiz')
def quiz():
    questions = [
        {
            "question": "Which ant species is known for its painful sting?",
            "options": ["Camponotus pennsylvanicus", "Solenopsis invicta", "Lasius niger"],
            "answer": 1
        },
        {
            "question": "What do carpenter ants do with wood?",
            "options": ["Eat it for nutrition", "Excavate it for nesting", "Convert it to fungal gardens"],
            "answer": 1
        },
        {
            "question": "Which ant species farms aphids for honeydew?",
            "options": ["Black Carpenter Ant", "Red Imported Fire Ant", "Black Garden Ant"],
            "answer": 2
        }
    ]
    return render_template('quiz.html', questions=questions)

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True, port=5002)