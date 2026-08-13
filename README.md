# AI Voice Receptionist

An AI-powered voice receptionist backend designed to handle conversational appointment booking.

The system is built around a hybrid approach: AI models are used for speech recognition, language understanding, and speech generation, while deterministic Python logic manages appointment state and business decisions.

## Overview

The intended conversation flow is:

```text
Caller
  ↓
Speech-to-Text
  ↓
Language Understanding
  ↓
Appointment / Conversation Logic
  ↓
Text-to-Speech
  ↓
Caller
```

The current project is a backend prototype that implements the core voice-processing and appointment-conversation pipeline. The eventual goal is to connect the backend to a real telephony system so that callers can interact with the receptionist over a phone call.

## Architecture

```text
                    Caller
                      │
                  Audio Input
                      │
                      ▼
                ┌─────────────┐
                │ AssemblyAI  │
                │     STT     │
                └──────┬──────┘
                       │
                     Text
                       │
                       ▼
              ┌─────────────────┐
              │ Slot Extraction │
              │                 │
              │ Gemini /        │
              │ Rule Fallback   │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Conversation &  │
              │ Appointment     │
              │ Logic           │
              └────────┬────────┘
                       │
                  Reply Text
                       │
                       ▼
              ┌─────────────────┐
              │   Gemini TTS    │
              └────────┬────────┘
                       │
                    PCM Audio
                       │
                       ▼
                 WAV Response
```

## Current Features

### Speech-to-Text

The `/transcribe` endpoint accepts common audio formats and uses AssemblyAI to convert speech into text.

Supported formats include:

* WAV
* MP3
* M4A
* MP4
* WebM
* FLAC
* OGG

### Gemini Integration

Gemini 2.5 Flash is used for language processing and structured information extraction.

The `/reply` endpoint can also be used to generate a general text response from user input.

### Text-to-Speech

The `/speak` endpoint uses Gemini's TTS model to generate speech.

Gemini returns raw PCM audio data, which is converted into a WAV file by the backend before being returned to the client.

### Stateful Conversations

The `/call` endpoint creates or retrieves a session for each conversation.

Session state currently stores information such as:

* Conversation history
* Appointment intent
* Requested date
* Requested time
* Whether the time was explicitly specified
* Clarification count
* Last extracted slot
* Confirmation state

### Appointment Conversation Logic

The receptionist can guide a caller through the basic appointment-booking process:

```text
Caller: I want an appointment.

AI: Sure. Which day would you like to book?

Caller: Friday.

AI: What time works best?

Caller: Five PM.

AI: Just to confirm, you want to book an appointment
    on Friday at 5 PM, correct?

Caller: Yes.

AI: Your appointment is confirmed for Friday at 5 PM.
```

The current confirmation is conversational only; the system does not yet create an appointment in an external calendar or database.

### Ambiguous Time Handling

The system distinguishes between general time expressions and explicitly specified times.

For example:

```text
"Friday evening"
```

is treated differently from:

```text
"Friday at 5 PM"
```

The receptionist can request an exact time when necessary.

### Fallback Extraction

The project contains a deterministic fallback extractor for situations where LLM-based extraction is disabled or unavailable.

It currently handles:

* Today
* Tomorrow
* Days of the week
* Morning
* Afternoon
* Evening
* Night
* Explicit times such as `5 PM` and `5:30 PM`
* Basic correction phrases such as "actually", "instead", and "no wait"

### Confirmation Handling

The system recognizes basic confirmation and rejection responses.

Examples of confirmation:

```text
yes
yeah
yep
correct
right
confirm
```

Examples of rejection:

```text
no
nope
nah
wrong
cancel
```

## API Endpoints

### `GET /`

Basic server health endpoint.

### `POST /transcribe`

Accepts an audio file and returns the AssemblyAI transcription.

### `POST /reply`

Accepts text and generates a Gemini response.

Example request:

```json
{
  "text": "I want to book an appointment for Friday"
}
```

### `POST /speak`

Accepts text and generates a WAV speech response using Gemini TTS.

Example request:

```json
{
  "text": "Which day would you like to book?"
}
```

### `POST /call`

The main orchestration endpoint.

It accepts audio and an optional `session_id`, then:

1. Creates or retrieves a conversation session.
2. Transcribes the incoming audio.
3. Extracts appointment information.
4. Updates the conversation state.
5. Generates the appropriate receptionist response.
6. Optionally converts the response into speech.

## Development Mode

The project currently includes two development switches:

```python
ENABLE_TTS = False
ENABLE_LLM = False
```

These can be enabled when the corresponding AI functionality is available.

Silent development mode was introduced to allow the appointment and conversation logic to be tested without continuously consuming AI API quota.

When LLM extraction is disabled, the system falls back to deterministic slot extraction.

## Technology Stack

* **Python**
* **FastAPI** — backend API
* **Uvicorn** — ASGI server
* **AssemblyAI** — Speech-to-Text
* **Google Gemini** — language processing and Text-to-Speech
* **python-dotenv** — environment variable management

## Project Structure

```text
AI-VOICE-BACKEND/
│
├── main.py
├── inspect_tts.py
├── list_models.py
├── requirements.txt
├── .gitignore
│
├── uploads/          # Runtime/generated audio files
├── venv/             # Python virtual environment
└── .env              # API keys (not committed)
```

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd AI-VOICE-BACKEND
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
ASSEMBLYAI_API_KEY=your_assemblyai_api_key
GEMINI_API_KEY=your_gemini_api_key
```

**Never commit the `.env` file or expose API keys publicly.**

### 5. Run the server

```bash
uvicorn main:app --reload
```

The API will be available locally through the FastAPI server.

## Current Limitations

This repository represents the backend prototype and not yet a production-ready phone receptionist.

The following components are still to be implemented or integrated:

* Real telephony / phone-call integration
* Real-time audio streaming
* Actual appointment availability checking
* Calendar or appointment database integration
* Persistent conversation/session storage
* Production deployment
* Authentication and security
* More robust error and retry handling
* Call interruption / barge-in handling
* Production-level latency optimization

The current in-memory session store:

```python
sessions = {}
```

is intended for development and does not provide persistent storage.

## Future Direction

The planned evolution of the system is:

```text
Current Prototype
      ↓
Real-time Voice Pipeline
      ↓
Telephony Integration
      ↓
Appointment Availability
      ↓
Calendar / Database Integration
      ↓
Persistent Sessions
      ↓
Production Deployment
      ↓
Business Dashboard
```

The eventual system should allow a caller to phone a business, converse naturally with the AI receptionist, check appointment availability, and book an available appointment without requiring human intervention.

## Design Philosophy

The project uses a **hybrid AI + deterministic architecture**.

LLMs are useful for understanding natural language, but critical business decisions should not be left entirely to an LLM.

Therefore:

```text
LLM
↓
Understand / Extract information

Python Logic
↓
Validate / Manage state / Make decisions
```

This separation is intended to make appointment handling more predictable and reliable while still allowing callers to speak naturally.
