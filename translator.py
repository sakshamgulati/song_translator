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
import threading
from flask_cors import CORS

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


def listen_and_translate(sid):
    """
    Listens for audio, transcribes it, and sends translations to the client.
    This function runs in a background thread for a specific client.
    """
    r = sr.Recognizer()
    # How many seconds of non-speaking audio before a phrase is considered complete.
    # This is the key to capturing complete sentences.
    r.pause_threshold = 2.0 
    # You can also adjust this if the recognizer is too sensitive to background noise
    # r.energy_threshold = 4000 
    mic = sr.Microphone()
    
    client_states[sid]['running'] = True
    print(f"[{sid}] Starting translation thread.")
    
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=1) # Adjust for ambient noise once
        
    while client_states.get(sid, {}).get('running', False):
        socketio.emit('status_update', {'status': 'Listening...'}, room=sid)
        print(f"[{sid}] Listening for a sentence...")
        try:
            with mic as source:
                # Listen for a full phrase, determined by the pause_threshold
                audio = r.listen(source)
            
            # Let the user know we are processing
            socketio.emit('status_update', {'status': 'Processing...'}, room=sid)
            print(f"[{sid}] Processing audio...")

            source_language = client_states.get(sid, {}).get('language', 'hi-IN')
            
            # Recognize speech using Google Web Speech API
            try:
                original_text = r.recognize_google(audio, language=source_language)
                print(f"[{sid}] Original: {original_text}")

                # Translate the recognized text
                translated_text = translate_text(original_text, sid)
                print(f"[{sid}] Translated: {translated_text}")

                # Send the final update to the specific client
                socketio.emit('translation_update', {
                    'original': original_text,
                    'translated': translated_text
                }, room=sid)

            except sr.UnknownValueError:
                # This is the key change: if we can't understand the audio (e.g., it's just music),
                # we don't treat it as an error. We just silently ignore it and continue listening.
                print(f"[{sid}] Could not understand audio or it was just music. Continuing...")
                continue # Go back to the start of the loop
            except sr.RequestError as e:
                print(f"[{sid}] Could not request results; {e}")
                socketio.emit('status_update', {'status': f"API Error: {e}"}, room=sid)

        except Exception as e:
            print(f"An error occurred in the listening loop: {e}")
            break
            
    print(f"[{sid}] Translation thread stopped.")


@socketio.on('connect')
def handle_connect():
    sid = request.sid
    print(f"Client connected: {sid}")
    # Initialize state for the new client
    client_states[sid] = {
        'running': False,
        'language': 'hi-IN', # Default language
        'thread': None,
        'history': [] # Add history for each client
    }
    emit('status_update', {'status': 'Connected and ready.'})

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f"Client disconnected: {sid}")
    # Stop the translation thread if it's running
    if client_states.get(sid, {}).get('running'):
        client_states[sid]['running'] = False
        if client_states[sid]['thread']:
            client_states[sid]['thread'].join() # Wait for the thread to finish
    # Clean up the client state
    if sid in client_states:
        del client_states[sid]

@socketio.on('start_translation')
def handle_start_translation():
    sid = request.sid
    if not client_states.get(sid, {}).get('running'):
        # Start the translation process in a background thread
        client_states[sid]['history'] = [] # Clear history on start
        thread = threading.Thread(target=listen_and_translate, args=(sid,))
        client_states[sid]['thread'] = thread
        thread.start()
        emit('status_update', {'status': 'Translation started.'})
    else:
        emit('status_update', {'status': 'Translation is already running.'})


@socketio.on('stop_translation')
def handle_stop_translation():
    sid = request.sid
    if client_states.get(sid, {}).get('running'):
        client_states[sid]['running'] = False
        if client_states[sid]['thread']:
            client_states[sid]['thread'].join() # Ensure the thread has stopped
            client_states[sid]['thread'] = None
        emit('status_update', {'status': 'Translation stopped. Ready.'})
    else:
        emit('status_update', {'status': 'Translation is not running.'})


@socketio.on('set_language')
def handle_set_language(data):
    sid = request.sid
    language = data.get('language')
    if language:
        client_states[sid]['language'] = language
        print(f"[{sid}] Language set to: {language}")
        emit('status_update', {'status': f"Language set to {LANG_MAP.get(language, language)}"})

# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Flask server...")
    # app.run(debug=True, use_reloader=False)
    socketio.run(app, debug=True, use_reloader=False)
