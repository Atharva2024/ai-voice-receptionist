import os
import uuid
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
import assemblyai as aai
import asyncio
from fastapi import Body, HTTPException
from google import genai  # client library
import base64
from fastapi.responses import FileResponse
import requests
import wave
import json
ENABLE_TTS = False  # 🔇 Silent dev mode
ENABLE_LLM= False
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())  # ensures .env is found no matter what
  # loads ASSEMBLYAI_API_KEY from .env if present

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not aai.settings.api_key:
    raise SystemExit("Error: ASSEMBLYAI_API_KEY not set (set it in your shell or .env).")

app = FastAPI(title="AI Voice - STT")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def home():
    return {"message": "AI Voice STT server is running"}


@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    # Basic client-side validation for file types
    allowed_ext = (".wav", ".mp3", ".m4a", ".mp4", ".webm", ".flac", ".ogg")
    if not file.filename.lower().endswith(allowed_ext):
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    # Save upload to a temporary file
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    tmp_path = os.path.join(UPLOAD_DIR, filename)
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    finally:
        file.file.close()

    # Transcribe using AssemblyAI SDK (uploads file, polls until done)
    try:
        transcriber = aai.Transcriber()
        result = transcriber.transcribe(tmp_path)
    except Exception as e:
        # Clean up and return error
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    # Optionally remove temp file to keep disk clean
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    return JSONResponse({
        "text": result.text,
        "status": getattr(result, "status", None),
        "id": getattr(result, "id", None)
    })

# configure gemini (after load_dotenv())
print("🔍 DEBUG: Loading GEMINI_API_KEY...")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
print("🔍 DEBUG: Key exists?", GEMINI_API_KEY is not None)

print("🔍 DEBUG: GEMINI_API_KEY value:", GEMINI_API_KEY)

print("🔍 DEBUG: Attempting to create Gemini client...")
try:
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        print("✔ DEBUG: Gemini client created successfully.")
    else:
        client = None
        print("❌ DEBUG: No GEMINI_API_KEY found in environment.")
except Exception as e:
    print("❌ DEBUG: Gemini client creation failed:", e)
    raise


@app.post("/reply")
async def generate_reply(payload: dict = Body(...)):
    user_text = payload.get("text")
    if not user_text:
        raise HTTPException(status_code=400, detail="Missing 'text' in request body.")

    system_prompt = payload.get("system", "You are a helpful and concise assistant.")

    if not client:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured on server.")

    def call_gemini():
        full_prompt = f"{system_prompt}\n\nUser: {user_text}"

        resp = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[
                {"role": "user", "parts": [{"text": full_prompt}]}
            ]
        )
        return resp

    try:
        resp = await asyncio.to_thread(call_gemini)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini call failed: {e}")

    try:
        assistant_text = resp.text
    except:
        assistant_text = str(resp)

    return {"reply": assistant_text}

@app.post("/speak")
async def speak(payload: dict = Body(...)):
    print("📌 /speak called. Payload =", payload)

    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text' field.")

    if not client:
        raise HTTPException(status_code=500, detail="Gemini client not configured.")

    # ---------- TTS CALL ----------
    def call_tts(input_text: str):
        print("📌 Calling Gemini TTS:", input_text)

        return client.models.generate_content(
            model="models/gemini-2.5-flash-preview-tts",
            contents=[{"text": input_text}],
            config={
                "responseModalities": ["AUDIO"],
                "speechConfig": "achernar"  # voice name
            }
        )

    try:
        resp = await asyncio.to_thread(call_tts, text)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"TTS failed: {e}")

    # ---------- AUDIO EXTRACTION ----------
    try:
        print("📌 Extracting audio...")

        part = resp.candidates[0].content.parts[0]
        blob = part.inline_data

        if not blob:
            raise Exception("No inline_data found in TTS response")

        audio_bytes = blob.data  # raw PCM (L16, 24kHz)

        output_path = "output.wav"
        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)        # mono
            wav_file.setsampwidth(2)        # 16-bit PCM
            wav_file.setframerate(24000)    # 24 kHz
            wav_file.writeframes(audio_bytes)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Audio extraction failed: {e}"
        )

    print("✔ Audio ready:", output_path)
    return FileResponse(
        output_path,
        media_type="audio/wav",
        filename="response.wav"
    )
def decide_reply(session) -> str:
    if session["intent"] is None:
        session["intent"] = "appointment"
        return "Sure, I can help with that. Which day would you like to book?"

    if session["requested_date"] is None:
        return "Which day would you like to book?"

    if session["requested_time"] is None:
        return "What time works best for you?"

    # ⬇️ NEW CHECK
    if not session.get("time_explicit", False):
        return "Got it. What exact time would you prefer?"

    return (
        f"Alright. Let me check availability for "
        f"{session['requested_date']} at {session['requested_time']}."
    )

