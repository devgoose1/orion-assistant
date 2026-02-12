"""
Orion Assistant - JARVIS-style Holographic UI
A futuristic AI assistant interface with glowing effects and geometric designs
"""

import sys
import os
import json
import math
import subprocess
import webbrowser
import asyncio
import tempfile
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv
from html import escape

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect,
    QSizePolicy, QTabWidget
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QThread, QPropertyAnimation, QEasingCurve, Property, QUrl
from PySide6.QtGui import (QPainter, QColor, QPen, QFont, QLinearGradient, QPalette, QBrush, QImage,
                           QVector3D, QMatrix4x4, QTextCursor)

# Try to import QtWebEngine for embedded browser
WEBENGINE_IMPORT_ERROR = None
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage
    WEBENGINE_AVAILABLE = True
except ImportError as e:
    WEBENGINE_AVAILABLE = False
    WEBENGINE_IMPORT_ERROR = str(e)
    QWebEngineView = None  # type: ignore
    QWebEnginePage = None  # type: ignore
    print("WARNING: QtWebEngine not available. Install PySide6 with WebEngine support.")
    print(f"         Import error: {e}")

print(f">>> [DEBUG] Python executable: {sys.executable}")
print(f">>> [DEBUG] WEBENGINE_AVAILABLE: {WEBENGINE_AVAILABLE}")

# Import backend logic
from main import ConversationMemory

# Try to import TTS
try:
    import websockets
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("WARNING: websockets not available. TTS disabled. Install with: pip install websockets")

# Try to import STT
try:
    import speech_recognition as sr
    from faster_whisper import WhisperModel
    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False
    sr = None
    WhisperModel = None
    print("WARNING: STT libraries not available. Install with: pip install SpeechRecognition pyaudio faster-whisper")

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not ELEVENLABS_API_KEY and TTS_AVAILABLE:
    print("WARNING: ELEVENLABS_API_KEY not set. TTS will be disabled.")


class AIAnimationWidget(QWidget):
    """3D rotating sphere animation widget with speaking pulsation"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle_y = 0
        self.angle_x = 0
        self.sphere_points = self.create_sphere_points()
        self.is_speaking = False
        self.pulse_angle = 0
        self.setMinimumSize(200, 200)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(30)

    def start_speaking_animation(self):
        """Activates the speaking animation state."""
        self.is_speaking = True

    def stop_speaking_animation(self):
        """Deactivates the speaking animation state."""
        self.is_speaking = False
        self.pulse_angle = 0
        self.update()

    def create_sphere_points(self, radius=60, num_points_lat=20, num_points_lon=40):
        """Creates a list of QVector3D points on the surface of a sphere."""
        points = []
        for i in range(num_points_lat + 1):
            lat = math.pi * (-0.5 + i / num_points_lat)
            y = radius * math.sin(lat)
            xy_radius = radius * math.cos(lat)

            for j in range(num_points_lon):
                lon = 2 * math.pi * (j / num_points_lon)
                x = xy_radius * math.cos(lon)
                z = xy_radius * math.sin(lon)
                points.append(QVector3D(x, y, z))
        return points

    def update_animation(self):
        self.angle_y += 0.8
        self.angle_x += 0.2
        if self.is_speaking:
            self.pulse_angle += 0.2
            if self.pulse_angle > math.pi * 2:
                self.pulse_angle -= math.pi * 2

        if self.angle_y >= 360: self.angle_y = 0
        if self.angle_x >= 360: self.angle_x = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)

        w, h = self.width(), self.height()
        painter.translate(w / 2, h / 2)

        pulse_factor = 1.0
        if self.is_speaking:
            pulse_amplitude = 0.08
            pulse = (1 + math.sin(self.pulse_angle)) / 2
            pulse_factor = 1.0 + (pulse * pulse_amplitude)

        rotation_y = QMatrix4x4()
        rotation_y.rotate(self.angle_y, 0, 1, 0)
        rotation_x = QMatrix4x4()
        rotation_x.rotate(self.angle_x, 1, 0, 0)
        rotation = rotation_y * rotation_x

        projected_points = []
        for point in self.sphere_points:
            rotated_point = rotation.map(point)
            
            z_factor = 200 / (200 + rotated_point.z())
            x = (rotated_point.x() * z_factor) * pulse_factor
            y = (rotated_point.y() * z_factor) * pulse_factor
            
            size = (rotated_point.z() + 60) / 120
            alpha = int(50 + 205 * size)
            point_size = 1 + size * 3
            projected_points.append((x, y, point_size, alpha))

        projected_points.sort(key=lambda p: p[2])
        
        for x, y, point_size, alpha in projected_points:
            color = QColor(170, 255, 255, alpha) if self.is_speaking else QColor(0, 255, 255, alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(int(x), int(y), int(point_size), int(point_size))


class HexagonWidget(QWidget):
    """Hexagonal frame widget for geometric design"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw hexagon outline
        pen = QPen(QColor(0, 191, 255, 100), 2)
        painter.setPen(pen)
        
        w = self.width()
        h = self.height()
        
        # Hexagon points
        points = [
            (w * 0.25, h * 0.1),
            (w * 0.75, h * 0.1),
            (w * 0.95, h * 0.5),
            (w * 0.75, h * 0.9),
            (w * 0.25, h * 0.9),
            (w * 0.05, h * 0.5),
        ]
        
        for i in range(len(points)):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % len(points)]
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))


class GlowingLineEdit(QLineEdit):
    """Custom line edit with glowing border effect"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_style()
        
    def setup_style(self):
        # Add glow effect
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(15)
        glow.setColor(QColor(0, 191, 255, 180))
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)
        
        self.setStyleSheet("""
            QLineEdit {
                background-color: rgba(10, 25, 47, 180);
                border: 2px solid rgba(0, 191, 255, 100);
                border-radius: 8px;
                padding: 12px 15px;
                color: #00FFFF;
                font-size: 14px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QLineEdit:focus {
                border: 2px solid rgba(0, 255, 255, 200);
                background-color: rgba(15, 30, 55, 200);
            }
        """)


class GlowingTextEdit(QTextEdit):
    """Custom text edit with holographic styling"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_style()
        
    def setup_style(self):
        # Add subtle glow effect
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(20)
        glow.setColor(QColor(0, 191, 255, 100))
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)
        
        self.setStyleSheet("""
            QTextEdit {
                background-color: rgba(5, 15, 30, 200);
                border: 2px solid rgba(0, 191, 255, 80);
                border-radius: 10px;
                padding: 15px;
                color: #B0E0E6;
                font-size: 13px;
                font-family: 'Consolas', 'Courier New', monospace;
                selection-background-color: rgba(0, 191, 255, 50);
            }
        """)


class StatusIndicator(QWidget):
    """Animated status indicator with rotating lines"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        self.angle = 0
        self.is_active = False
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.timer.setInterval(50)
        
    def start_animation(self):
        self.is_active = True
        self.timer.start()
        
    def stop_animation(self):
        self.is_active = False
        self.timer.stop()
        self.update()
        
    def rotate(self):
        self.angle = (self.angle + 5) % 360
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        center_x = self.width() // 2
        center_y = self.height() // 2
        
        if self.is_active:
            # Draw rotating lines
            painter.translate(center_x, center_y)
            painter.rotate(self.angle)
            
            for i in range(4):
                painter.rotate(90)
                pen = QPen(QColor(0, 255, 255, 150), 2)
                painter.setPen(pen)
                painter.drawLine(0, 0, 15, 0)
        else:
            # Draw static circle when idle
            pen = QPen(QColor(0, 191, 255, 100), 2)
            painter.setPen(pen)
            painter.drawEllipse(center_x - 8, center_y - 8, 16, 16)


class WorkerThread(QThread):
    """Background thread for LLM processing with tool calling support"""
    response_ready = Signal(str)
    tool_call_detected = Signal(str, dict)  # tool_name, args
    error_occurred = Signal(str)
    tts_text_ready = Signal(str)
    
    def __init__(self, user_input, conversation_history, model, url):
        super().__init__()
        self.user_input = user_input
        self.conversation_history = conversation_history
        self.model = model
        self.url = url
        
    def run(self):
        import requests
        
        try:
            # Build system prompt with tool calling instructions
            system_prompt = """You are ORION, an AI assistant with tool calling capabilities.

