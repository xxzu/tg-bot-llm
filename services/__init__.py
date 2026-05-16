# Services module
from services.gemini import (
    client, USE_NEW_API, genai_old, genai_new,
    process_image_with_gemini, download_and_encode_image
)
from services.voice import process_voice_message, text_to_speech
