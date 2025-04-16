import os
import uuid
import numpy as np
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import tensorflow as tf
from dotenv import load_dotenv
import openai
import requests
from geopy.geocoders import Nominatim
import json
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}

# Initialize OpenAI client
openai.api_key = os.getenv('OPENAI_API_KEY')

# Initialize ArcGIS API key
arcgis_api_key = os.getenv('ARCGIS_API_KEY')

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Add route to serve uploaded files
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Mock ant species database (in a real app, this would come from a database)
ANT_SPECIES = {
    0: {
        "name": "Camponotus pennsylvanicus",
        "common_name": "Black Carpenter Ant",
        "description": "Large black ants that nest in wood. They are important decomposers in forest ecosystems.",
        "habitat": "Forests, urban areas, particularly in dead or decaying wood",
        "distribution": "Eastern North America",
        "facts": [
            "Can grow up to 13mm in length",
            "Do not eat wood but excavate it for nesting",
            "Have a major and minor worker caste system",
            "Can live for several years"
        ]
    },
    1: {
        "name": "Solenopsis invicta",
        "common_name": "Red Imported Fire Ant",
        "description": "Aggressive reddish-brown ants known for their painful sting.",
        "habitat": "Open sunny areas, meadows, agricultural land",
        "distribution": "Southern United States, originally from South America",
        "facts": [
            "Introduced to the US in the 1930s",
            "Build large mound nests that can damage agricultural equipment",
            "Have a potent alkaloid venom",
            "Can survive flooding by forming living rafts"
        ]
    },
    2: {
        "name": "Lasius niger",
        "common_name": "Black Garden Ant",
        "description": "Small black ants commonly found in gardens and homes.",
        "habitat": "Gardens, meadows, urban areas",
        "distribution": "Europe, parts of Asia and North America",
        "facts": [
            "Form trails to food sources",
            "Farm aphids for honeydew",
            "Queens can live for up to 15 years",
            "Colonies can contain up to 15,000 workers"
        ]
    }
}

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Mock CNN model loading (in a real app, you would load a trained model)
def load_model():
    # This is a placeholder. In a real app, you would load a trained TensorFlow model
    print("Loading model...")
    # Return a mock model that always predicts class 0 (for demonstration purposes)
    class MockModel:
        def predict(self, img_array):
            # Return a mock prediction (always predicts the first class with high confidence)
            return np.array([[0.9, 0.05, 0.05]])
    return MockModel()

# Load the model at startup
model = load_model()

# Preprocess image for the model
def preprocess_image(image_path):
    img = Image.open(image_path)
    img = img.resize((224, 224))  # Resize to the input size expected by the model
    img_array = np.array(img) / 255.0  # Normalize pixel values
    img_array = np.expand_dims(img_array, axis=0)  # Add batch dimension
    return img_array

# Generate a response from the GPT model
def get_gpt_response(prompt):
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
        print(f"Error with OpenAI API: {e}")
        return "I'm sorry, I'm having trouble connecting to my knowledge base right now. Please try again later."

# Generate a response from the local Ollama server with llama3.2 model
def get_ollama_response(prompt):
    try:
        # Ollama API endpoint
        url = "http://localhost:11434/api/generate"
        
        # Prepare the request payload
        payload = {
            "model": "llama3.2",
            "prompt": f"You are an expert myrmecologist (ant scientist) named AntTutor. Provide accurate, educational information about ants in a friendly, engaging manner. Keep responses concise but informative.\n\nUser: {prompt}\n\nAntTutor:",
            "stream": False
        }
        
        # Send the request to Ollama
        response = requests.post(url, json=payload)
        
        # Check if the request was successful
        if response.status_code == 200:
            # Parse the JSON response
            result = response.json()
            return result.get("response", "I'm sorry, I couldn't generate a response.")
        else:
            print(f"Error with Ollama API: Status code {response.status_code}")
            return f"I'm sorry, there was an error connecting to my knowledge base. Status code: {response.status_code}"
    except Exception as e:
        print(f"Error with Ollama API: {e}")
        return "I'm sorry, I'm having trouble connecting to my knowledge base right now. Please try again later."

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/identify', methods=['GET', 'POST'])
def identify():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['file']
        
        # If user does not select file, browser also submits an empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            # Generate a unique filename
            filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Preprocess the image and make a prediction
            img_array = preprocess_image(filepath)
            predictions = model.predict(img_array)
            predicted_class = np.argmax(predictions[0])
            confidence = float(predictions[0][predicted_class])
            
            # Get species information
            species_info = ANT_SPECIES.get(predicted_class, {
                "name": "Unknown Species",
                "common_name": "Could not identify",
                "description": "The model could not confidently identify this species.",
                "habitat": "Unknown",
                "distribution": "Unknown",
                "facts": ["Try uploading a clearer image", "Make sure the ant is clearly visible"]
            })
            
            # Store the results in session
            session['identification_results'] = {
                'filename': filename,
                'species_name': species_info['name'],
                'common_name': species_info['common_name'],
                'confidence': confidence,
                'description': species_info['description'],
                'habitat': species_info['habitat'],
                'distribution': species_info['distribution'],
                'facts': species_info['facts']
            }
            
            return redirect(url_for('results'))
    
    return render_template('identify.html')

@app.route('/results')
def results():
    # Get results from session
    results = session.get('identification_results', None)
    if not results:
        return redirect(url_for('identify'))
    
    return render_template('results.html', results=results)

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.method == 'POST':
        user_message = request.form.get('message', '')
        if user_message:
            # Use Ollama instead of OpenAI
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
    
    # In a real application, you would save this to a database
    # For this demo, we'll just return success
    return jsonify({
        'success': True,
        'message': f'Added observation of {species} at coordinates ({lat}, {lng})'
    })

@app.route('/quiz')
def quiz():
    # In a real app, you would generate questions from a database
    # For this demo, we'll use a static set of questions
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
