class AudioProcessor extends AudioWorkletProcessor {
  process(inputs, outputs, parameters) {
    // We only need to send the audio data from the first input and first channel.
    const audioData = inputs[0][0];
    if (audioData) {
      // Post the raw audio data (Float32Array) back to the main thread.
      // The second argument is a list of transferable objects to avoid copying.
      this.port.postMessage(audioData.buffer, [audioData.buffer]);
    }
    return true; // Keep the processor alive.
  }
}

registerProcessor('audio-processor', AudioProcessor);
