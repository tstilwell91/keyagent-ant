# Ant Species Identification and Learning Platform

An interactive web application that combines computer vision and natural language processing to help students identify ant species and learn about myrmecology.

## Features

- **Ant Species Identification**: Upload images to identify ant species using a trained CNN model
- **Interactive Chatbot**: Get detailed explanations and answers to questions about ants using a GPT-based tutor
- **Species Distribution Map**: (ArcGIS integration temporarily disabled)
- **Interactive Quizzes**: Test your knowledge with dynamically generated quizzes

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your API keys:
   ```
   OPENAI_API_KEY=your_openai_api_key
   ARCGIS_API_KEY=your_arcgis_api_key
   ```
4. Run the application:
   ```
   python app.py
   ```

## Project Structure

- `/static`: CSS, JavaScript, and image assets
- `/templates`: HTML templates
- `/models`: CNN model for ant species identification
- `/uploads`: Temporary storage for uploaded images
