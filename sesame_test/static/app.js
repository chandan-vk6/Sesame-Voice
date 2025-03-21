// SesameAI Voice Chat Web Client

// DOM Elements
const connectButton = document.getElementById('connect-btn');
const disconnectButton = document.getElementById('disconnect-btn');
const connectSpinner = document.getElementById('connect-spinner');
const characterSelect = document.getElementById('character-select');
const statusLight = document.getElementById('status-light');
const statusText = document.getElementById('status-text');
const logContainer = document.getElementById('log-container');
const clearLogButton = document.getElementById('clear-log-btn');
const debugButton = document.getElementById('debug-btn');
const resetAudioButton = document.getElementById('reset-audio-btn');
const autoDisconnectSwitch = document.getElementById('auto-disconnect');
const inputVisualizer = document.getElementById('input-visualizer');
const outputVisualizer = document.getElementById('output-visualizer');

// Audio Context and Processing Variables

let microphoneStream;
let micScriptProcessor;
let speakerScriptProcessor;
let wsConnection;
let isConnected = false;
let serverSampleRate = 24000; // Default, will be updated from server
let inputSampleRate = 16000;
let inputAnalyser;
let outputAnalyser;
let inputVisualizerBars = [];
let outputVisualizerBars = [];
let silenceDetector = null;

// Create audio visualizer bars
function initializeVisualizers() {
    const inputBarCount = 64;
    const outputBarCount = 64;
    
    // Clear existing bars
    inputVisualizer.innerHTML = '';
    outputVisualizer.innerHTML = '';
    inputVisualizerBars = [];
    outputVisualizerBars = [];
    
    // Create input visualizer bars
    for (let i = 0; i < inputBarCount; i++) {
        const bar = document.createElement('div');
        bar.className = 'visualizer-bar';
        bar.style.left = `${(i / inputBarCount) * 100}%`;
        bar.style.height = '0px';
        inputVisualizer.appendChild(bar);
        inputVisualizerBars.push(bar);
    }
    
    // Create output visualizer bars
    for (let i = 0; i < outputBarCount; i++) {
        const bar = document.createElement('div');
        bar.className = 'visualizer-bar';
        bar.style.left = `${(i / outputBarCount) * 100}%`;
        bar.style.height = '0px';
        outputVisualizer.appendChild(bar);
        outputVisualizerBars.push(bar);
    }
}

// Update visualizers
function updateVisualizers() {
    if (!audioContext || !isConnected) return;
    
    // Update input visualizer
    if (inputAnalyser) {
        const inputFrequencyData = new Uint8Array(inputAnalyser.frequencyBinCount);
        inputAnalyser.getByteFrequencyData(inputFrequencyData);
        
        // Map frequency data to visualizer bars
        const barWidth = Math.ceil(inputFrequencyData.length / inputVisualizerBars.length);
        for (let i = 0; i < inputVisualizerBars.length; i++) {
            let sum = 0;
            for (let j = 0; j < barWidth; j++) {
                const index = i * barWidth + j;
                if (index < inputFrequencyData.length) {
                    sum += inputFrequencyData[index];
                }
            }
            const average = sum / barWidth;
            const height = (average / 255) * 30; // Max height 30px
            inputVisualizerBars[i].style.height = `${height}px`;
        }
    }
    
    // Update output visualizer
    if (outputAnalyser) {
        const outputFrequencyData = new Uint8Array(outputAnalyser.frequencyBinCount);
        outputAnalyser.getByteFrequencyData(outputFrequencyData);
        
        // Map frequency data to visualizer bars
        const barWidth = Math.ceil(outputFrequencyData.length / outputVisualizerBars.length);
        for (let i = 0; i < outputVisualizerBars.length; i++) {
            let sum = 0;
            for (let j = 0; j < barWidth; j++) {
                const index = i * barWidth + j;
                if (index < outputFrequencyData.length) {
                    sum += outputFrequencyData[index];
                }
            }
            const average = sum / barWidth;
            const height = (average / 255) * 30; // Max height 30px
            outputVisualizerBars[i].style.height = `${height}px`;
        }
    }
    
    // Schedule next update
    requestAnimationFrame(updateVisualizers);
}

// Add log entry
function addLogEntry(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.textContent = message;
    logContainer.appendChild(entry);
    logContainer.scrollTop = logContainer.scrollHeight;
}

// Clear log
function clearLog() {
    logContainer.innerHTML = '';
    addLogEntry('System: Log cleared', 'system');
}

