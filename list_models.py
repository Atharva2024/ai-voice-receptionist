from google import genai
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("AVAILABLE MODELS:\n")

# iterate directly over pager
for m in client.models.list():
    print("-", m.name)

print("\nMODEL METADATA FOR TTS MODELS:\n")

for m in client.models.list():
    if "tts" in m.name.lower():
        print("MODEL:", m.name)
        print(m)
        print("\n---------------------\n")