Available tools:
- create_folder(folder_path): Create a new folder
- create_file(file_path, content): Create a new file with content
- edit_file(file_path, content): Append content to existing file  
- list_files(directory_path): List files in directory (use "." for current directory)
- read_file(file_path): Read file contents
- open_application(application_name): Open desktop application (notepad, calculator, chrome, etc)
- open_website(url): Open URL in browser
- execute_code(code): Execute Python code and return result

CRITICAL RULE: When a user asks you to DO something (create, open, list, execute, etc), you MUST respond with ONLY JSON. NO explanatory text before or after.

JSON FORMAT (for tool calls):
{"tool": "tool_name", "args": {"arg1": "value1"}}

If arg is optional or uses default, include it anyway:
{"tool": "list_files", "args": {"directory_path": "."}}

EXAMPLES OF TOOL CALLS:
User: "list files" or "show files" or "list files in current directory"
Assistant: {"tool": "list_files", "args": {"directory_path": "."}}

User: "open notepad" or "launch notepad" or "start notepad"
Assistant: {"tool": "open_application", "args": {"application_name": "notepad"}}

User: "open google" or "go to google.com" or "open google.com"
Assistant: {"tool": "open_website", "args": {"url": "google.com"}}

User: "create folder test"
Assistant: {"tool": "create_folder", "args": {"folder_path": "test"}}

User: "what is 5 plus 5" or "calculate 5+5"
Assistant: {"tool": "execute_code", "args": {"code": "5+5"}}

User: "read the file main.py"
Assistant: {"tool": "read_file", "args": {"file_path": "main.py"}}

EXAMPLES OF NORMAL CHAT (NO JSON):
User: "hello" or "hi"
Assistant: Hello! I'm ORION. How can I assist you today?

User: "what can you do"
Assistant: I can help you with file management, opening applications and websites, executing code, and general questions.

User: "who are you"
Assistant: I'm ORION, an advanced AI assistant with system integration capabilities.