def get_guidance_reply(session) -> str:
    MAX_CLARIFICATIONS = 3

    # ---- Escape hatch ----
    if session["clarification_count"] >= MAX_CLARIFICATIONS:
        session["requested_date"] = None
        session["requested_time"] = None
        session["time_explicit"] = False
        session["last_slot"] = None
        session["clarification_count"] = 0

        return (
            "I'm having trouble understanding. "
            "Let's start again. Which day would you like to book?"
        )

    # ---- Intent bootstrap ----
    if session["intent"] is None:
        session["intent"] = "appointment"
        return (
            "Sure. Which day would you like to book? "
            "Please say something like Friday."
        )

    # ---- Missing date ----
    if session["requested_date"] is None:
        session["clarification_count"] += 1
        return (
            "Please say the day clearly. "
            "For example: Friday or Saturday."
        )

    # ---- Missing time ----
    if session["requested_time"] is None:
        session["clarification_count"] += 1
        return (
            "Please say the time clearly. "
            "For example: five PM or five thirty PM."
        )

    # ---- Fuzzy time DOES NOT resolve ----
    if not session["time_explicit"]:
        session["clarification_count"] += 1
        return (
            "I heard a general time, but I need an exact time. "
            "Please say it like five PM or five thirty PM."
        )

    # ---- SUCCESS ----
    # ---- Ready to confirm ----
    session["clarification_count"] = 0
    session["awaiting_confirmation"] = True

    return (
        f"Just to confirm, you want to book an appointment on "
        f"{session['requested_date']} at {session['requested_time']}, correct?"
)


def extract_slots_llm(user_text: str) -> dict:
    prompt = f"""
You are a strict information extraction system.

Return ONLY valid JSON. No markdown. No explanation.

Schema:
{{
  "date": string | null,
  "time": string | null,
  "correction": boolean
}}

User input:
"{user_text}"
"""

    try:
        resp = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[{"text": prompt}],
            config={"responseMimeType": "application/json"}
        )

        print("====== LLM DEBUG START ======")
        print("resp:", resp)
        print("resp.text:", getattr(resp, "text", None))
        print("candidates:", resp.candidates)

        if resp.candidates:
            c = resp.candidates[0]
            print("candidate.content:", c.content)
            print("candidate.parts:", c.content.parts)
            if c.content.parts:
                print("part.text:", c.content.parts[0].text)

        print("====== LLM DEBUG END ======")

        raw = resp.candidates[0].content.parts[0].text
        return json.loads(raw)

    except Exception as e:
        print("[DEBUG][EXTRACT ERROR]:", e)
        return {"date": None, "time": None, "correction": False}

import re

import re

def extract_slots_fallback(user_text: str) -> dict:
    text = user_text.lower()

    date = None
    time = None
    correction = False

    # ---- date rules ----
    if "today" in text:
        date = "Today"
    elif "tomorrow" in text:
        date = "Tomorrow"
    elif "monday" in text:
        date = "Monday"
    elif "tuesday" in text:
        date = "Tuesday"
    elif "wednesday" in text:
        date = "Wednesday"
    elif "thursday" in text:
        date = "Thursday"
    elif "friday" in text:
        date = "Friday"
    elif "saturday" in text:
        date = "Saturday"
    elif "sunday" in text:
        date = "Sunday"

    # ---- fuzzy time words ----
    if "morning" in text:
        time = "10:00 AM"
    elif "afternoon" in text:
        time = "2:00 PM"
    elif "evening" in text:
        time = "6:00 PM"
    elif "night" in text:
        time = "8:00 PM"

    # ---- exact time like 5pm, 5:30 pm ----
    match = re.search(r'(\d{1,2})(:\d{2})?\s*(am|pm)', text)
    if match:
        hour = match.group(1)
        minute = match.group(2) or ":00"
        suffix = match.group(3).upper()
        time = f"{hour}{minute} {suffix}"

    # ---- correction detection ----
    if any(word in text for word in ["actually", "instead", "no wait", "change", "sorry"]):
        correction = True

    return {
        "date": date,
        "time": time,
        "correction": correction
    }
def needs_explicit_time(session) -> bool:
    return session["requested_time"] is None or not session.get("time_explicit", False)

def is_yes(text: str) -> bool:
    return text.lower() in {"yes", "yeah", "yep", "correct", "right", "confirm"}

def is_no(text: str) -> bool:
    return text.lower() in {"no", "nope", "nah", "wrong", "cancel"}

