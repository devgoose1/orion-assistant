import os
from dotenv import load_dotenv
import requests
import json
import sys
from typing import Optional, TYPE_CHECKING
import threading

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

def get_local_llm_response(prompt: str, model: str = "qwen:1.5b", base_url: str = "http://localhost:11434") -> str:
    """Get response from locally hosted LLM (Ollama)"""
    try:
        url = f"{base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        return result.get("response", "").strip()
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

    print("\n INFO: Chat started (type 'exit' to quit)\n")

    while True:
        # Get user input
        user_input = get_stt_input(recognizer, microphone)
        
        if not user_input:
            continue
            
        if user_input.lower() == "exit":
            break

        # Get LLM response
        if USE_LOCAL_LLM:
            response_text = get_local_llm_response(user_input, LOCAL_LLM_MODEL, LOCAL_LLM_URL)
            if response_text:
                print(f"Bot: {response_text}\n")
        else:
            if chat is not None:
                response = chat.send_message_stream(user_input)
                print("Bot: ", end="", flush=True)
                for chunk in response:
                    print(chunk.text, end="", flush=True)
                print("\n")

    print("\n INFO: Goodbye!")

if __name__ == "__main__":
    main()