REMEMBER: Action commands = JSON only. Questions/greetings = normal text."""
            
            # Prepare messages with system instruction
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self.conversation_history)
            messages.append({"role": "user", "content": self.user_input})
            
            url = f"{self.url}/api/chat"
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Lower temperature for more consistent JSON
                    "top_p": 0.9,
                }
            }
            
            print(f">>> [DEBUG] Sending request to LLM: {self.user_input}")
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            response_text = result.get("message", {}).get("content", "").strip()
            print(f">>> [DEBUG] LLM Response: {response_text}")
            
            if response_text:
                # Check if response is a tool call (JSON format)
                if response_text.strip().startswith("{") and "tool" in response_text:
                    try:
                        # Try to parse JSON
                        tool_data = json.loads(response_text.strip())
                        
                        if "tool" in tool_data:
                            # Get args, default to empty dict if not present
                            args = tool_data.get("args", {})
                            
                            # Handle different arg formats
                            if args is None:
                                args = {}
                            elif not isinstance(args, dict):
                                args = {}
                            
                            print(f">>> [DEBUG] Tool call detected: {tool_data['tool']} with args: {args}")
                            self.tool_call_detected.emit(tool_data["tool"], args)
                            return
                    except json.JSONDecodeError as e:
                        print(f">>> [DEBUG] JSON parse error: {e}")
                        print(f">>> [DEBUG] Response text: {response_text}")
                        pass  # Not valid JSON, treat as normal text
                
                # Normal text response
                self.response_ready.emit(response_text)
                self.tts_text_ready.emit(response_text)
            else:
                self.error_occurred.emit("No response received from LLM")
                
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit(f"Cannot connect to LLM at {self.url}. Make sure Ollama is running.")
        except Exception as e:
            self.error_occurred.emit(str(e))


class TTSWorker(QThread):
    """Background thread for Text-to-Speech using ElevenLabs"""
    speaking_started = Signal()
    speaking_stopped = Signal()
    error_occurred = Signal(str)
    
    def __init__(self, text, voice_id="pFZP5JQG7iQjIQuC4Bku"):
        super().__init__()
        self.text = text
        self.voice_id = voice_id
        
    def run(self):
        if not TTS_AVAILABLE or not ELEVENLABS_API_KEY:
            return
            
        try:
            self.speaking_started.emit()
            
            # Run TTS in async context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_tts())
            loop.close()
            
        except Exception as e:
            self.error_occurred.emit(f"TTS Error: {str(e)}")
        finally:
            self.speaking_stopped.emit()
    
    async def _run_tts(self):
        """Async TTS implementation"""
        import base64
        import pyaudio
        
        if not TTS_AVAILABLE:
            return
        
        import websockets
        
        uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream-input?model_id=eleven_turbo_v2_5&output_format=pcm_24000"
        
        try:
            async with websockets.connect(uri) as websocket:
                # Start stream
                await websocket.send(json.dumps({
                    "text": " ",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
                    "xi_api_key": ELEVENLABS_API_KEY,
                }))
                
                # Create audio player
                pya = pyaudio.PyAudio()
                stream = pya.open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
                
                # Listen for audio chunks
                async def listen():
                    while True:
                        try:
                            message = await websocket.recv()
                            data = json.loads(message)
                            if data.get("audio"):
                                audio_data = base64.b64decode(data["audio"])
                                stream.write(audio_data)
                            elif data.get("isFinal"):
                                break
                        except websockets.exceptions.ConnectionClosed:
                            break
                
                listen_task = asyncio.create_task(listen())
                
                # Send text
                await websocket.send(json.dumps({"text": self.text + " "}))
                await websocket.send(json.dumps({"text": ""}))
                
                # Wait for completion
                await listen_task
                
                # Cleanup
                stream.stop_stream()
                stream.close()
                pya.terminate()
                
        except Exception as e:
            print(f"TTS Error: {e}")


class STTWorker(QThread):
    """Background thread for Speech-to-Text using faster-whisper"""
    transcription_ready = Signal(str)
    error_occurred = Signal(str)
    recording_started = Signal()
    recording_stopped = Signal()
    
    def __init__(self, language="auto", microphone_index=None):
        super().__init__()
        self.language = language  # "auto", "nl", "en", etc.
        self.microphone_index = microphone_index
        self.recognizer = None
        self.microphone = None
        
    def run(self):
        if not STT_AVAILABLE or sr is None:
            self.error_occurred.emit("STT not available. Install required libraries.")
            return
            
        try:
            # List available microphones
            print(">>> [STT DEBUG] Available microphones:")
            for index, name in enumerate(sr.Microphone.list_microphone_names()):
                print(f"    [{index}] {name}")
            
            # Initialize recognizer and microphone
            self.recognizer = sr.Recognizer()
            if self.microphone_index is not None:
                self.microphone = sr.Microphone(device_index=self.microphone_index)
                print(f">>> [STT DEBUG] Using microphone [{self.microphone_index}]: {sr.Microphone.list_microphone_names()[self.microphone_index]}")
            else:
                self.microphone = sr.Microphone()
                print(f">>> [STT DEBUG] Using default microphone")
            
            # Configure for EXTREMELY bad/quiet microphones
            self.recognizer.dynamic_energy_threshold = False  # Don't auto-adjust
            self.recognizer.energy_threshold = 10  # EXTREMELY low threshold (3% mic needs this)
            self.recognizer.pause_threshold = 0.5  # Shorter pause before stopping
            
            self.recording_started.emit()
            
            # Capture audio
            with self.microphone as source:
                # Skip noise calibration for extremely weak mics - just set ultra-low threshold
                print(f">>> [STT DEBUG] Microphone configured with MAXIMUM sensitivity")
                print(f">>> [STT DEBUG] Energy threshold: {self.recognizer.energy_threshold} (ultra-sensitive)")
                print(f">>> [STT DEBUG] Now listening... PUT YOUR MOUTH CLOSE TO THE MIC AND SPEAK LOUDLY!")
                print(f">>> [STT DEBUG] (Will auto-detect when you start speaking)")
                
                # Extended listening time - will start recording when sound detected
                audio = self.recognizer.listen(source, timeout=30, phrase_time_limit=25)
                print(f">>> [STT DEBUG] Audio captured! Duration: {len(audio.frame_data) / (audio.sample_rate * audio.sample_width):.2f} seconds")
            
            self.recording_stopped.emit()
            
            # Transcribe using faster-whisper
            self._transcribe_audio(audio)
            
        except sr.WaitTimeoutError:
            self.recording_stopped.emit()
            self.error_occurred.emit("No speech detected (timeout)")
        except Exception as e:
            self.recording_stopped.emit()
            self.error_occurred.emit(f"STT Error: {str(e)}")
    
    def _transcribe_audio(self, audio):
        """Transcribe audio using faster-whisper or fallback to Google"""
        try:
            print(f">>> [STT DEBUG] Starting transcription...")
            
            if WhisperModel is None:
                raise ImportError("faster-whisper not available")
                
            # Save audio to temporary file
            audio_data = audio.get_wav_data()
            print(f">>> [STT DEBUG] Audio data size: {len(audio_data)} bytes")
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                temp_audio.write(audio_data)
                temp_path = temp_audio.name
            
            print(f">>> [STT DEBUG] Audio saved to: {temp_path}")
            print(f">>> [STT DEBUG] Loading Whisper 'tiny' model (fast, lower accuracy)...")
            
            # Use 'tiny' model for faster processing (small was too heavy)
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            
            print(f">>> [STT DEBUG] Model loaded, transcribing...")
            
            # Transcribe with language support and VAD filter for noise reduction
            if self.language == "auto":
                segments, info = model.transcribe(
                    temp_path, 
                    beam_size=5,
                    vad_filter=True,  # Voice Activity Detection to filter out noise
                    vad_parameters=dict(min_silence_duration_ms=500)  # Reduce false positives
                )
            else:
                segments, info = model.transcribe(
                    temp_path, 
                    beam_size=5, 
                    language=self.language,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500)
                )
            
            print(f">>> [STT DEBUG] Transcription complete, processing segments...")
            
            # Combine segments
            transcription = " ".join([segment.text for segment in segments])
            print(f">>> [STT DEBUG] Transcription result: '{transcription}'")
            
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass
            
            if transcription.strip():
                print(f">>> [STT DEBUG] Emitting transcription: '{transcription.strip()}'")
                self.transcription_ready.emit(transcription.strip())
            else:
                print(f">>> [STT DEBUG] Empty transcription - no speech detected")
                self.error_occurred.emit("No speech detected")
                
        except Exception as e:
            print(f">>> [STT DEBUG] Whisper transcription failed: {str(e)}")
            print(f">>> [STT DEBUG] Falling back to Google Speech Recognition...")
            # Fallback to Google Speech Recognition
            try:
                if not self.recognizer or not sr:
                    raise RuntimeError("Speech recognition not available")
                
                if self.language == "auto":
                    transcription = self.recognizer.recognize_google(audio)  # type: ignore
                elif self.language == "nl":
                    transcription = self.recognizer.recognize_google(audio, language="nl-NL")  # type: ignore
                elif self.language == "en":
                    transcription = self.recognizer.recognize_google(audio, language="en-US")  # type: ignore
                else:
                    transcription = self.recognizer.recognize_google(audio)  # type: ignore
                    
                if transcription.strip():
                    self.transcription_ready.emit(transcription.strip())
                else:
                    self.error_occurred.emit("No speech detected")
            except Exception as fallback_error:
                self.error_occurred.emit(f"Transcription failed: {str(fallback_error)}")


class OrionMainWindow(QMainWindow):
    """Main window with JARVIS-style holographic interface"""
    user_text_submitted = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ORION - Advanced AI Assistant")
        self.setGeometry(100, 50, 1600, 900)
        self.setMinimumSize(1280, 720)
        
        # Configuration
        self.LOCAL_LLM_MODEL = "qwen2.5:1.5b"
        self.LOCAL_LLM_URL = "http://localhost:11434"
        self.conversation_history = []
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.is_first_orion_chunk = True
        
        # Initialize memory
        self.memory = None
        try:
            self.memory = ConversationMemory()
        except Exception as e:
            print(f"Warning: Could not initialize memory: {e}")
        
        # Current worker threads
        self.worker = None
        self.tts_worker = None
        self.stt_worker = None
        self.is_recording = False
        self.stt_language = "auto"  # "auto", "nl", "en"
        self.stt_microphone_index = None  # None = default microphone

        # Browser widget reference
        self.browser_tabs = None  # QTabWidget container
        self.browser_placeholder = None
        self.browser_base_width = 900

        # Setup UI
        self.setup_ui()
        self.apply_holographic_theme()
        
    def setup_ui(self):
        """Setup the main UI layout"""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # === LEFT PANEL: Tool Activity ===
        left_panel = QFrame()
        left_panel.setObjectName("left_panel")
        left_panel.setMaximumWidth(400)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        # Tool activity header
        self.tool_activity_title = QLabel("⬡ SYSTEM ACTIVITY ⬡")
        self.tool_activity_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tool_activity_title.setStyleSheet("""
            QLabel {
                color: #00FFFF;
                font-size: 12px;
                font-weight: bold;
                padding: 12px;
                background-color: rgba(0, 100, 150, 100);
                border-bottom: 2px solid #00BFFF;
                font-family: 'Consolas', monospace;
                letter-spacing: 2px;
            }
        """)
        left_layout.addWidget(self.tool_activity_title)
        
        # Tool activity display
        self.tool_activity_display = QTextEdit()
        self.tool_activity_display.setReadOnly(True)
        self.tool_activity_display.setStyleSheet("""
            QTextEdit {
                background-color: rgba(5, 15, 30, 180);
                color: #B0E0E6;
                border: none;
                padding: 15px;
                font-size: 11px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        self.tool_activity_display.setHtml("""
            <div style='color: #87CEEB;'>
            <p style="margin-top: 10px;"><i>System initialized and ready...</i></p>
            <p style="margin-top: 10px; color: #00BFFF;">◊ Waiting for commands...</p>
            </div>
        """)
        left_layout.addWidget(self.tool_activity_display)
        
        # === MIDDLE PANEL: Chat & Animation ===
        middle_panel = QFrame()
        middle_panel.setObjectName("middle_panel")
        middle_layout = QVBoxLayout(middle_panel)
        middle_layout.setContentsMargins(0, 0, 0, 15)
        middle_layout.setSpacing(10)
        
        # Animation widget (3D sphere)
        self.animation_widget = AIAnimationWidget()
        self.animation_widget.setMinimumHeight(180)
        self.animation_widget.setMaximumHeight(220)
        middle_layout.addWidget(self.animation_widget, stretch=0)
        
        # Chat display
        self.chat_display = GlowingTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setMinimumHeight(400)
        
        # Add welcome message
        self.chat_display.setHtml("""
            <div style='color: #00BFFF; font-size: 13px;'>
            <p><b style='color: #00FFFF;'>━━━ ORION SYSTEM INITIALIZED ━━━</b></p>
            <p style='color: #B0E0E6; margin-top: 10px;'>Advanced AI Assistant with tool calling capabilities.</p>
            <p style='color: #87CEEB;'>Type your message below or use voice commands.</p>
            </div>
        """)
        
        middle_layout.addWidget(self.chat_display, stretch=1)
        
        # Input area
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(15, 10, 15, 0)
        input_layout.setSpacing(8)
        
        self.input_field = GlowingLineEdit()
        self.input_field.setPlaceholderText("⬢ Enter command or query...")
        self.input_field.returnPressed.connect(self.send_message)
        
        # Microphone button for STT
        self.mic_button = QPushButton("🎤")
        self.mic_button.setFixedSize(45, 45)
        self.mic_button.setToolTip("Click to speak (Right-click for language)")
        self.mic_button.clicked.connect(self.start_recording)
        self.mic_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mic_button.customContextMenuRequested.connect(self.show_language_menu)
        self.mic_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 100, 150, 120);
                border: 2px solid rgba(0, 191, 255, 100);
                border-radius: 22px;
                color: #00FFFF;
                font-size: 20px;
            }
            QPushButton:hover {
                background-color: rgba(0, 150, 200, 150);
                border: 2px solid rgba(0, 255, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(0, 200, 255, 180);
            }
        """)
        
        if not STT_AVAILABLE:
            self.mic_button.setEnabled(False)
            self.mic_button.setToolTip("STT not available - install required libraries")
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.mic_button)
        middle_layout.addWidget(input_container)
        
        # === RIGHT PANEL: Stats & Video ===
        right_panel = QFrame()
        right_panel.setObjectName("right_panel")
        right_panel.setMaximumWidth(560)
        right_panel.setMinimumWidth(480)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(15)
        
        # Stats header
        stats_header = QLabel("⬢ SYSTEM METRICS ⬢")
        stats_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_header.setStyleSheet("""
            QLabel {
                color: #00FFFF;
                font-size: 13px;
                font-weight: bold;
                padding: 10px;
                font-family: 'Consolas', monospace;
                letter-spacing: 2px;
            }
        """)
        right_layout.addWidget(stats_header)
        
        # Stats display
        self.stats_display = QTextEdit()
        self.stats_display.setReadOnly(True)
        self.stats_display.setMaximumHeight(180)
        self.stats_display.setStyleSheet("""
            QTextEdit {
                background-color: rgba(5, 15, 30, 150);
                border: 1px solid rgba(0, 191, 255, 60);
                border-radius: 8px;
                padding: 10px;
                color: #87CEEB;
                font-size: 11px;
                font-family: 'Consolas', monospace;
            }
        """)
        self.update_stats()
        right_layout.addWidget(self.stats_display)
        
        # Integrated Browser
        browser_header = QLabel("⬢ WEB INTERFACE ⬢")
        browser_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        browser_header.setStyleSheet("""
            QLabel {
                color: #00FFFF;
                font-size: 12px;
                font-weight: bold;
                padding: 8px;
                font-family: 'Consolas', monospace;
                letter-spacing: 2px;
            }
        """)
        right_layout.addWidget(browser_header)
        
        self.browser_controls_container = QWidget()
        self.browser_controls_layout = QHBoxLayout(self.browser_controls_container)
        self.browser_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.browser_controls_layout.setSpacing(5)
        self.browser_controls_container.setVisible(False)
        right_layout.addWidget(self.browser_controls_container)

        self.browser_container = QFrame()
        self.browser_container.setObjectName("browser_container")
        self.browser_container_layout = QVBoxLayout(self.browser_container)
        self.browser_container_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.browser_container, stretch=1)

        if WEBENGINE_AVAILABLE and QWebEngineView is not None:
            self._init_embedded_browser()
        else:
            self.browser = None
            self._show_browser_placeholder()
        
        # Hexagon decoration
        hex_widget = HexagonWidget()
        hex_widget.setFixedSize(200, 180)
        right_layout.addWidget(hex_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Add panels to main layout
        main_layout.addWidget(left_panel, stretch=2)
        main_layout.addWidget(middle_panel, stretch=5)
        main_layout.addWidget(right_panel, stretch=3)
    
    def load_browser_home(self):
        """Load the home page in the browser"""
        if not self._ensure_embedded_browser():
            return
        self._set_browser_home()

    def _ensure_embedded_browser(self):
        """Try to enable the embedded browser if possible."""
        if WEBENGINE_AVAILABLE and self.browser_tabs:
            return True
        if not self._try_enable_webengine():
            self._show_browser_placeholder()
            return False
        return self._init_embedded_browser()

    def _try_enable_webengine(self):
        """Attempt to import QtWebEngine at runtime."""
        global WEBENGINE_AVAILABLE, WEBENGINE_IMPORT_ERROR, QWebEngineView, QWebEnginePage
        if WEBENGINE_AVAILABLE and QWebEngineView is not None:
            return True
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView as _QWebEngineView
            from PySide6.QtWebEngineCore import QWebEnginePage as _QWebEnginePage
            QWebEngineView = _QWebEngineView
            QWebEnginePage = _QWebEnginePage
            WEBENGINE_AVAILABLE = True
            WEBENGINE_IMPORT_ERROR = None
            return True
        except ImportError as e:
            WEBENGINE_AVAILABLE = False
            WEBENGINE_IMPORT_ERROR = repr(e)
            return False

    def _init_embedded_browser(self):
        """Create and mount the embedded browser widget with tabs."""
        if not WEBENGINE_AVAILABLE or QWebEngineView is None or self.browser_tabs:
            return False

        if hasattr(self, "browser_placeholder") and self.browser_placeholder is not None:
            self.browser_placeholder.setParent(None)
            self.browser_placeholder = None

        # Create tab widget for browser
        self.browser_tabs = QTabWidget()
        self.browser_tabs.setTabsClosable(True)
        self.browser_tabs.setMovable(True)
        self.browser_tabs.tabCloseRequested.connect(self._close_browser_tab)
        self.browser_tabs.setStyleSheet("""
            QTabWidget::pane {
                background-color: rgba(0, 0, 0, 100);
                border: 2px solid rgba(0, 191, 255, 80);
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: rgba(0, 50, 100, 120);
                border: 1px solid rgba(0, 191, 255, 60);
                border-radius: 4px;
                padding: 6px 12px;
                margin: 2px;
                color: #00BFFF;
            }
            QTabBar::tab:selected {
                background-color: rgba(0, 100, 150, 180);
                border: 1px solid rgba(0, 191, 255, 120);
                color: #00FFFF;
            }
            QTabBar::tab:hover {
                background-color: rgba(0, 80, 130, 150);
            }
        """)
        self.browser_container_layout.addWidget(self.browser_tabs)
        self._ensure_browser_controls()
        
        # Add initial home tab
        self._add_browser_tab()
        return True

    def _ensure_browser_controls(self):
        """Create the browser control buttons when WebEngine is available."""
        if self.browser_controls_container.isVisible() or not self.browser_tabs:
            return

        btn_style = """
            QPushButton {
                background-color: rgba(0, 100, 150, 120);
                border: 1px solid rgba(0, 191, 255, 100);
                border-radius: 4px;
                color: #00FFFF;
                font-size: 14px;
                padding: 5px;
            }
            QPushButton:hover { background-color: rgba(0, 150, 200, 150); }
        """

        back_btn = QPushButton("◄")
        back_btn.setFixedWidth(40)
        back_btn.setToolTip("Back")
        back_btn.clicked.connect(self._browser_back)
        back_btn.setStyleSheet(btn_style)

        forward_btn = QPushButton("►")
        forward_btn.setFixedWidth(40)
        forward_btn.setToolTip("Forward")
        forward_btn.clicked.connect(self._browser_forward)
        forward_btn.setStyleSheet(btn_style)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedWidth(40)
        refresh_btn.setToolTip("Refresh")
        refresh_btn.clicked.connect(self._browser_reload)
        refresh_btn.setStyleSheet(btn_style)

        home_btn = QPushButton("⌂")
        home_btn.setFixedWidth(40)
        home_btn.setToolTip("Home")
        home_btn.clicked.connect(self.load_browser_home)
        home_btn.setStyleSheet(btn_style)

        new_tab_btn = QPushButton("+")
        new_tab_btn.setFixedWidth(40)
        new_tab_btn.setToolTip("New Tab")
        new_tab_btn.clicked.connect(lambda: self._add_browser_tab())
        new_tab_btn.setStyleSheet(btn_style)

        self.browser_controls_layout.addWidget(back_btn)
        self.browser_controls_layout.addWidget(forward_btn)
        self.browser_controls_layout.addWidget(refresh_btn)
        self.browser_controls_layout.addWidget(home_btn)
        self.browser_controls_layout.addWidget(new_tab_btn)
        self.browser_controls_layout.addStretch()
        self.browser_controls_container.setVisible(True)

    def _add_browser_tab(self, url=None, title="New Tab"):
        """Add a new browser tab."""
        if not self.browser_tabs:
            return None
        
        if not WEBENGINE_AVAILABLE or QWebEngineView is None:
            return None
        
        browser = QWebEngineView()
        browser.setStyleSheet("""
            QWebEngineView {
                background-color: rgba(0, 0, 0, 100);
                border: none;
            }
        """)
        
        # Connect title change signal
        browser.titleChanged.connect(lambda t: self._update_tab_title(browser, t))
        
        # Add tab
        index = self.browser_tabs.addTab(browser, title)
        self.browser_tabs.setCurrentIndex(index)
        
        # Load URL or home page
        if url:
            browser.setUrl(QUrl(url))
        else:
            self._set_browser_home_for_view(browser)
        
        self._update_browser_zoom()
        return browser
    
    def _close_browser_tab(self, index):
        """Close a browser tab."""
        if not self.browser_tabs or self.browser_tabs.count() <= 1:
            # Keep at least one tab
            return
        widget = self.browser_tabs.widget(index)
        self.browser_tabs.removeTab(index)
        if widget:
            widget.deleteLater()
    
    def _get_current_browser(self):
        """Get the current active browser view."""
        if not self.browser_tabs:
            return None
        return self.browser_tabs.currentWidget()
    
    def _update_tab_title(self, browser, title):
        """Update tab title when page title changes."""
        if not self.browser_tabs:
            return
        for i in range(self.browser_tabs.count()):
            if self.browser_tabs.widget(i) == browser:
                # Limit title length
                display_title = title[:25] + "..." if len(title) > 25 else title
                self.browser_tabs.setTabText(i, display_title or "New Tab")
                break
    
    def _browser_back(self):
        """Navigate back in current tab."""
        browser = self._get_current_browser()
        if browser and QWebEngineView is not None and isinstance(browser, QWebEngineView):
            browser.back()
    
    def _browser_forward(self):
        """Navigate forward in current tab."""
        browser = self._get_current_browser()
        if browser and QWebEngineView is not None and isinstance(browser, QWebEngineView):
            browser.forward()
    
    def _browser_reload(self):
        """Reload current tab."""
        browser = self._get_current_browser()
        if browser and QWebEngineView is not None and isinstance(browser, QWebEngineView):
            browser.reload()

    def _set_browser_home(self):
        """Set the current browser tab to home page."""
        browser = self._get_current_browser()
        if browser and hasattr(browser, 'setHtml'):
            self._set_browser_home_for_view(browser)
    
    def _set_browser_home_for_view(self, browser):
        """Set the embedded browser home page for a specific view."""
        if not browser:
            return
        browser.setHtml("""
            <html>
            <head>
                <style>
                    body {
                        background: linear-gradient(135deg, #0a0a1a 0%, #10182a 100%);
                        color: #00FFFF;
                        font-family: 'Consolas', monospace;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                    }
                    .container {
                        text-align: center;
                        padding: 20px;
                    }
                    h1 {
                        font-size: 24px;
                        margin-bottom: 10px;
                        text-shadow: 0 0 10px #00FFFF;
                    }
                    p {
                        color: #87CEEB;
                        font-size: 14px;
                    }
                    .pulse {
                        width: 60px;
                        height: 60px;
                        border: 3px solid #00FFFF;
                        border-radius: 50%;
                        margin: 20px auto;
                        animation: pulse 2s infinite;
                    }
                    @keyframes pulse {
                        0%, 100% { transform: scale(1); opacity: 1; }
                        50% { transform: scale(1.1); opacity: 0.7; }
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="pulse"></div>
                    <h1>⬡ ORION WEB INTERFACE ⬡</h1>
                    <p>Browser ready for navigation</p>
                    <p style="margin-top: 20px; font-size: 12px; color: #00BFFF;">Ask me to open a website...</p>
                </div>
            </body>
            </html>
        """)
        self._update_browser_zoom()

    def _update_browser_zoom(self):
        """Scale the web content to better fit the panel width."""
        if not self.browser_tabs:
            return
        # Apply zoom to all tabs
        for i in range(self.browser_tabs.count()):
            browser = self.browser_tabs.widget(i)
            if browser and QWebEngineView is not None and isinstance(browser, QWebEngineView):
                width = max(browser.width(), 1)
                zoom = width / float(self.browser_base_width)
                zoom = max(0.6, min(1.2, zoom))
                browser.setZoomFactor(zoom)

    def resizeEvent(self, event):
        """Keep browser content scaled with the window size."""
        super().resizeEvent(event)
        self._update_browser_zoom()

    def _show_browser_placeholder(self):
        """Show a placeholder when WebEngine is not available."""
        if hasattr(self, "browser_tabs") and self.browser_tabs:
            self.browser_tabs.setParent(None)
            self.browser_tabs = None

        if not hasattr(self, "browser_placeholder") or self.browser_placeholder is None:
            self.browser_placeholder = QLabel()
            self.browser_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.browser_placeholder.setStyleSheet("""
                QLabel {
                    background-color: rgba(0, 0, 0, 100);
                    border: 2px solid rgba(0, 191, 255, 80);
                    border-radius: 8px;
                    color: #00BFFF;
                    font-size: 11px;
                    padding: 20px;
                }
            """)
            self.browser_container_layout.addWidget(self.browser_placeholder)

        error_line = f"Import error: {WEBENGINE_IMPORT_ERROR}\n\n" if WEBENGINE_IMPORT_ERROR else ""
        self.browser_placeholder.setText(
            "◊ WEB BROWSER ◊\n\n"
            "[NOT AVAILABLE]\n\n"
            "QtWebEngine is not available.\n\n"
            f"Python: {sys.executable}\n\n"
            f"{error_line}"
            "Fix your PySide6 install\n"
            "to enable the integrated browser.\n\n"
            "━━━━━━━━━━━━━━━\n\n"
            "Required in env:\n"
            "• PySide6 with QtWebEngine"
        )
        
    def apply_holographic_theme(self):
        """Apply dark holographic theme to the main window"""
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(5, 10, 25, 255),
                    stop:0.5 rgba(10, 20, 40, 255),
                    stop:1 rgba(5, 15, 30, 255)
                );
            }
            QFrame {
                background: transparent;
            }
        """)
        
    def update_stats(self):
        """Update system statistics display"""
        stats_html = f"""
        <div style='color: #87CEEB; font-size: 11px;'>
        <p><b style='color: #00BFFF;'>SESSION:</b> {self.session_id}</p>
        <p><b style='color: #00BFFF;'>MODEL:</b> {self.LOCAL_LLM_MODEL}</p>
        <p><b style='color: #00BFFF;'>MESSAGES:</b> {len(self.conversation_history) // 2}</p>
        """
        
        if self.memory:
            try:
                mem_stats = self.memory.get_stats()
                stats_html += f"""
                <p><b style='color: #00BFFF;'>TOTAL CONV:</b> {mem_stats['total_conversations']}</p>
                <p><b style='color: #00BFFF;'>DAYS ACTIVE:</b> {mem_stats['days_active']}</p>
                """
            except:
                pass
                
        stats_html += "</div>"
        self.stats_display.setHtml(stats_html)
    
    def start_recording(self):
        """Start recording audio for STT"""
        if not STT_AVAILABLE:
            self.append_chat_message("SYSTEM", "Speech recognition not available. Please install required libraries.", "#FF6B6B")
            return
        
        if self.is_recording:
            return
        
        # Create and start STT worker
        self.is_recording = True
        self.stt_worker = STTWorker(language=self.stt_language, microphone_index=self.stt_microphone_index)
        self.stt_worker.transcription_ready.connect(self.handle_transcription)
        self.stt_worker.error_occurred.connect(self.handle_stt_error)
        self.stt_worker.recording_started.connect(self.on_recording_started)
        self.stt_worker.recording_stopped.connect(self.on_recording_stopped)
        self.stt_worker.start()
        
        # Update UI
        self.mic_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 50, 50, 150);
                border: 2px solid rgba(255, 100, 100, 200);
                border-radius: 22px;
                color: #FFFFFF;
                font-size: 20px;
            }
        """)
        self.mic_button.setText("⏺")
    
    @Slot()
    def on_recording_started(self):
        """Visual feedback when recording starts"""
        self.input_field.setPlaceholderText("🎤 Listening... Speak now!")
        self.append_chat_message("SYSTEM", "🎤 Listening...", "#00FFFF")
    
    @Slot()
    def on_recording_stopped(self):
        """Visual feedback when recording stops"""
        self.is_recording = False
        self.input_field.setPlaceholderText("⬢ Enter command or query...")
        
        # Reset button style
        self.mic_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 100, 150, 120);
                border: 2px solid rgba(0, 191, 255, 100);
                border-radius: 22px;
                color: #00FFFF;
                font-size: 20px;
            }
            QPushButton:hover {
                background-color: rgba(0, 150, 200, 150);
                border: 2px solid rgba(0, 255, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(0, 200, 255, 180);
            }
        """)
        self.mic_button.setText("🎤")
    
    @Slot(str)
    def handle_transcription(self, text):
        """Handle transcribed text from STT"""
        if text:
            self.input_field.setText(text)
            self.append_chat_message("YOU (voice)", text, "#FFD700")
            # Auto-send the message
            QTimer.singleShot(500, self.send_message)
    
    @Slot(str)
    def handle_stt_error(self, error_msg):
        """Handle STT errors"""
        self.append_chat_message("SYSTEM", f"⚠ {error_msg}", "#FF6B6B")
    
    def show_language_menu(self, position):
        """Show language and microphone selection menu on right-click"""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(10, 25, 47, 230);
                border: 2px solid rgba(0, 191, 255, 150);
                border-radius: 8px;
                padding: 5px;
                color: #00FFFF;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: rgba(0, 150, 200, 150);
            }
        """)
        
        # Language options
        auto_action = QAction("🌐 Auto-detect", self)
        auto_action.triggered.connect(lambda: self.set_stt_language("auto"))
        if self.stt_language == "auto":
            auto_action.setText("🌐 Auto-detect ✓")
        
        dutch_action = QAction("🇳🇱 Dutch", self)
        dutch_action.triggered.connect(lambda: self.set_stt_language("nl"))
        if self.stt_language == "nl":
            dutch_action.setText("🇳🇱 Dutch ✓")
        
        english_action = QAction("🇬🇧 English", self)
        english_action.triggered.connect(lambda: self.set_stt_language("en"))
        if self.stt_language == "en":
            english_action.setText("🇬🇧 English ✓")
        
        menu.addAction(auto_action)
        menu.addAction(dutch_action)
        menu.addAction(english_action)
        menu.addSeparator()
        
        # Microphone selection submenu
        if STT_AVAILABLE and sr:
            mic_menu = menu.addMenu("🎙 Select Microphone")
            mic_menu.setStyleSheet(menu.styleSheet())
            
            try:
                mic_list = sr.Microphone.list_microphone_names()
                
                # Default microphone option
                default_action = QAction("Default Microphone", self)
                default_action.triggered.connect(lambda: self.set_microphone(None))
                if self.stt_microphone_index is None:
                    default_action.setText("Default Microphone ✓")
                mic_menu.addAction(default_action)
                mic_menu.addSeparator()
                
                # List all available microphones
                for idx, mic_name in enumerate(mic_list):
                    # Truncate long names
                    display_name = mic_name if len(mic_name) < 40 else mic_name[:37] + "..."
                    mic_action = QAction(f"[{idx}] {display_name}", self)
                    mic_action.triggered.connect(lambda checked, i=idx: self.set_microphone(i))
                    if self.stt_microphone_index == idx:
                        mic_action.setText(f"[{idx}] {display_name} ✓")
                    mic_menu.addAction(mic_action)
            except Exception as e:
                error_action = QAction(f"Error listing mics: {str(e)}", self)
                error_action.setEnabled(False)
                mic_menu.addAction(error_action)
        
        menu.exec(self.mic_button.mapToGlobal(position))
    
    def set_microphone(self, index):
        """Set the microphone to use"""
        self.stt_microphone_index = index
        if index is None:
            self.append_chat_message("SYSTEM", "Using default microphone", "#00BFFF")
        else:
            try:
                if STT_AVAILABLE and sr:
                    mic_name = sr.Microphone.list_microphone_names()[index]
                    self.append_chat_message("SYSTEM", f"Microphone set to: [{index}] {mic_name}", "#00BFFF")
            except:
                self.append_chat_message("SYSTEM", f"Microphone set to: [{index}]", "#00BFFF")
    
    def set_stt_language(self, language):
        """Set the STT language"""
        self.stt_language = language
        lang_names = {"auto": "Auto-detect", "nl": "Dutch", "en": "English"}
        self.append_chat_message("SYSTEM", f"Language set to: {lang_names.get(language, language)}", "#00BFFF")
    
    def append_chat_message(self, sender, message, color="#B0E0E6"):
        """Helper method to append a message to chat display"""
        self.chat_display.append(f"""
            <p style='margin: 10px 0;'>
            <b style='color: {color};'>► {escape(sender)}:</b>
            <span style='color: #B0E0E6;'>{escape(message)}</span>
            </p>
        """)
        
    @Slot()
    def send_message(self):
        """Handle sending a message"""
        user_input = self.input_field.text().strip()
        
        if not user_input:
            return
            
        # Clear input field
        self.input_field.clear()
        
        # Display user message
        self.chat_display.append(f"""
            <p style='margin: 10px 0;'>
            <b style='color: #00FF00;'>► USER:</b>
            <span style='color: #B0E0E6;'>{escape(user_input)}</span>
            </p>
        """)
        
        # Update UI state
        self.input_field.setEnabled(False)
        
        # Process in background thread
        self.worker = WorkerThread(
            user_input,
            self.conversation_history.copy(),
            self.LOCAL_LLM_MODEL,
            self.LOCAL_LLM_URL
        )
        self.worker.response_ready.connect(self.handle_response)
        self.worker.tool_call_detected.connect(self.handle_tool_call)
        self.worker.tts_text_ready.connect(self.start_tts)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.finished.connect(self.reset_ui_state)
        self.worker.start()
        
        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": user_input})
    
    @Slot(str, dict)
    def handle_tool_call(self, tool_name, args):
        """Execute tool call and send result back"""
        print(f">>> [TOOL CALL] Executing {tool_name} with args: {args}")
        
        # Update tool activity display - show that we're executing
        self.tool_activity_title.setText(f"⬡ EXECUTING // {tool_name.upper()} ⬡")
        self.tool_activity_display.setHtml(f"""
            <div style='color: #FFA500;'>
            <p><b>⚡ EXECUTING TOOL...</b></p>
            <p>Tool: {escape(tool_name)}</p>
            <p>Args: {escape(str(args))}</p>
            </div>
        """)
        
        result = None
        result_html = ""
        
        try:
            if tool_name == "create_folder":
                result = self._create_folder(args.get("folder_path"))
                result_html = f"""
                    <p style='color: #00FFFF;'><b>CREATE FOLDER</b></p>
                    <p style='color: #87CEEB;'>Path: {escape(args.get("folder_path", ""))}</p>
                    <p style='color: #90EE90;'>Status: {result.get("status")}</p>
                    <p>{escape(result.get("message", ""))}</p>
                """
            
            elif tool_name == "create_file":
                result = self._create_file(args.get("file_path"), args.get("content"))
                result_html = f"""
                    <p style='color: #00FFFF;'><b>CREATE FILE</b></p>
                    <p style='color: #87CEEB;'>Path: {escape(args.get("file_path", ""))}</p>
                    <p style='color: #90EE90;'>Status: {result.get("status")}</p>
                    <p>{escape(result.get("message", ""))}</p>
                """
            
            elif tool_name == "edit_file":
                result = self._edit_file(args.get("file_path"), args.get("content"))
                result_html = f"""
                    <p style='color: #00FFFF;'><b>EDIT FILE</b></p>
                    <p style='color: #87CEEB;'>Path: {escape(args.get("file_path", ""))}</p>
                    <p style='color: #90EE90;'>Status: {result.get("status")}</p>
                    <p>{escape(result.get("message", ""))}</p>
                """
            
            elif tool_name == "list_files":
                result = self._list_files(args.get("directory_path", "."))
                if result.get("status") == "success":
                    files = result.get("files", [])
                    result_html = f"""
                        <p style='color: #00FFFF;'><b>LIST FILES</b></p>
                        <p style='color: #87CEEB;'>Directory: {escape(result.get("directory_path", "."))}</p>
                        <p style='color: #90EE90;'>Found {len(files)} items</p>
                        <ul style='margin: 5px 0; padding-left: 20px;'>
                    """
                    for f in files[:20]:  # Limit to 20 items
                        result_html += f"<li style='color: #B0E0E6;'>{escape(f)}</li>"
                    if len(files) > 20:
                        result_html += f"<li style='color: #FFA500;'>... and {len(files) - 20} more</li>"
                    result_html += "</ul>"
                else:
                    result_html = f"<p style='color: #FF6B6B;'>{escape(result.get('message', ''))}</p>"
            
            elif tool_name == "read_file":
                result = self._read_file(args.get("file_path"))
                if result.get("status") == "success":
                    content = result.get("content", "")
                    preview = content[:500] + ("..." if len(content) > 500 else "")
                    result_html = f"""
                        <p style='color: #00FFFF;'><b>READ FILE</b></p>
                        <p style='color: #87CEEB;'>Path: {escape(args.get("file_path", ""))}</p>
                        <pre style='background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; color: #E0E0E0; font-size: 10px; white-space: pre-wrap;'>{escape(preview)}</pre>
                    """
                else:
                    result_html = f"<p style='color: #FF6B6B;'>{escape(result.get('message', ''))}</p>"
            
            elif tool_name == "open_application":
                result = self._open_application(args.get("application_name"))
                result_html = f"""
                    <p style='color: #00FFFF;'><b>OPEN APPLICATION</b></p>
                    <p style='color: #87CEEB;'>App: {escape(args.get("application_name", ""))}</p>
                    <p style='color: #90EE90;'>Status: {result.get("status")}</p>
                    <p>{escape(result.get("message", ""))}</p>
                """
            
            elif tool_name == "open_website":
                result = self._open_website(args.get("url"))
                result_html = f"""
                    <p style='color: #00FFFF;'><b>OPEN WEBSITE</b></p>
                    <p style='color: #87CEEB;'>URL: {escape(args.get("url", ""))}</p>
                    <p style='color: #90EE90;'>Status: {result.get("status")}</p>
                    <p>{escape(result.get("message", ""))}</p>
                """
            
            elif tool_name == "execute_code":
                result = self._execute_code(args.get("code"))
                if result.get("status") == "success":
                    code = args.get("code", "")
                    output = result.get("output", "")
                    result_html = f"""
                        <p style='color: #00FFFF;'><b>EXECUTE CODE</b></p>
                        <pre style='background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; color: #87CEEB; font-size: 10px; white-space: pre-wrap;'>{escape(code)}</pre>
                        <p style='color: #00BFFF; margin-top: 8px;'><b>OUTPUT:</b></p>
                        <pre style='background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; color: #90EE90; font-size: 10px; white-space: pre-wrap;'>{escape(output)}</pre>
                    """
                else:
                    result_html = f"<p style='color: #FF6B6B;'>{escape(result.get('message', ''))}</p>"
            
            # Update tool activity display
            self.tool_activity_display.setHtml(result_html)
            
            # Update title based on success/failure
            if result and result.get("status") == "success":
                self.tool_activity_title.setText(f"⬡ ✓ SUCCESS // {tool_name.upper()} ⬡")
            else:
                self.tool_activity_title.setText(f"⬡ ✗ ERROR // {tool_name.upper()} ⬡")
            
            # Display in chat
            if result:
                status_color = "#90EE90" if result.get("status") == "success" else "#FF6B6B"
                status_icon = "✓" if result.get("status") == "success" else "✗"
                self.chat_display.append(f"""
                    <p style='margin: 10px 0;'>
                    <b style='color: {status_color};'>{status_icon} TOOL EXECUTED:</b>
                    <span style='color: #87CEEB;'>{escape(tool_name)} - {escape(result.get("message", ""))}</span>
                    </p>
                """)
                
                # Update conversation history with tool result
                tool_result_msg = f"Tool '{tool_name}' executed. Result: {result.get('message', '')}"
                if result.get("output"):
                    tool_result_msg += f"\nOutput: {result.get('output')}"
            else:
                tool_result_msg = f"Tool '{tool_name}' executed but returned no result."
            self.conversation_history.append({"role": "assistant", "content": tool_result_msg})
            
            # Save to memory
            if self.memory:
                try:
                    user_msg = self.conversation_history[-2]["content"]
                    self.memory.save_exchange(user_msg, tool_result_msg, self.session_id)
                except:
                    pass
            
            # TTS feedback - only on success
            if result and result.get("status") == "success":
                feedback_msg = result.get("message", f"Tool {tool_name} executed.")
                self.start_tts(feedback_msg)
            
        except Exception as e:
            error_msg = f"Error executing tool: {str(e)}"
            print(f">>> [ERROR] {error_msg}")
            self.tool_activity_display.setHtml(f"<p style='color: #FF6B6B;'>{escape(error_msg)}</p>")
            self.chat_display.append(f"""
                <p style='margin: 10px 0;'>
                <b style='color: #FF4444;'>⚠ TOOL ERROR:</b>
                <span style='color: #FFB6C1;'>{escape(error_msg)}</span>
                </p>
            """)
        
        # Update stats
        self.update_stats()
    
    # Tool execution methods
    def _create_folder(self, folder_path):
        try:
            if not folder_path or not isinstance(folder_path, str):
                return {"status": "error", "message": "Invalid folder path provided."}
            if os.path.exists(folder_path):
                return {"status": "skipped", "message": f"Folder '{folder_path}' already exists."}
            os.makedirs(folder_path)
            return {"status": "success", "message": f"Created folder '{folder_path}'."}
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}
    
    def _create_file(self, file_path, content):
        try:
            if not file_path or not isinstance(file_path, str):
                return {"status": "error", "message": "Invalid file path provided."}
            if os.path.exists(file_path):
                return {"status": "skipped", "message": f"File '{file_path}' already exists."}
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content or "")
            return {"status": "success", "message": f"Created file '{file_path}'."}
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}
    
    def _edit_file(self, file_path, content):
        try:
            if not file_path or not isinstance(file_path, str):
                return {"status": "error", "message": "Invalid file path provided."}
            if not os.path.exists(file_path):
                return {"status": "error", "message": f"File '{file_path}' does not exist."}
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{content or ''}")
            return {"status": "success", "message": f"Appended content to '{file_path}'."}
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}
    
    def _list_files(self, directory_path):
        try:
            path_to_list = directory_path if directory_path else '.'
            if not isinstance(path_to_list, str):
                return {"status": "error", "message": "Invalid directory path provided."}
            if not os.path.isdir(path_to_list):
                return {"status": "error", "message": f"'{path_to_list}' is not a valid directory."}
            files = os.listdir(path_to_list)
            return {"status": "success", "message": f"Found {len(files)} items.", "files": files, "directory_path": path_to_list}
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}
    
    def _read_file(self, file_path):
        try:
            if not file_path or not isinstance(file_path, str):
                return {"status": "error", "message": "Invalid file path provided."}
            if not os.path.exists(file_path):
                return {"status": "error", "message": f"File '{file_path}' does not exist."}
            if not os.path.isfile(file_path):
                return {"status": "error", "message": f"'{file_path}' is not a file."}
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"status": "success", "message": f"Read file '{file_path}'.", "content": content}
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}
    
    def _open_application(self, application_name):
        try:
            if not application_name or not isinstance(application_name, str):
                return {"status": "error", "message": "Invalid application name provided."}
            
            print(f">>> [DEBUG] Attempting to open application: '{application_name}'")
            command, shell_mode = [], False
            if sys.platform == "win32":
                app_map = {
                    "calculator": "calc", "calc": "calc",
                    "notepad": "notepad",
                    "chrome": "chrome", "google chrome": "chrome",
                    "firefox": "firefox",
                    "edge": "msedge", "microsoft edge": "msedge",
                    "explorer": "explorer", "file explorer": "explorer",
                    "cmd": "cmd", "command prompt": "cmd",
                    "powershell": "powershell",
                    "paint": "mspaint",
                    "wordpad": "write"
                }
                app_command = app_map.get(application_name.lower(), application_name)
                command = f"start {app_command}"
                shell_mode = True
            elif sys.platform == "darwin":
                app_map = {
                    "calculator": "Calculator",
                    "chrome": "Google Chrome", "google chrome": "Google Chrome",
                    "firefox": "Firefox",
                    "finder": "Finder",
                    "textedit": "TextEdit"
                }
                app_name = app_map.get(application_name.lower(), application_name)
                command = ["open", "-a", app_name]
            else:
                command = [application_name.lower()]
            
            result = subprocess.Popen(command, shell=shell_mode)
            print(f">>> [DEBUG] Application launched with PID: {result.pid}")
            return {"status": "success", "message": f"Launched '{application_name}'."}
        except FileNotFoundError:
            return {"status": "error", "message": f"Application '{application_name}' not found."}
        except Exception as e:
            print(f">>> [ERROR] Failed to launch application: {e}")
            return {"status": "error", "message": f"Error: {str(e)}"}
    
    def _open_website(self, url):
        try:
            if not url or not isinstance(url, str):
                return {"status": "error", "message": "Invalid URL provided."}
            
            # Clean and format URL
            url = url.strip()
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            print(f">>> [DEBUG] Opening URL: {url}")
            
            # Use integrated browser if available - open in new tab
            if self._ensure_embedded_browser() and self.browser_tabs:
                self._add_browser_tab(url, url)
                print(f">>> [DEBUG] URL loaded in new browser tab: {url}")
                return {"status": "success", "message": f"Opened '{url}' in new tab."}

            print(">>> [ERROR] Integrated browser not available. QtWebEngine import failed.")
            detail = f"Python: {sys.executable}. Import error: {WEBENGINE_IMPORT_ERROR}" if WEBENGINE_IMPORT_ERROR else f"Python: {sys.executable}"
            return {"status": "error", "message": f"Integrated browser not available. {detail}"}
            
        except Exception as e:
            print(f">>> [ERROR] Failed to open website: {e}")
            return {"status": "error", "message": f"Error: {str(e)}"}
    
    def _execute_code(self, code):
        try:
            if not code or not isinstance(code, str):
                return {"status": "error", "message": "Invalid code provided."}
            
            # Create a restricted namespace
            namespace = {"__builtins__": __builtins__}
            
            # Capture output
            from io import StringIO
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            
            try:
                # Execute code
                exec(code, namespace)
                output = captured_output.getvalue()
                
                # If no output, try to eval and get result
                if not output:
                    try:
                        result = eval(code, namespace)
                        output = str(result) if result is not None else ""
                    except:
                        pass
                
                return {"status": "success", "message": "Code executed successfully.", "output": output or "(no output)"}
            finally:
                sys.stdout = old_stdout
                
        except Exception as e:
            return {"status": "error", "message": f"Execution error: {str(e)}"}
        
    @Slot(str)
    def handle_response(self, response):
        """Handle LLM text response"""
        # Display bot response
        if self.is_first_orion_chunk:
            self.is_first_orion_chunk = False
            self.chat_display.append(f"""
                <p style='margin: 10px 0;'>
                <b style='color: #00FFFF;'>◆ ORION:</b>
                <span style='color: #87CEEB;'>{escape(response)}</span>
                </p>
            """)
        else:
            # Append to existing message
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(response)
        
        # Scroll to bottom
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # Update conversation history
        self.conversation_history.append({"role": "assistant", "content": response})
        
        # Save to memory
        if self.memory:
            try:
                user_msg = self.conversation_history[-2]["content"]
                self.memory.save_exchange(user_msg, response, self.session_id)
            except Exception as e:
                print(f"Warning: Could not save to memory: {e}")
        
        # Update stats
        self.update_stats()
        
        # Reset for next message
        self.is_first_orion_chunk = True
    
    @Slot(str)
    def handle_error(self, error_msg):
        """Handle error during processing"""
        self.chat_display.append(f"""
            <p style='margin: 10px 0;'>
            <b style='color: #FF4444;'>⚠ ERROR:</b>
            <span style='color: #FFB6C1;'>{escape(error_msg)}</span>
            </p>
        """)
        
        self.tool_activity_display.setHtml(f"""
            <div style='color: #FF6B6B;'>
            <p><b>ERROR</b></p>
            <p>{escape(error_msg)}</p>
            </div>
        """)
    
    @Slot()
    def reset_ui_state(self):
        """Reset UI to ready state"""
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
    
    @Slot(str)
    def start_tts(self, text):
        """Start TTS playback"""
        if not TTS_AVAILABLE or not ELEVENLABS_API_KEY:
            return
        
        # Stop previous TTS if running
        if self.tts_worker and self.tts_worker.isRunning():
            self.tts_worker.terminate()
            self.tts_worker.wait()
        
        # Start new TTS
        self.tts_worker = TTSWorker(text)
        self.tts_worker.speaking_started.connect(self.animation_widget.start_speaking_animation)
        self.tts_worker.speaking_stopped.connect(self.animation_widget.stop_speaking_animation)
        self.tts_worker.error_occurred.connect(self.handle_error)
        self.tts_worker.start()
        
    def closeEvent(self, event):
        """Handle window close event"""
        # Stop TTS if running
        if self.tts_worker and self.tts_worker.isRunning():
            self.tts_worker.terminate()
            self.tts_worker.wait()
        
        # Close memory
        if self.memory:
            self.memory.close()
        
        event.accept()


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set application-wide font
    font = QFont("Consolas", 10)
    app.setFont(font)
    
    # Create and show main window
    window = OrionMainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