# in-memory session store (temporary)
sessions = {}
@app.post("/call")
async def call(
    audio: UploadFile = File(...),
    session_id: str | None = Form(None)
):
    print(">>> ENTERED /call")
    print("📞 /call invoked")

    if session_id is None:
        session_id = uuid.uuid4().hex
        sessions[session_id] = {
            "history": [],
            "intent": None,
            "requested_date": None,
            "requested_time": None,
            "time_explicit": False,
            "clarification_count": 0,
            "last_slot": None,
            "awaiting_confirmation": False               
            }
        print("New session:", session_id)
    else:
        print("Existing session:", session_id)
    session=sessions[session_id]
    # Save audio
    temp_audio_path = f"uploads/{uuid.uuid4().hex}_{audio.filename}"
    with open(temp_audio_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    # Transcribe
    try:
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(temp_audio_path)

        user_text = transcript.text.strip()
        print(">>> AFTER STT, user_text =", user_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    # --------- Confirmation handling (MUST be here) ---------
    if session.get("awaiting_confirmation", False):
        if is_yes(user_text):
            session["awaiting_confirmation"] = False
            session["clarification_count"] = 0

            reply_text = (
                f"Your appointment is confirmed for "
                f"{session['requested_date']} at {session['requested_time']}."
        )

            sessions[session_id]["history"].append(("assistant", reply_text))
            return {
                "session_id": session_id,
                "reply": reply_text,
                "history": sessions[session_id]["history"]
        }

        if is_no(user_text):
            session["requested_date"] = None
            session["requested_time"] = None
            session["time_explicit"] = False
            session["last_slot"] = None
            session["clarification_count"] = 0
            session["awaiting_confirmation"] = False

            reply_text = "Alright, let's start again. Which day would you like to book?"

            sessions[session_id]["history"].append(("assistant", reply_text))
            return {
                "session_id": session_id,
                "reply": reply_text,
                "history": sessions[session_id]["history"]
        }

    # Neither yes nor no
        reply_text = "Please say yes to confirm or no to restart."

        sessions[session_id]["history"].append(("assistant", reply_text))
        return {
            "session_id": session_id,
            "reply": reply_text,
            "history": sessions[session_id]["history"]
    }

    # After STT
    print(">>> AFTER STT, user_text =", user_text)

# --------- Guard: unclear speech ---------
    if len(user_text) < 3:
        reply_text = "Sorry, I didn’t catch that. Could you please repeat?"

    # Silent dev mode
        if not ENABLE_TTS:
            return {
                "session_id": session_id,
                "reply": reply_text,
                "history": session["history"]
        }

    # TTS fallback (same logic as /speak)
        def call_tts(input_text: str):
            return client.models.generate_content(
                model="models/gemini-2.5-flash-preview-tts",
                contents=[{"text": input_text}],
                config={
                    "responseModalities": ["AUDIO"],
                    "speechConfig": "achernar"
            }
        )

        tts_resp = await asyncio.to_thread(call_tts, reply_text)
        part = tts_resp.candidates[0].content.parts[0]
        audio_bytes = part.inline_data.data

        output_path = f"uploads/{session_id}_reply.wav"
        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(audio_bytes)

        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename="reply.wav",
            headers={"X-Session-ID": session_id}
    )
# --------- Normal flow continues ---------
    user_text = user_text.strip()
    sessions[session_id]["history"].append(("user", user_text))
    # ---- LLM slot extraction ----
    print(">>> REACHED SLOT EXTRACTION")
    try:
        if ENABLE_LLM:
            slots = extract_slots_llm(user_text)
        else:
            raise RuntimeError("LLM disabled")
    except Exception as e:
        print("[WARN] LLM unavailable, using fallback:", e)
        slots = extract_slots_fallback(user_text)


    print(f"[DEBUG] RAW USER TEXT: {user_text}")
    print(f"[DEBUG] EXTRACTED SLOTS: {slots}")
    print(f"[SESSION {session_id}] SLOTS:", slots)

    # ---- Apply DATE ----
    if slots.get("date") is not None:
        session["requested_date"] = slots["date"]

    # 🚨 If date comes AFTER time, invalidate time
        if session.get("last_slot") == "time":
            session["requested_time"] = None
            session["time_explicit"] = False

        session["last_slot"] = "date"

# ---- Apply TIME ----
    if slots.get("time") is not None:
        session["requested_time"] = slots["time"]

    # Explicit time only if digits were spoken
        if re.search(r'\d', user_text):
            session["time_explicit"] = True
        else:
            session["time_explicit"] = False

        session["last_slot"] = "time"
    # Decide reply
    reply_text = get_guidance_reply(session)
    print(f"[SESSION {session_id}] BOT :", reply_text)



    sessions[session_id]["history"].append(("assistant", reply_text))
    # ---------- SILENT DEV MODE ----------
    if not ENABLE_TTS:
        return {
        "session_id": session_id,
        "reply": reply_text,
        "history": sessions[session_id]["history"]
    }

    # ---------- TTS (reuse exact logic pattern from /speak) ----------
    def call_tts(input_text: str):
        return client.models.generate_content(
            model="models/gemini-2.5-flash-preview-tts",
            contents=[{"text": input_text}],
            config={
                "responseModalities": ["AUDIO"],
                "speechConfig": "achernar"
        }
    )
    try:
        tts_resp = await asyncio.to_thread(call_tts, reply_text)
        part = tts_resp.candidates[0].content.parts[0]
        audio_bytes = part.inline_data.data
    except Exception as e:
        import traceback
        print("❌ TTS BLOCK FAILED")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    output_path = f"uploads/{session_id}_reply.wav"
    with wave.open(output_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(audio_bytes)
    return FileResponse(
        output_path,
        media_type="audio/wav",
        filename="reply.wav",
        headers={"X-Session-ID": session_id}
)