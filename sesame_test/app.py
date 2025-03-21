# app.py
import os
import json
import asyncio
import logging
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import time
import numpy as np

# Import SesameAI client modules
from sesame_ai import SesameAI, SesameWebSocket, TokenManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("sesame_web")

# Initialize FastAPI app
app = FastAPI(title="SesameAI Web Client")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Active client connections
active_connections = {}

# Create SesameAI client
sesame_client = SesameAI()
token_manager = TokenManager(sesame_client, token_file="token.json")

class AudioStreamManager:
    """Manages bidirectional audio streaming between browser and SesameAI"""
    
    def __init__(self, client_websocket, character="Miles"):
        self.client_websocket = client_websocket
        self.character = character
        self.client_id = id(client_websocket)
        self.sesame_ws = None
        self.running = False
        self.tasks = []
        
        # Audio buffering for smoother transmission
        self.audio_buffer_to_sesame = []
        self.buffer_size_limit = 5  # Maximum number of chunks to buffer
        
        # Audio chunk size threshold for sending to SesameAI
        # Sending larger chunks can improve the AI's ability to process speech
        self.min_chunk_size = 8192    # Minimum bytes before sending to SesameAI
    
    async def initialize(self):
        """Initialize connection to SesameAI with improved reliability and token handling"""
        try:
            # Force a new token creation on each connection attempt
            # This solves the 401 Unauthorized issues
            id_token = token_manager.get_valid_token(force_new=True)
            
            # Log token creation
            logger.info(f"Created new auth token for {self.character} connection")
            
            # Create SesameAI WebSocket client
            self.sesame_ws = SesameWebSocket(
                id_token=id_token,
                character=self.character
            )
            
            # Connect (non-blocking)
            logger.info(f"Attempting to connect to SesameAI as {self.character}")
            connected = self.sesame_ws.connect(blocking=False)
            
            # Wait for connection to be established with longer timeout
            for attempt in range(20):  # Wait up to 2 seconds
                if self.sesame_ws.is_connected():
                    logger.info(f"Connected to SesameAI as {self.character}")
                    return True
                await asyncio.sleep(0.1)
                if attempt % 5 == 0:
                    logger.debug(f"Waiting for connection to SesameAI... attempt {attempt+1}")
            
            # If still not connected, check for specific issues
            if not self.sesame_ws.is_connected():
                # Try to get connection status info
                if hasattr(self.sesame_ws, 'session_id') and self.sesame_ws.session_id:
                    logger.warning(f"Partial connection to SesameAI: Got session_id but no call_id")
                else:
                    logger.error("Failed to connect to SesameAI: No session established")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error initializing SesameAI connection: {e}", exc_info=True)
            return False
    
    async def start_streaming(self):
        """Start bidirectional audio streaming between client and SesameAI"""
        self.running = True
        
        # Create tasks for browser → SesameAI and SesameAI → browser
        browser_to_sesame_task = asyncio.create_task(self.stream_browser_to_sesame())
        sesame_to_browser_task = asyncio.create_task(self.stream_sesame_to_browser())
        
        self.tasks = [browser_to_sesame_task, sesame_to_browser_task]
        
        logger.info(f"Started audio streaming for client {self.client_id}")
    
    async def stream_browser_to_sesame(self):
        """Stream audio from browser to SesameAI"""
        try:
            while self.running:
                # Receive binary audio data from browser
                audio_data = await self.client_websocket.receive_bytes()
                
                # Send to SesameAI
                if self.sesame_ws and self.sesame_ws.is_connected():
                    self.sesame_ws.send_audio_data(audio_data)
        except Exception as e:
            if self.running:
                logger.error(f"Error in browser→SesameAI stream: {e}")
            self.running = False
    
    async def stream_sesame_to_browser(self):
        """Stream audio from SesameAI to browser with improved chunk processing"""
        try:
            audio_received_count = 0
            consecutive_empty_chunks = 0
            
            # Track recently seen chunks to avoid duplicates
            recently_seen = set()
            max_recent = 20
            
            # Enhanced audio buffer for smoother delivery
            audio_buffer = []
            max_buffer_size = 5  # Store more chunks for analysis
            min_buffer_size = 3  # Minimum chunks before processing
            last_send_time = 0
            min_send_interval = 0.02  # 20ms intervals for smoother playback
            
            # For detecting and eliminating click/pop sounds
            prev_chunk_end = None  # To track the end of the previous chunk
            
            while self.running and self.sesame_ws and self.sesame_ws.is_connected():
                # Non-blocking check for audio from SesameAI
                audio_chunk = self.sesame_ws.get_next_audio_chunk(timeout=0.01)
                
                # If we got audio, process it
                if audio_chunk and self.running:
                    # Skip empty or tiny chunks
                    if len(audio_chunk) < 10:
                        consecutive_empty_chunks += 1
                        if consecutive_empty_chunks > 50:
                            await asyncio.sleep(0.1)
                        continue
                    
                    consecutive_empty_chunks = 0
                    
                    # Improved deduplication
                    if len(audio_chunk) > 40:
                        chunk_hash = hash(audio_chunk[:20] + audio_chunk[-20:])
                    else:
                        chunk_hash = hash(audio_chunk)
                    
                    if chunk_hash in recently_seen:
                        logger.debug(f"Detected duplicate audio chunk, skipping")
                        continue
                    
                    # Add to recently seen set and manage its size
                    recently_seen.add(chunk_hash)
                    if len(recently_seen) > max_recent:
                        recently_seen.pop() if recently_seen else None
                    
                    # Process the audio chunk to prevent clicks/pops
                    processed_chunk = self._process_audio_chunk(audio_chunk, prev_chunk_end)
                    
                    # Update the previous chunk end for next time
                    if len(audio_chunk) >= 4:
                        # Keep the last few samples to check continuity
                        prev_chunk_end = audio_chunk[-4:]
                    
                    # Add to buffer for analysis and delivery
                    audio_buffer.append(processed_chunk)
                    
                    # Log receipt of audio periodically
                    audio_received_count += 1
                    if audio_received_count % 20 == 0:
                        logger.debug(f"Audio buffer size: {len(audio_buffer)} chunks")
                    
                    # Process and send buffered audio when we have enough data
                    current_time = time.time()
                    if (len(audio_buffer) >= min_buffer_size and 
                        (current_time - last_send_time) >= min_send_interval):
                        
                        # Take the oldest chunk from buffer
                        chunk_to_send = audio_buffer.pop(0)
                        
                        # Send to browser
                        await self.client_websocket.send_bytes(chunk_to_send)
                        last_send_time = current_time
                else:
                    # Small sleep to prevent CPU spinning
                    await asyncio.sleep(0.01)
                    
                    # Send any remaining buffered chunks at regular intervals
                    current_time = time.time()
                    if audio_buffer and (current_time - last_send_time) >= min_send_interval:
                        chunk_to_send = audio_buffer.pop(0)
                        await self.client_websocket.send_bytes(chunk_to_send)
                        last_send_time = current_time
                    
                    # Check connection periodically
                    if audio_received_count > 0 and audio_received_count % 100 == 0:
                        if not self.sesame_ws.is_connected():
                            logger.warning("SesameAI connection lost, stopping stream")
                            break
                            
        except asyncio.CancelledError:
            logger.info(f"Stream SesameAI→browser task cancelled for client {self.client_id}")
        except Exception as e:
            if self.running:
                logger.error(f"Error in SesameAI→browser stream: {e}", exc_info=True)
            self.running = False
    
    async def handle_control_message(self, message):
        """Handle control messages from client"""
        try:
            data = json.loads(message)
            if data.get('action') == 'ping':
                # Respond with pong to confirm connection is alive
                await self.client_websocket.send_json({
                    'action': 'pong',
                    'timestamp': time.time()
                })
                return True
        except:
            # Not a valid control message, ignore
            pass
        return False
    
    def _process_audio_chunk(self, audio_chunk, prev_chunk_end=None):
        """
        Process audio chunk to eliminate clicks and pops
        """
        try:
            # Convert to numpy array for processing
            # Assuming audio_chunk is Int16 PCM data
            np_data = np.frombuffer(audio_chunk, dtype=np.int16)
            
            # Skip processing if chunk is too small
            if len(np_data) < 20:
                return audio_chunk
                
            # Create output array
            processed = np.copy(np_data)
            
            # Apply gentle tapering at the start of the chunk to avoid clicks
            taper_length = min(32, len(processed) // 10)
            if taper_length > 0:
                # Create a gentle taper window (half cosine)
                taper = np.sin(np.linspace(0, np.pi/2, taper_length))
                processed[:taper_length] = processed[:taper_length] * taper
            
            # Apply gentle tapering at the end of the chunk
            if taper_length > 0:
                # Create a gentle taper window (half cosine)
                taper = np.sin(np.linspace(np.pi/2, 0, taper_length))
                processed[-taper_length:] = processed[-taper_length:] * taper
                
            # If we have data from the previous chunk, ensure smooth transition
            if prev_chunk_end is not None:
                prev_end = np.frombuffer(prev_chunk_end, dtype=np.int16)
                if len(prev_end) > 0 and len(processed) > len(prev_end):
                    # Create a crossfade between chunks
                    xfade_len = len(prev_end)
                    fade_out = np.cos(np.linspace(0, np.pi/2, xfade_len))
                    fade_in = np.sin(np.linspace(0, np.pi/2, xfade_len))
                    
                    # Apply crossfade to start of current chunk
                    processed[:xfade_len] = processed[:xfade_len] * fade_in
            
            # Convert back to bytes
            return processed.tobytes()
        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}")
            # Return original if processing fails
            return audio_chunk
        
    async def stop(self):
        """Stop audio streaming and close connections"""
        self.running = False
        
        # Cancel streaming tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Disconnect from SesameAI
        if self.sesame_ws:
            self.sesame_ws.disconnect()
        
        logger.info(f"Stopped audio streaming for client {self.client_id}")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the main HTML page"""
    with open("static/index.html", "r") as f:
        return f.read()

@app.websocket("/ws/audio/{character}")
async def websocket_audio_endpoint(websocket: WebSocket, character: str):
    """WebSocket endpoint for audio streaming"""
    await websocket.accept()
    
    # Validate character
    valid_characters = ["Miles", "Maya"]
    if character not in valid_characters:
        await websocket.send_json({"error": f"Invalid character. Choose from: {', '.join(valid_characters)}"})
        await websocket.close()
        return
    
    client_id = id(websocket)
    logger.info(f"New client connected: {client_id}, selected character: {character}")
    
    try:
        # Clear existing tokens first to force a new token
        token_manager.clear_tokens()
        
        # Initialize audio stream manager
        stream_manager = AudioStreamManager(websocket, character)
        active_connections[client_id] = stream_manager
        
        # Initialize SesameAI connection with retry logic
        retry_count = 0
        max_retries = 3
        initialization_success = False
        
        while retry_count < max_retries and not initialization_success:
            if retry_count > 0:
                logger.info(f"Retrying connection to SesameAI (attempt {retry_count+1}/{max_retries})")
                await websocket.send_json({"status": "retrying", "attempt": retry_count+1, "max": max_retries})
                await asyncio.sleep(1)  # Small delay between retries
                
            initialization_success = await stream_manager.initialize()
            retry_count += 1
            
        if not initialization_success:
            await websocket.send_json({"error": "Failed to connect to SesameAI after multiple attempts"})
            await websocket.close()
            del active_connections[client_id]
            return
            
        # Start streaming
        await stream_manager.start_streaming()
        
        # Notify client that connection is established
        await websocket.send_json({"status": "connected", "character": character, "sampleRate": stream_manager.sesame_ws.server_sample_rate})
        
        # Keep connection alive until client disconnects
        try:
            while True:
                # Periodically check if connection is still alive
                await asyncio.sleep(1)
                if not stream_manager.running:
                    break
        except Exception:
            pass
            
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}", exc_info=True)
    finally:
        # Clean up connection
        if client_id in active_connections:
            await active_connections[client_id].stop()
            del active_connections[client_id]

@app.get("/api/characters")
async def get_characters():
    """Get available characters"""
    return {"characters": ["Miles", "Maya"]}

if __name__ == "__main__":
    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)
    
    # Run server
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)