// Set connection status
function setConnectionStatus(connected, character = null) {
    isConnected = connected;
    
    if (connected) {
        statusLight.classList.add('connected');
        statusText.textContent = `Connected to ${character}`;
        connectButton.disabled = true;
        disconnectButton.disabled = false;
        characterSelect.disabled = true;
        connectSpinner.classList.add('d-none'); // Hide spinner
    } else {
        statusLight.classList.remove('connected');
        statusText.textContent = 'Disconnected';
        connectButton.disabled = false;
        disconnectButton.disabled = true;
        characterSelect.disabled = false;
        connectSpinner.classList.add('d-none'); // Hide spinner
    }
}



// Modified audio handling based on the Python library's approach
// This simulates the PyAudio direct streaming approach used in the Python version

// Audio settings to match the Python implementation
const CHUNK_SIZE = 1024; // Matches the Python library's chunk size
const INPUT_SAMPLE_RATE = 16000; // Fixed rate as in Python lib
const OUTPUT_SAMPLE_RATE = 24000; // Will be updated from server
const CHANNELS = 1;
const AMPLITUDE_THRESHOLD = 500; // For voice activity detection

// Audio Context and Processing Variables
let audioContext;
// let microphoneStream;
let inputProcessor;
let outputProcessor;
// let wsConnection;
// let isConnected = false;
// let serverSampleRate = OUTPUT_SAMPLE_RATE; // Will be updated from server

// Direct, simple audio buffering (similar to Python implementation)
let audioOutputQueue = [];
let isAudioPlaying = false;
let silenceCounter = 0;
let silenceLimit = 50; // Number of consecutive silent chunks before sending silence

