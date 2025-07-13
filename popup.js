const socket = io("http://127.0.0.1:5000");

const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
const statusText = document.getElementById("status-text");
const statusIndicator = document.getElementById("status-indicator");
const historyDiv = document.getElementById("history");
const downloadBtn = document.getElementById("download-btn");
const languageSelect = document.getElementById("language-select");


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


startBtn.addEventListener("click", () => {
    console.log("Start button clicked");
    socket.emit("start_translation");
    startBtn.style.display = "none";
    stopBtn.style.display = "inline-block";
    downloadBtn.style.display = "none"; // Hide until stopped
    historyDiv.innerHTML = ""; // Clear history on start
    updateStatus("Listening...", true);
});

stopBtn.addEventListener("click", () => {
    console.log("Stop button clicked");
    socket.emit("stop_translation");
    stopBtn.style.display = "none";
    startBtn.style.display = "inline-block";
    downloadBtn.style.display = "block"; // Show download button
    updateStatus("Ready", false);
});

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


socket.on("connect", () => {
    console.log("Connected to server");
    updateStatus("Ready", false);
});

socket.on("disconnect", () => {
    console.log("Disconnected from server");
    updateStatus("Disconnected", false);
});

socket.on('translation_update', (data) => {
    console.log("Received translation:", data);
    
    // Create a new entry in the history
    const entryDiv = document.createElement('div');
    entryDiv.className = 'history-entry';

    const originalP = document.createElement('p');
    originalP.innerHTML = `<strong>Original:</strong> <span class="original">${data.original}</span>`;
    
    const translatedP = document.createElement('p');
    translatedP.innerHTML = `<strong>Translation:</strong> <span class="translated">${data.translated}</span>`;

    entryDiv.appendChild(originalP);
    entryDiv.appendChild(translatedP);

    historyDiv.appendChild(entryDiv);
    historyDiv.scrollTop = historyDiv.scrollHeight; // Auto-scroll
});


socket.on("status_update", (data) => {
    console.log("Received status update:", data.status);
    const isListening = data.status === "Listening...";
    updateStatus(data.status, isListening);
});

function updateStatus(text, isListening) {
    statusText.textContent = text;
    if (isListening) {
        statusIndicator.classList.add("listening");
    } else {
        statusIndicator.classList.remove("listening");
    }
}
