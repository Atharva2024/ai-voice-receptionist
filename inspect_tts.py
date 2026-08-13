from google import genai
import os, json
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise SystemExit("❌ No GEMINI_API_KEY found.")

client = genai.Client(api_key=API_KEY)

model_name = "models/gemini-2.5-flash-preview-tts"

print("🔍 Fetching raw model metadata from Google API...\n")

# We bypass client.models.* and hit the internal API directly
raw = client._api_client.request(
    http_request={
        "method": "GET",
        "url": f"/v1beta/models/{model_name}"
    },
    http_options={},
    stream=False
)

print(json.dumps(raw, indent=2))

