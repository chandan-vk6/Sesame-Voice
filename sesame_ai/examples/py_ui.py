import sys
import os
import time
import threading
import logging
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QComboBox, QFrame, QSlider, QProgressBar,
                            QGraphicsDropShadowEffect, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QRect
from PyQt5.QtGui import QColor, QFont, QIcon, QLinearGradient, QBrush, QPalette, QPainter, QPainterPath
import pyqtgraph as pg

# Import the existing VoiceChat class
from voice_chat import VoiceChat

# Setup logging
logger = logging.getLogger('sesame.gui')

class WaveformWidget(pg.PlotWidget):
    """Custom widget to display audio waveform"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set background to transparent
        self.setBackground(None)
        
        # Remove axes
        self.hideAxis('left')
        self.hideAxis('bottom')
        
        # Set up plot
        self.plot_item = self.getPlotItem()
        self.plot_item.setMouseEnabled(x=False, y=False)
        self.plot_item.setMenuEnabled(False)
        
        # Create line for waveform
        pen = pg.mkPen(color=(0, 183, 255), width=2)
        self.waveform_line = self.plot_item.plot([], [], pen=pen)
        
        # Buffer for waveform data
        self.buffer_size = 1000
        self.buffer = np.zeros(self.buffer_size)
        
        # Time axis data
        self.time_data = np.linspace(0, 1, self.buffer_size)
        
    def update_waveform(self, audio_data):
        """Update the waveform display with new audio data"""
        if audio_data is None or len(audio_data) == 0:
            return
            
        # Convert audio data to numpy array if it's not already
        if not isinstance(audio_data, np.ndarray):
            audio_data = np.frombuffer(audio_data, dtype=np.int16)
        
        # Normalize audio data to [-1, 1]
        audio_data = audio_data.astype(np.float32) / 32768.0
        
        # Shift buffer and add new data
        if len(audio_data) >= self.buffer_size:
            # If we have more data than buffer size, just take the most recent
            self.buffer = audio_data[-self.buffer_size:]
        else:
            # Shift buffer left and add new data
            self.buffer = np.roll(self.buffer, -len(audio_data))
            self.buffer[-len(audio_data):] = audio_data
        
        # Update plot
        self.waveform_line.setData(self.time_data, self.buffer)


class CircularProgressBar(QWidget):
    """Custom circular progress bar for voice activity visualization"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize properties
        self.value = 0
        self.max_value = 100
        self.min_value = 0
        self.progress_color = QColor(0, 183, 255)
        self.background_color = QColor(50, 50, 50, 100)
        self.text_color = QColor(255, 255, 255)
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMinimumSize(100, 100)
        
    def sizeHint(self):
        return QSize(100, 100)
        
    def setValue(self, value):
        """Set the current value of the progress bar"""
        self.value = max(self.min_value, min(self.max_value, value))
        self.update()
        
    def paintEvent(self, event):
        """Paint the circular progress bar"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate sizes
        size = min(self.width(), self.height())
        rect = QRect(0, 0, size, size)
        rect.moveCenter(self.rect().center())
        
        # Draw background circle
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.background_color)
        painter.drawEllipse(rect)
        
        # Draw progress arc
        painter.setBrush(self.progress_color)
        span_angle = int(360 * (self.value - self.min_value) / (self.max_value - self.min_value))
        painter.drawPie(rect, 90 * 16, -span_angle * 16)
        
        # Draw center circle (for microphone icon)
        center_rect = QRect(0, 0, int(size * 0.7), int(size * 0.7))
        center_rect.moveCenter(rect.center())
        painter.setBrush(QColor(30, 30, 30))
        painter.drawEllipse(center_rect)
        
        # Draw text
        painter.setPen(self.text_color)
        painter.setFont(QFont("Arial", 12, QFont.Bold))
        painter.drawText(rect, Qt.AlignCenter, f"{int(self.value)}%")


class RoundedButton(QPushButton):
    """Custom button with rounded corners and hover effects"""
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        
        # Set fixed size
        self.setFixedSize(180, 50)
        
        # Set cursor to pointing hand
        self.setCursor(Qt.PointingHandCursor)
        
        # Set font
        font = QFont("Arial", 10, QFont.Bold)
        self.setFont(font)
        
        # Set style
        self.setStyleSheet("""
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052D4, stop:1 #4364F7);
                color: white;
                border-radius: 25px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052D4, stop:1 #6FB1FC);
            }
            QPushButton:pressed {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052D4, stop:1 #4364F7);
                padding: 10px;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #aaaaaa;
            }
        """)
        
        # Add shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)


class VoiceAIGUI(QMainWindow):
    """Main GUI window for Voice AI Chat"""
    
    # Signal for updating the waveform
    waveform_update_signal = pyqtSignal(object)
    
    def __init__(self):
        super().__init__()
        
        # Initialize the main window
        self.setWindowTitle("SesameAI Voice Chat")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1A1A1A;
            }
            QLabel {
                color: #FFFFFF;
                font-family: Arial;
            }
            QComboBox {
                background-color: #2A2A2A;
                color: #FFFFFF;
                border: 1px solid #3A3A3A;
                border-radius: 5px;
                padding: 5px;
                min-width: 100px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
            QComboBox::down-arrow {
                image: url(./assets/down_arrow.png);
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #2A2A2A;
                border: 1px solid #3A3A3A;
                selection-background-color: #4364F7;
                selection-color: #FFFFFF;
            }
            QSlider {
                height: 25px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #3A3A3A;
                height: 8px;
                background: #2A2A2A;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052D4, stop:1 #4364F7);
                border: 1px solid #5c5c5c;
                width: 18px;
                margin: -2px 0;
                border-radius: 9px;
            }
            QProgressBar {
                border: 1px solid #3A3A3A;
                border-radius: 5px;
                text-align: center;
                color: #FFFFFF;
                background-color: #2A2A2A;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052D4, stop:1 #4364F7);
                border-radius: 5px;
            }
        """)
        
        # Initialize the VoiceChat instance
        self.voice_chat = None
        
        # Set up the UI
        self.setup_ui()
        
        # Set up audio devices
        self.populate_audio_devices()
        
        # Audio data buffer for visualization
        self.audio_buffer = np.zeros(1024)
        
        # Set up timer for animations
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_animations)
        self.animation_timer.start(50)  # 20 fps
        
        # Voice activity value
        self.voice_activity = 0
        
        # Connect waveform update signal
        self.waveform_update_signal.connect(self.waveform_widget.update_waveform)
        
        # Flag to indicate if chat is running
        self.chat_running = False
    
    def setup_ui(self):
        """Set up the user interface"""
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # Header section
        header_layout = QHBoxLayout()
        
        # Logo and title
        logo_label = QLabel("SesameAI")
        logo_label.setFont(QFont("Arial", 24, QFont.Bold))
        logo_label.setStyleSheet("color: #4364F7;")
        header_layout.addWidget(logo_label)
        
        header_layout.addStretch()
        
        # Character selection
        char_layout = QHBoxLayout()
        char_label = QLabel("Character:")
        char_label.setFont(QFont("Arial", 12))
        self.char_combo = QComboBox()
        self.char_combo.addItems(VoiceChat.AVAILABLE_CHARACTERS)
        self.char_combo.setFont(QFont("Arial", 12))
        char_layout.addWidget(char_label)
        char_layout.addWidget(self.char_combo)
        header_layout.addLayout(char_layout)
        
        main_layout.addLayout(header_layout)
        
        # Middle section (visualizations)
        visual_frame = QFrame()
        visual_frame.setFrameShape(QFrame.StyledPanel)
        visual_frame.setStyleSheet("QFrame { background-color: #2A2A2A; border-radius: 10px; }")
        
        # Add shadow effect to the visualization frame
        shadow = QGraphicsDropShadowEffect(visual_frame)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 5)
        visual_frame.setGraphicsEffect(shadow)
        
        visual_layout = QVBoxLayout(visual_frame)
        visual_layout.setContentsMargins(20, 20, 20, 20)
        
        # Waveform visualization
        self.waveform_widget = WaveformWidget()
        visual_layout.addWidget(self.waveform_widget)
        
        # Voice activity indicator
        activity_layout = QHBoxLayout()
        
        # Add circular progress bar
        self.voice_activity_indicator = CircularProgressBar()
        activity_layout.addWidget(self.voice_activity_indicator, alignment=Qt.AlignCenter)
        
        visual_layout.addLayout(activity_layout)
        
        main_layout.addWidget(visual_frame)
        
        # Bottom section (controls)
        controls_layout = QHBoxLayout()
        
        # Audio device selection
        devices_layout = QVBoxLayout()
        
        # Input device
        input_layout = QHBoxLayout()
        input_label = QLabel("Microphone:")
        input_label.setFont(QFont("Arial", 10))
        self.input_combo = QComboBox()
        self.input_combo.setFont(QFont("Arial", 10))
        input_layout.addWidget(input_label)
        input_layout.addWidget(self.input_combo)
        devices_layout.addLayout(input_layout)
        
        # Output device
        output_layout = QHBoxLayout()
        output_label = QLabel("Speaker:")
        output_label.setFont(QFont("Arial", 10))
        self.output_combo = QComboBox()
        self.output_combo.setFont(QFont("Arial", 10))
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_combo)
        devices_layout.addLayout(output_layout)
        
        controls_layout.addLayout(devices_layout)
        controls_layout.addStretch()
        
        # Start/Stop button
        self.start_stop_button = RoundedButton("Start Chat")
        self.start_stop_button.clicked.connect(self.toggle_chat)
        controls_layout.addWidget(self.start_stop_button)
        
        main_layout.addLayout(controls_layout)
        
        # Status bar
        self.statusBar().showMessage("Ready")
        self.statusBar().setStyleSheet("QStatusBar { color: #BBBBBB; }")
    
    def populate_audio_devices(self):
        """Populate the audio device combo boxes"""
        # Create a temporary PyAudio instance to get device info
        import pyaudio
        p = pyaudio.PyAudio()
        
        # Clear existing items
        self.input_combo.clear()
        self.output_combo.clear()
        
        # Input devices
        for i in range(p.get_device_count()):
            dev_info = p.get_device_info_by_index(i)
            name = dev_info.get('name', 'Unknown')
            inputs = dev_info.get('maxInputChannels', 0)
            
            if inputs > 0:
                self.input_combo.addItem(f"{name}", i)
        
        # Output devices
        for i in range(p.get_device_count()):
            dev_info = p.get_device_info_by_index(i)
            name = dev_info.get('name', 'Unknown')
            outputs = dev_info.get('maxOutputChannels', 0)
            
            if outputs > 0:
                self.output_combo.addItem(f"{name}", i)
                
        # Terminate PyAudio
        p.terminate()
    
    def update_animations(self):
        """Update animations and visualizations"""
        if self.chat_running and self.voice_chat:
            # Generate random data for now - this would be replaced with actual audio data
            # In a real implementation, you'd hook this up to the VoiceChat class audio capture
            if hasattr(self.voice_chat, 'last_rms'):
                # Scale RMS to 0-100
                self.voice_activity = min(100, max(0, self.voice_chat.last_rms / 10))
            else:
                # Just animate randomly if we don't have real data
                self.voice_activity = max(0, min(100, self.voice_activity + np.random.normal(0, 5)))
            
            # Update the voice activity indicator
            self.voice_activity_indicator.setValue(self.voice_activity)
            
            # Update waveform with random data for the animation
            # In a real implementation, this would use actual audio data
            audio_data = np.random.normal(0, 0.1 * (0.5 + self.voice_activity/100), 1024)
            self.waveform_update_signal.emit(audio_data)
    
    def toggle_chat(self):
        """Toggle between starting and stopping the chat"""
        if self.chat_running:
            self.stop_chat()
        else:
            self.start_chat()
    
    def start_chat(self):
        """Start the voice chat"""
        # Get selected devices
        input_idx = self.input_combo.currentData()
        output_idx = self.output_combo.currentData()
        character = self.char_combo.currentText()
        
        # Update UI
        self.start_stop_button.setText("Stop Chat")
        self.statusBar().showMessage(f"Connecting to {character}...")
        
        # Disable controls
        self.input_combo.setEnabled(False)
        self.output_combo.setEnabled(False)
        self.char_combo.setEnabled(False)
        
        # Initialize VoiceChat
        self.voice_chat = VoiceChat(
            character=character,
            input_device=input_idx,
            output_device=output_idx
        )
        
        # Extend the VoiceChat class to capture audio levels
        original_capture_microphone = self.voice_chat.capture_microphone
        
        def extended_capture_microphone(*args, **kwargs):
            """Extended version of capture_microphone that also captures audio levels"""
            logger.debug("Extended microphone capture started")
            
            while self.voice_chat.running:
                if not self.voice_chat.ws.is_connected():
                    time.sleep(0.1)
                    continue
                
                try:
                    # Read audio data from microphone
                    data = self.voice_chat.input_stream.read(self.voice_chat.chunk_size, exception_on_overflow=False)
                    
                    # Check audio level for voice activity detection
                    audio_samples = np.frombuffer(data, dtype=np.int16)
                    rms_val = np.sqrt(np.mean(audio_samples.astype(np.float32) ** 2))
                    
                    # Store the RMS value for visualization
                    self.voice_chat.last_rms = rms_val
                    
                    # Update waveform
                    self.waveform_update_signal.emit(audio_samples)
                    
                    if rms_val > self.voice_chat.amplitude_threshold:
                        # Voice detected
                        self.voice_chat.silence_counter = 0
                        self.voice_chat.ws.send_audio_data(data)
                    else:
                        # Silence detected
                        self.voice_chat.silence_counter += 1
                        if self.voice_chat.silence_counter >= self.voice_chat.silence_limit:
                            # Send completely silent audio after silence threshold
                            silent_data = np.zeros(self.voice_chat.chunk_size, dtype=np.int16).tobytes()
                            self.voice_chat.ws.send_audio_data(silent_data)
                        else:
                            # Continue sending actual audio during brief pauses
                            self.voice_chat.ws.send_audio_data(data)
                except Exception as e:
                    if self.voice_chat.running:
                        logger.error(f"Error capturing microphone: {e}", exc_info=True)
                        time.sleep(0.1)
        
        # Replace the original method with our extended version
        # self.voice_chat.capture_microphone = extended_capture_microphone
        
        # Start voice chat in a separate thread
        self.chat_thread = threading.Thread(target=self._run_voice_chat)
        self.chat_thread.daemon = True
        self.chat_thread.start()
        
        # Set chat running flag
        self.chat_running = True
    
    def _run_voice_chat(self):
        """Run the voice chat in a separate thread"""
        try:
            # Start the voice chat
            if self.voice_chat.authenticate():
                # Connect to WebSocket (will trigger on_connect callback)
                if self.voice_chat.connect():
                    # Update status
                    self.statusBar().showMessage(f"Connected to {self.voice_chat.character}")
                else:
                    # Connection failed
                    self.statusBar().showMessage("Failed to connect")
                    self.stop_chat()
            else:
                # Authentication failed
                self.statusBar().showMessage("Authentication failed")
                self.stop_chat()
        except Exception as e:
            logger.error(f"Error starting voice chat: {e}", exc_info=True)
            self.statusBar().showMessage(f"Error: {str(e)}")
            self.stop_chat()
    
    def stop_chat(self):
        """Stop the voice chat"""
        # Update UI
        self.start_stop_button.setText("Start Chat")
        self.statusBar().showMessage("Disconnected")
        
        # Enable controls
        self.input_combo.setEnabled(True)
        self.output_combo.setEnabled(True)
        self.char_combo.setEnabled(True)
        
        # Stop voice chat
        if self.voice_chat:
            self.voice_chat.stop()
            self.voice_chat = None
        
        # Set chat running flag
        self.chat_running = False
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Stop voice chat if running
        if self.chat_running:
            self.stop_chat()
        
        # Accept the event
        event.accept()


def main():
    """Main function"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create application
    app = QApplication(sys.argv)
    
    # Create and show main window
    main_window = VoiceAIGUI()
    main_window.show()
    
    # Run the application
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()