// Connect to server with simplified PyAudio-like approach
async function connect() {
    try {
        const selectedCharacter = characterSelect.value;
        
        // Check browser support
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            addLogEntry('Error: Your browser does not support audio input', 'error');
            return;
        }
        
        addLogEntry(`System: Connecting to ${selectedCharacter}...`, 'system');
        
        // Initialize audio context with exact sample rate matching Python implementation
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: INPUT_SAMPLE_RATE // Force 16kHz to match Python lib
        });
        
        // Get microphone access with constraints matching Python implementation
        microphoneStream = await navigator.mediaDevices.getUserMedia({ 
            audio: { 
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                channelCount: CHANNELS,
                sampleRate: INPUT_SAMPLE_RATE, // Match Python lib
                latency: 0.01
            } 
        });
        
        // Connect to WebSocket server
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/audio/${selectedCharacter}`;
        wsConnection = new WebSocket(wsUrl);
        
        // WebSocket event handlers
        wsConnection.onopen = () => {
            addLogEntry('System: WebSocket connection established', 'system');
        };
        
        wsConnection.onmessage = async (event) => {
            if (event.data instanceof Blob) {
                handleAudioFromServer(event.data);
            } else {
                try {
                    const message = JSON.parse(event.data);
                    
                    if (message.status === 'connected') {
                        // Update server sample rate
                        serverSampleRate = message.sampleRate || OUTPUT_SAMPLE_RATE;
                        addLogEntry(`System: Connected to ${message.character}`, 'system');
                        setConnectionStatus(true, message.character);
                        setupPyAudioLikeProcessing();
                    } else if (message.error) {
                        addLogEntry(`Error: ${message.error}`, 'error');
                        disconnectFromServer();
                    }
                } catch (e) {
                    addLogEntry(`Error parsing message: ${e.message}`, 'error');
                }
            }
        };
        
        wsConnection.onerror = (error) => {
            addLogEntry(`WebSocket error: ${error.message || 'Unknown error'}`, 'error');
            disconnectFromServer();
        };
        
        wsConnection.onclose = () => {
            addLogEntry('System: WebSocket connection closed', 'system');
            disconnectFromServer();
        };
        
    } catch (error) {
        addLogEntry(`Error: ${error.message}`, 'error');
        disconnectFromServer();
    }
}

// Set up audio processing to mimic PyAudio direct streaming approach
function setupPyAudioLikeProcessing() {
    // Create simple direct input processing
    const micSource = audioContext.createMediaStreamSource(microphoneStream);
    
    // Initialize visualizers
    initializeVisualizers();
    
    // Create input analyzer for visualization only
    inputAnalyser = audioContext.createAnalyser();
    inputAnalyser.fftSize = 1024;
    inputAnalyser.smoothingTimeConstant = 0.3;
    micSource.connect(inputAnalyser);
    
    // Create output analyzer
    outputAnalyser = audioContext.createAnalyser();
    outputAnalyser.fftSize = 1024;
    outputAnalyser.smoothingTimeConstant = 0.3;
    
    // Create ScriptProcessor for microphone input - using exact CHUNK_SIZE from Python
    inputProcessor = audioContext.createScriptProcessor(CHUNK_SIZE, CHANNELS, CHANNELS);
    micSource.connect(inputProcessor);
    inputProcessor.connect(audioContext.destination);
    
    // Handler for microphone audio - simplified like Python version
    inputProcessor.onaudioprocess = (e) => {
        if (!isConnected || !wsConnection || wsConnection.readyState !== WebSocket.OPEN) {
            return;
        }
        
        const inputBuffer = e.inputBuffer.getChannelData(0);
        
        // Calculate RMS like in Python version
        let sumSquares = 0;
        for (let i = 0; i < inputBuffer.length; i++) {
            sumSquares += inputBuffer[i] * inputBuffer[i];
        }
        const rms = Math.sqrt(sumSquares / inputBuffer.length);
        
        // Convert float to 16-bit integer values (similar to Python's int16)
        const int16Data = new Int16Array(inputBuffer.length);
        for (let i = 0; i < inputBuffer.length; i++) {
            // Convert float [-1,1] to int16 [-32768,32767]
            int16Data[i] = Math.max(-32767, Math.min(32767, Math.round(inputBuffer[i] * 32767)));
        }
        
        // Simple voice activity detection like in Python version
        // RMS * 32767 to get same scale as Python version
        const scaledRMS = rms * 32767;
        
        if (scaledRMS > AMPLITUDE_THRESHOLD) {
            // Voice detected - reset silence counter
            silenceCounter = 0;
            wsConnection.send(int16Data.buffer);
        } else {
            // Silence detected
            silenceCounter++;
            if (silenceCounter >= silenceLimit) {
                // Send completely silent audio after silence threshold
                const silentData = new Int16Array(CHUNK_SIZE).fill(0);
                wsConnection.send(silentData.buffer);
            } else {
                // Continue sending actual audio during brief pauses (matches Python behavior)
                wsConnection.send(int16Data.buffer);
            }
        }
    };
    
    // Direct output processor for audio playback - simpler like Python version
    outputProcessor = audioContext.createScriptProcessor(CHUNK_SIZE, CHANNELS, CHANNELS);
    outputProcessor.connect(audioContext.destination);
    outputProcessor.connect(outputAnalyser);
    
    // Start direct audio playback system
    startDirectAudioPlayback();
    
    // Start visualizer updates
    updateVisualizers();
    
    addLogEntry('System: Audio processing initialized - PyAudio style', 'system');
    addLogEntry('System: Speak into your microphone to begin chatting', 'system');
}

// Simple, direct audio handling from server - mimicking Python version
async function handleAudioFromServer(blob) {
    if (!audioContext || !isConnected) return;
    
    try {
        // Convert blob to ArrayBuffer
        const arrayBuffer = await blob.arrayBuffer();
        
        // Skip empty chunks
        if (arrayBuffer.byteLength === 0) return;
        
        // Add to queue for immediate playback (like Python version)
        audioOutputQueue.push(arrayBuffer);
        
        // Start playback if not already playing
        if (!isAudioPlaying) {
            playNextAudioChunk();
        }
        
    } catch (error) {
        console.error('Error processing audio from server:', error);
    }
}

// Direct audio playback system like in Python version
function playNextAudioChunk() {
    if (audioOutputQueue.length === 0) {
        isAudioPlaying = false;
        return;
    }
    
    isAudioPlaying = true;
    
    // Get next chunk from queue
    const audioData = audioOutputQueue.shift();
    
    // Convert to Int16Array (same as Python)
    const int16Data = new Int16Array(audioData);
    
    // Create audio buffer with server sample rate
    const audioBuffer = audioContext.createBuffer(CHANNELS, int16Data.length, serverSampleRate);
    
    // Convert Int16 to Float32 (normalized -1 to 1)
    const channelData = audioBuffer.getChannelData(0);
    for (let i = 0; i < int16Data.length; i++) {
        channelData[i] = int16Data[i] / 32767.0;
    }
    
    // Create source for playback
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    
    // Simple direct connection like in Python version - minimal processing
    source.connect(audioContext.destination);
    
    // Also connect to analyzer for visualization
    source.connect(outputAnalyser);
    
    // Start playback immediately (direct like Python)
    source.start();
    
    // When this chunk finishes, play the next one
    source.onended = playNextAudioChunk;
}

// Start direct audio playback system
function startDirectAudioPlayback() {
    // Initialize audio output state
    isAudioPlaying = false;
    audioOutputQueue = [];
    
    // Create a dummy silent buffer to "wake up" the audio context
    // This helps avoid first-chunk playback issues
    const silentBuffer = audioContext.createBuffer(CHANNELS, CHUNK_SIZE, serverSampleRate);
    const source = audioContext.createBufferSource();
    source.buffer = silentBuffer;
    source.connect(audioContext.destination);
    source.start();
    
    addLogEntry('System: Audio playback system initialized', 'system');
}

// Simple disconnect that matches Python behavior
function disconnectFromServer() {
    // Stop audio playback
    isAudioPlaying = false;
    audioOutputQueue = [];
    
    // Close WebSocket
    if (wsConnection) {
        if (wsConnection.readyState === WebSocket.OPEN) {
            wsConnection.close();
        }
        wsConnection = null;
    }
    
    // Stop microphone stream
    if (microphoneStream) {
        microphoneStream.getTracks().forEach(track => track.stop());
        microphoneStream = null;
    }
    
    // Clean up audio processors
    if (inputProcessor) {
        inputProcessor.disconnect();
        inputProcessor = null;
    }
    
    if (outputProcessor) {
        outputProcessor.disconnect();
        outputProcessor = null;
    }
    
    // Reset connection status
    setConnectionStatus(false);
    
    addLogEntry('System: Disconnected and all audio processing stopped', 'system');
}
// Event Listeners
connectButton.addEventListener('click', async () => {
    // Show spinner
    connectSpinner.classList.remove('d-none');
    
    // Ensure audio context is resumed (needed for browsers with autoplay restrictions)
    if (audioContext && audioContext.state === 'suspended') {
        try {
            await audioContext.resume();
            addLogEntry('System: Audio context resumed', 'system');
        } catch (e) {
            console.error("Error resuming audio context:", e);
        }
    }
    
    // Initiate connection
    connect().catch(error => {
        console.error("Connection error:", error);
        connectSpinner.classList.add('d-none');
    });
});

disconnectButton.addEventListener('click', () => {
    addLogEntry('System: Disconnecting...', 'system');
    disconnectFromServer();
});

clearLogButton.addEventListener('click', clearLog);

// Add click listener to entire document to help with audio autoplay restrictions
document.addEventListener('click', async () => {
    if (audioContext && audioContext.state === 'suspended') {
        await audioContext.resume();
        addLogEntry('System: Audio context resumed after user interaction', 'system');
    }
});

// Debug button - test audio playback
debugButton.addEventListener('click', async () => {
    try {
        // Create an audio context if it doesn't exist
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            addLogEntry('System: Created new AudioContext for testing', 'system');
        }
        
        // Resume the audio context if suspended
        if (audioContext.state === 'suspended') {
            await audioContext.resume();
            addLogEntry('System: Audio context resumed', 'system');
        }
        
        // Create a simple beep sound
        const oscillator = audioContext.createOscillator();
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(440, audioContext.currentTime); // A4 note
        
        const gainNode = audioContext.createGain();
        gainNode.gain.setValueAtTime(0.2, audioContext.currentTime); // 20% volume
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        // Play for 0.5 seconds
        oscillator.start();
        oscillator.stop(audioContext.currentTime + 0.5);
        
        addLogEntry('System: Test sound played - If you heard a beep, audio output is working!', 'system');
    } catch (error) {
        addLogEntry(`Error: Failed to play test sound: ${error.message}`, 'error');
    }
});

// Reset Audio button - completely reset the audio system
resetAudioButton.addEventListener('click', async () => {
    try {
        // First disconnect if connected
        if (isConnected) {
            disconnectFromServer();
        }
        
        // Clear all logs
        clearLog();
        
        // Close and recreate audio context
        if (audioContext) {
            // Close old audio context
            if (audioContext.state !== 'closed') {
                try {
                    await audioContext.close();
                } catch (e) {
                    console.error('Error closing AudioContext:', e);
                }
            }
            audioContext = null;
        }
        
        // Create a fresh audio context for testing
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            latencyHint: 'interactive',
            sampleRate: 48000  // Higher sample rate for better quality
        });
        
        // Play a test sound
        const oscillator = audioContext.createOscillator();
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(880, audioContext.currentTime); // A5 note
        
        const gainNode = audioContext.createGain();
        gainNode.gain.setValueAtTime(0.2, audioContext.currentTime); // 20% volume
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        // Play for 0.5 seconds
        oscillator.start();
        oscillator.stop(audioContext.currentTime + 0.3);
        
        // Reset all state variables
        chunkDuplicateMap.clear();
        audioBufferQueue = [];
        isAudioPlaying = false;
        lastPlaybackTime = 0;
        window.firstAudioPlayed = false;
        
        // Initialize visualizers
        initializeVisualizers();
        
        addLogEntry('System: Audio system completely reset. Ready to reconnect.', 'system');
        
        // Wait for the tone to finish before showing ready message
        setTimeout(() => {
            addLogEntry('System: Click "Connect" to start a new conversation with fresh audio settings.', 'system');
        }, 500);
        
    } catch (error) {
        addLogEntry(`Error: Failed to reset audio system: ${error.message}`, 'error');
    }
});

// Initialize
initializeVisualizers();
addLogEntry('System: SesameAI Voice Chat Web Client initialized', 'system');