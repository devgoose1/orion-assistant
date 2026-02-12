import os
from dotenv import load_dotenv
import requests
import json
import sys
from typing import Optional, TYPE_CHECKING, List, Tuple
import threading
import sqlite3
from datetime import datetime

if TYPE_CHECKING:
    import speech_recognition as sr

try:
    import speech_recognition as sr
    from faster_whisper import WhisperModel
    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False
    print("WARNING: SpeechRecognition or faster-whisper not available. Install with: pip install SpeechRecognition PyAudio faster-whisper")

try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import play
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("WARNING: ElevenLabs not available. Install with: pip install elevenlabs")

class ConversationMemory:
    """Manages long-term conversation storage using SQLite"""
    
    def __init__(self, db_path: str = "conversation_memory.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.create_tables()
    
    def create_tables(self):
        """Create necessary database tables"""
        cursor = self.conn.cursor()
        
        # Main conversation table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_message TEXT NOT NULL,
                bot_response TEXT NOT NULL,
                session_id TEXT
            )
        ''')
        
        # Session metadata table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                end_time DATETIME,
                summary TEXT
            )
        ''')
        
        self.conn.commit()
    
    def save_exchange(self, user_message: str, bot_response: str, session_id: Optional[str] = None):
        """Save a conversation exchange to the database"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (user_message, bot_response, session_id)
            VALUES (?, ?, ?)
        ''', (user_message, bot_response, session_id))
        self.conn.commit()
    
    def get_recent_history(self, limit: int = 10) -> List[Tuple[str, str]]:
        """Retrieve recent conversation history"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT user_message, bot_response
            FROM conversations
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        results = cursor.fetchall()
        return list(reversed(results))  # Return in chronological order
    
    def get_session_history(self, session_id: str) -> List[Tuple[str, str]]:
        """Retrieve conversation history for a specific session"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT user_message, bot_response
            FROM conversations
            WHERE session_id = ?
            ORDER BY timestamp ASC
        ''', (session_id,))
        return cursor.fetchall()
    
    def search_conversations(self, query: str, limit: int = 5) -> List[Tuple[str, str, str]]:
        """Search past conversations by keyword"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT timestamp, user_message, bot_response
            FROM conversations
            WHERE user_message LIKE ? OR bot_response LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (f'%{query}%', f'%{query}%', limit))
        return cursor.fetchall()
    
    def format_history_for_context(self, history: List[Tuple[str, str]], max_messages: int = 5) -> str:
        """Format conversation history for LLM context"""
        if not history:
            return ""
        
        recent = history[-max_messages:] if len(history) > max_messages else history
        formatted = "Previous conversation:\n"
        for user_msg, bot_msg in recent:
            formatted += f"User: {user_msg}\n"
            formatted += f"Assistant: {bot_msg}\n"
        formatted += "\nCurrent conversation:\n"
        return formatted
    
    def clear_old_conversations(self, days: int = 30):
        """Delete conversations older than specified days"""
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM conversations
            WHERE timestamp < datetime('now', '-' || ? || ' days')
        ''', (days,))
        self.conn.commit()
        return cursor.rowcount
    
    def get_stats(self) -> dict:
        """Get conversation statistics"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM conversations')
        total = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(DISTINCT DATE(timestamp))
            FROM conversations
        ''')
        days_active = cursor.fetchone()[0]
        
        return {
            'total_conversations': total,
            'days_active': days_active
        }
    
    def close(self):
        """Close database connection"""
        self.conn.close()

def get_local_llm_response(prompt: str, model: str = "qwen:1.5b", base_url: str = "http://localhost:11434", conversation_history: Optional[List[dict]] = None) -> str:
    """Get response from locally hosted LLM (Ollama)"""
    try:
        url = f"{base_url}/api/chat"
        
        # Build message history
        if conversation_history is None:
            conversation_history = []
        
        messages = conversation_history + [{"role": "user", "content": prompt}]
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }
        
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        return result.get("message", {}).get("content", "").strip()
    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Cannot connect to local LLM at {base_url}")
        print("   Make sure Ollama is running: ollama serve")
        return ""
    except Exception as e:
        print(f"\nERROR: Error getting LLM response: {e}")
        return ""

def get_stt_input(recognizer: Optional[sr.Recognizer], microphone: Optional[sr.Microphone]) -> str:
    """Get input from STT or fallback to manual input"""
    if not recognizer or not microphone:
        user_input = input("You: ")
        return user_input
    
    try:
        print("INFO: Listening... (speak now)", end="", flush=True)
        
        with microphone as source:
            # Adjust for ambient noise briefly
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
        
        print("\rINFO: Processing...", end="", flush=True)
        
        # Use faster-whisper for local transcription (offline)
        try:
            if not STT_AVAILABLE:
                raise ImportError("faster-whisper not available")
            from faster_whisper import WhisperModel
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            audio_data = audio.get_wav_data()
            import io
            import tempfile
            # Save audio to temporary file (faster-whisper requires file path)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                temp_audio.write(audio_data)
                temp_path = temp_audio.name
            
            segments, info = model.transcribe(temp_path, beam_size=5)
            user_input = " ".join([segment.text for segment in segments])
            
            # Clean up temp file
            import os as os_module
            os_module.unlink(temp_path)
        except:
            # Fallback to Google if Whisper fails
            user_input = recognizer.recognize_google(audio)  # type: ignore
        
        print(f"\rYou: {user_input}")
        return user_input
    
    except sr.WaitTimeoutError:
        print("\rINFO: Timeout - no speech detected")
        print("Falling back to manual input...")
        user_input = input("You: ")
        return user_input
    except sr.UnknownValueError:
        print("\rWARNING: Could not understand audio")
        print("Falling back to manual input...")
        user_input = input("You: ")
        return user_input
    except Exception as e:
        print(f"\rERROR: STT Error: {e}")
        print("Falling back to manual input...")
        user_input = input("You: ")
        return user_input

