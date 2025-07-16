// Connect to the Socket.IO server
const socket = io("http://127.0.0.1:5001");

// UI Elements
const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
const statusText = document.getElementById("status-text");
const statusIndicator = document.getElementById("status-indicator");
const historyDiv = document.getElementById("history");
const downloadBtn = document.getElementById("download-btn");
const languageSelect = document.getElementById("language-select");

// Audio recording state and variables
let audioContext;
let mediaStream;
let workletNode;
let isRecording = false;
const bufferSize = 4096; // This is not directly used by AudioWorklet in the same way, but good for reference
let audioBuffer = [];

// Populate language dropdown
const languages = {
    "en-US": "English",
    "hi-IN": "Hindi",
    "pa-IN": "Punjabi",
    "fr-FR": "French",
    "es-ES": "Spanish",
    "de-DE": "German"
};

for (const code in languages) {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = languages[code];
    if (code === "hi-IN") {
        option.selected = true;
    }
    languageSelect.appendChild(option);
}

// --- Core Audio Functions ---

async function startRecording() {
    if (isRecording) return;
    console.log("Starting recording...");
    updateStatus("Requesting mic...", true);
    audioBuffer = []; // Clear buffer at the start

    try {
        // 1. Get audio stream from the microphone
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        // 2. Create and configure the AudioContext
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        
        // 3. Add the AudioWorklet module
        try {
            await audioContext.audioWorklet.addModule('audio-processor.js');
        } catch (e) {
            console.error('Error adding audio worklet module', e);
            updateStatus("Error setting up audio processor.", false);
            return;
        }

        // 4. Create an AudioWorkletNode
        workletNode = new AudioWorkletNode(audioContext, 'audio-processor');

        // 5. Set up the message handler from the worklet
        workletNode.port.onmessage = (event) => {
            // The event.data is the ArrayBuffer from the worklet
            audioBuffer.push(new Float32Array(event.data));
        };

        // 6. Connect the microphone source to the worklet
        const source = audioContext.createMediaStreamSource(mediaStream);
        source.connect(workletNode);
        // It's good practice to connect the worklet to the destination
        // if you want to hear the audio, but for pure processing, it's not required.
        // We are not playing it back, so we can skip this.
        // workletNode.connect(audioContext.destination);
        
        isRecording = true;
        startBtn.style.display = "none";
        stopBtn.style.display = "inline-block";
        downloadBtn.style.display = "none";
        historyDiv.innerHTML = ""; // Clear history
        updateStatus("Listening...", true);

    } catch (err) {
        console.error("Error accessing microphone:", err.name, err.message);
        let errorMessage = `Mic error: ${err.name}`;
        if (err.name === 'NotAllowedError') {
            errorMessage = "Permission to use microphone was denied. Please allow access in browser settings.";
        } else if (err.name === 'NotFoundError') {
            errorMessage = "No microphone was found. Please ensure one is connected.";
        }
        updateStatus(errorMessage, false);
        isRecording = false;
    }
}

function stopRecording() {
    if (!isRecording) return;
    console.log("Stopping recording...");
    isRecording = false;

    // Stop the microphone track
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
    }
    
    // Disconnect the audio graph
    if (workletNode) {
        workletNode.port.onmessage = null; // Clean up the event listener
        workletNode.disconnect();
    }

    // Close the audio context
    if (audioContext) {
        audioContext.close().then(() => {
            console.log("AudioContext closed.");
            // Processing is now done after the context is confirmed closed
            updateStatus("Processing...", true);
            processAndSendAudio();
        });
    } else {
        // Fallback if audioContext wasn't created
        updateStatus("Processing...", true);
        processAndSendAudio();
    }


    stopBtn.style.display = "none";
    startBtn.style.display = "inline-block";
    downloadBtn.style.display = "block";
}

function processAndSendAudio() {
    if (audioBuffer.length === 0) {
        updateStatus("No audio recorded.", false);
        return;
    }

    // 1. Concatenate all buffered chunks
    const totalLength = audioBuffer.reduce((acc, val) => acc + val.length, 0);
    const concatenatedBuffer = new Float32Array(totalLength);
    let offset = 0;
    for (const buffer of audioBuffer) {
        concatenatedBuffer.set(buffer, offset);
        offset += buffer.length;
    }

    // 2. Convert Float32 to 16-bit PCM
    const pcmBuffer = new Int16Array(concatenatedBuffer.length);
    for (let i = 0; i < concatenatedBuffer.length; i++) {
        let s = Math.max(-1, Math.min(1, concatenatedBuffer[i]));
        pcmBuffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // 3. Send the raw PCM data (as a byte buffer) to the server
    const selectedLanguage = languageSelect.value;
    socket.emit('process_audio', {
        audio: pcmBuffer.buffer,
        sample_rate: audioContext.sampleRate,
        sample_width: 2, // 16-bit
        language: selectedLanguage
    });

    // 4. Clear the buffer for the next recording
    audioBuffer = [];
}


// --- UI Event Listeners ---

startBtn.addEventListener("click", startRecording);
stopBtn.addEventListener("click", stopRecording);

downloadBtn.addEventListener("click", () => {
    let transcript = "Live Translation Transcript\n";
    transcript += "============================\n\n";
    const entries = historyDiv.getElementsByClassName("history-entry");
    for (const entry of entries) {
        const original = entry.querySelector(".original").textContent;
        const translated = entry.querySelector(".translated").textContent;
        transcript += `Original: ${original}\n`;
        transcript += `Translated: ${translated}\n\n`;
    }

    const blob = new Blob([transcript], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "transcript.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

languageSelect.addEventListener("change", () => {
    const selectedLanguage = languageSelect.value;
    console.log(`Language changed to: ${selectedLanguage}`);
    socket.emit("set_language", { language: selectedLanguage });
});

// --- Socket.IO Event Handlers ---

socket.on("connect", () => {
    console.log("Connected to server");
    updateStatus("Ready", false);
});

socket.on("disconnect", () => {
    console.log("Disconnected from server");
    updateStatus("Disconnected", false);
    if (isRecording) {
        stopRecording();
    }
});

socket.on('translation_update', (data) => {
    console.log("Received translation:", data);
    
    const entryDiv = document.createElement('div');
    entryDiv.className = 'history-entry';

    const originalP = document.createElement('p');
    originalP.innerHTML = `<strong>Original:</strong> <span class="original">${data.original}</span>`;
    
    const translatedP = document.createElement('p');
    translatedP.innerHTML = `<strong>Translated:</strong> <span class="translated">${data.translated}</span>`;

    entryDiv.appendChild(originalP);
    entryDiv.appendChild(translatedP);
    historyDiv.appendChild(entryDiv);
    historyDiv.scrollTop = historyDiv.scrollHeight; // Auto-scroll

    updateStatus("Ready", false); // Ready for next input
});

socket.on('status_update', (data) => {
    console.log("Status update:", data.status);
    // Only update status if not currently recording, to avoid overwriting "Listening..."
    if (!isRecording) {
        updateStatus(data.status, false);
    }
});

// --- Utility Functions ---

function updateStatus(text, isProcessing) {
    statusText.textContent = text;
    if (isProcessing) {
        statusIndicator.classList.add("processing");
    } else {
        statusIndicator.classList.remove("processing");
    }
}
