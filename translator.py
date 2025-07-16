# Live Music Translator - Python Version
#
# This script listens to audio from your microphone, transcribes the speech,
# and translates it into English in near real-time.
#
# Required Libraries:
# You'll need to install a few Python libraries to run this script.
# Open your terminal or command prompt and run the following commands:
#
# pip install SpeechRecognition
# pip install PyAudio
# pip install requests
# pip install python-dotenv
# pip install Flask
# pip install flask-socketio
#
# Note: PyAudio can sometimes be tricky to install. If you run into issues,
# you may need to first install the PortAudio development libraries for your
# operating system (e.g., `sudo apt-get install portaudio19-dev` on Debian/Ubuntu
# or `brew install portaudio` on macOS).

import speech_recognition as sr
import requests
import json
import time
import os
from dotenv import load_dotenv
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import wave
import io

# Load environment variables from .env file if present
load_dotenv()

# --- Flask App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
CORS(app) # Enable CORS for all routes
socketio = SocketIO(app, cors_allowed_origins="*")

# --- State Management ---
# Use a dictionary to store the state for each client (session ID)
client_states = {}

# --- Configuration ---
# Your Google AI Studio API Key.
# It's recommended to set this as an environment variable for security.
# You can get a key from https://aistudio.google.com/
API_KEY = os.environ.get("GEMINI_API_KEY")  # Read Gemini API key from environment variable
# I've set the default to Punjabi as requested. You can change this to any other code in the list.
# SOURCE_LANGUAGE_CODE = "hi-IN" # Language to translate from (e.g., "hi-IN" for Hindi, "es-ES" for Spanish, "pa-IN" for Punjabi)

# Check for Google Cloud credentials
if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    print("\n[Warning] GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")
    print("          The application will fall back to a less reliable speech recognition method.")
    print("          For best results, please set up Google Cloud Speech-to-Text API credentials.")
    print("          See: https://cloud.google.com/docs/authentication/provide-credentials-adc\n")


# A simple mapping for display purposes.
LANG_MAP = {
    "es-ES": "Spanish",
    "fr-FR": "French",
    "de-DE": "German",
    "it-IT": "Italian",
    "pt-BR": "Portuguese",
    "ru-RU": "Russian",
    "ja-JP": "Japanese",
    "ko-KR": "Korean",
    "zh-CN": "Chinese (Mandarin)",
    "pa-IN": "Punjabi",
    "hi-IN": "Hindi", # Added Hindi
}

def get_language_name(code, sid):
    """Returns the full name of the language from its code."""
    source_language = client_states.get(sid, {}).get('language', 'hi-IN')
    return LANG_MAP.get(source_language, source_language)

def translate_text(text, sid):
    """
    Uses the Gemini API to translate the given text to English.
    """
    if not text.strip():
        return ""
    if not API_KEY:
        return "ERROR: Gemini API key is not set. Please add it to the script."

    # The URL for the Gemini API
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

    # The prompt and payload for the API request
    source_language_name = get_language_name(None, sid)
    prompt = f"Translate the following text from {source_language_name} to English: \"{text}\""
    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": prompt}]
        }]
    }
    headers = {'Content-Type': 'application/json'}

    try:
        # Make the POST request to the API
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        # Parse the JSON response
        result = response.json()

        # Extract the translated text
        if (result.get('candidates') and
                result['candidates'][0].get('content') and
                result['candidates'][0]['content'].get('parts')):
            translated = result['candidates'][0]['content']['parts'][0]['text']
            return translated.strip()
        else:
            return "Translation could not be retrieved from the API response."

    except requests.exceptions.RequestException as e:
        print(f"\n[Error] API request failed: {e}")
        return "Failed to connect to the translation service."
    except Exception as e:
        print(f"\n[Error] An unexpected error occurred during translation: {e}")
        return "An error occurred during translation."