def main():
    load_dotenv()

    # Configuration
    USE_LOCAL_LLM = True  # Set to True to use local LLM, False for Gemini
    LOCAL_LLM_MODEL = "qwen2.5:1.5b"  # Ollama model name
    LOCAL_LLM_URL = "http://localhost:11434"  # Ollama endpoint
    USE_STT = True  # Set to True to enable Speech-to-Text
    USE_MEMORY = True  # Enable long-term memory
    MEMORY_CONTEXT_SIZE = 5  # Number of previous exchanges to include as context

    # Initialize memory system
    memory = None
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if USE_MEMORY:
        try:
            memory = ConversationMemory()
            stats = memory.get_stats()
            print(f" INFO: Memory initialized ({stats['total_conversations']} conversations, {stats['days_active']} days active)")
        except Exception as e:
            print(f"WARNING: Failed to initialize memory: {e}")
            memory = None
    
    # Initialize STT if available and desired
    recognizer = None
    microphone = None
    
    if USE_STT and STT_AVAILABLE:
        try:
            print("INFO: Initializing Speech-to-Text (faster-whisper)...")
            recognizer = sr.Recognizer()
            microphone = sr.Microphone()
            print(" INFO: STT Ready")
        except Exception as e:
            print(f"WARNING: Failed to initialize STT: {e}")
            print("   Falling back to manual input")
            recognizer = None
            microphone = None
    elif USE_STT and not STT_AVAILABLE:
        print("WARNING: STT disabled: SpeechRecognition not installed")

    # Initialize LLM
    chat = None  # Initialize for type checking
    conversation_history = []  # Track conversation history for local LLM
    
    if USE_LOCAL_LLM:
        print(f" INFO: Using local LLM ({LOCAL_LLM_MODEL} via Ollama)")
        print(f"   Endpoint: {LOCAL_LLM_URL}")
    else:
        from google import genai
        from google.genai import types
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        client = genai.Client(api_key=api_key)
        chat = client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction="",
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
        )
        print(" INFO: Connected to Gemini API")

    print("\n INFO: Chat started (type 'exit' to quit)")
    if USE_MEMORY:
        print(" INFO: Type 'search <query>' to search past conversations")
        print(" INFO: Type 'stats' to see memory statistics\n")
    else:
        print()

    while True:
        # Get user input
        user_input = get_stt_input(recognizer, microphone)
        
        if not user_input:
            continue
            
        if user_input.lower() == "exit":
            break
        
        # Handle memory commands
        if USE_MEMORY and memory:
            if user_input.lower() == "stats":
                stats = memory.get_stats()
                print(f"Bot: Memory Statistics:")
                print(f"  Total conversations: {stats['total_conversations']}")
                print(f"  Days active: {stats['days_active']}\n")
                continue
            
            if user_input.lower().startswith("search "):
                query = user_input[7:].strip()
                results = memory.search_conversations(query)
                if results:
                    print(f"Bot: Found {len(results)} conversations matching '{query}':")
                    for timestamp, user_msg, bot_msg in results:
                        print(f"\n[{timestamp}]")
                        print(f"User: {user_msg[:100]}..." if len(user_msg) > 100 else f"User: {user_msg}")
                        print(f"Bot: {bot_msg[:100]}..." if len(bot_msg) > 100 else f"Bot: {bot_msg}")
                    print()
                else:
                    print(f"Bot: No conversations found matching '{query}'\n")
                continue
        
        # Get LLM response
        response_text = ""
        if USE_LOCAL_LLM:
            response_text = get_local_llm_response(user_input, LOCAL_LLM_MODEL, LOCAL_LLM_URL, conversation_history)
            if response_text:
                print(f"Bot: {response_text}\n")
                # Update conversation history
                conversation_history.append({"role": "user", "content": user_input})
                conversation_history.append({"role": "assistant", "content": response_text})
        else:
            if chat is not None:
                # For Gemini, we'd need to maintain conversation history differently
                # For now, just send the message
                response = chat.send_message_stream(user_input)
                print("Bot: ", end="", flush=True)
                response_parts = []
                for chunk in response:
                    print(chunk.text, end="", flush=True)
                    response_parts.append(chunk.text)
                response_text = "".join(response_parts)
                print("\n")
        
        # Save conversation to memory
        if USE_MEMORY and memory and response_text:
            try:
                memory.save_exchange(user_input, response_text, session_id)
            except Exception as e:
                print(f"WARNING: Failed to save to memory: {e}")

    # Cleanup
    if memory:
        memory.close()
    
    print("\n INFO: Goodbye!")

if __name__ == "__main__":
    main()