@socketio.on('process_audio')
def handle_process_audio(data):
    """
    Receives a blob of audio data from a client, transcribes, and translates it.
    """
    sid = request.sid
    print(f"[{sid}] Received audio data.")

    # The raw audio data is in data['audio']
    # The client also sends metadata needed to interpret the audio
    audio_bytes = data.get('audio')
    sample_rate = data.get('sample_rate', 16000) # Default to 16kHz if not provided
    # Sample width is 2 bytes for 16-bit audio, which is what we'll aim for from the client
    sample_width = data.get('sample_width', 2)

    if not audio_bytes:
        print(f"[{sid}] No audio data received.")
        socketio.emit('status_update', {'status': 'Error: No audio data received.'}, room=sid)
        return

    # Let the user know we are processing
    socketio.emit('status_update', {'status': 'Processing...'}, room=sid)
    print(f"[{sid}] Processing audio...")

    # Create an AudioData object for the speech_recognition library
    try:
        audio_data = sr.AudioData(audio_bytes, sample_rate, sample_width)
    except Exception as e:
        print(f"[{sid}] Error creating AudioData object: {e}")
        socketio.emit('status_update', {'status': f'Error processing audio format: {e}'}, room=sid)
        return

    r = sr.Recognizer()
    source_language = client_states.get(sid, {}).get('language', 'hi-IN')

    # Recognize speech
    try:
        # Use Google Cloud Speech-to-Text if credentials are available
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            print(f"[{sid}] Using Google Cloud Speech-to-Text API with default model for {source_language}.")
            original_text = r.recognize_google_cloud(
                audio_data,
                language_code=source_language,
                enable_automatic_punctuation=True
            )
        else:
            # Fallback to the less reliable web speech API
            print(f"[{sid}] Using standard Web Speech API (less reliable).")
            original_text = r.recognize_google(audio_data, language=source_language)
            
        print(f"[{sid}] Original: {original_text}")

        # Translate the recognized text
        translated_text = translate_text(original_text, sid)
        print(f"[{sid}] Translated: {translated_text}")

        # Send the final update to the specific client
        socketio.emit('translation_update', {
            'original': original_text,
            'translated': translated_text
        }, room=sid)
        # After processing, signal that the server is ready for more.
        socketio.emit('status_update', {'status': 'Ready for next input.'}, room=sid)

    except sr.UnknownValueError:
        print(f"[{sid}] Could not understand audio. It might be music or silence.")
        socketio.emit('status_update', {'status': 'Could not understand audio. Please try again.'}, room=sid)
    except sr.RequestError as e:
        print(f"[{sid}] Could not request results from Google Speech Recognition service; {e}")
        socketio.emit('status_update', {'status': f"API Error: {e}"}, room=sid)
    except Exception as e:
        print(f"[{sid}] An unexpected error occurred during recognition: {e}")
        socketio.emit('status_update', {'status': f"An unexpected error occurred: {e}"}, room=sid)


@socketio.on('connect')
def handle_connect():
    sid = request.sid
    print(f"Client connected: {sid}")
    # Initialize state for the new client
    client_states[sid] = {
        'running': False, # This can be repurposed to track recording state on client
        'language': 'hi-IN', # Default language
        'history': [] # Add history for each client
    }
    emit('status_update', {'status': 'Connected and ready.'})

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f"Client disconnected: {sid}")
    # Clean up the client state
    if sid in client_states:
        del client_states[sid]

# Removed handle_start_translation, handle_stop_translation, and listen_and_translate
# The client will now control the recording and send a complete audio chunk.

@socketio.on('set_language')
def handle_set_language(data):
    sid = request.sid
    language = data.get('language')
    if language:
        client_states[sid]['language'] = language
        print(f"[{sid}] Language set to: {language}")
        emit('status_update', {'status': f"Language set to {LANG_MAP.get(language, language)}"})

if __name__ == '__main__':
    print("Starting Flask-SocketIO server...")
    socketio.run(app, debug=True, port=5001)
