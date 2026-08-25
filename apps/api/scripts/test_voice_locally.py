"""Interactive local test for the Voice Receptionist agent (Phase 0 + 1) --
lets you "talk" to it from the terminal, without Twilio, ngrok, or a phone
number. Useful because a real phone call is currently blocked on Twilio
account verification (see apps/agents/voice-receptionist/CLAUDE.md).

This does NOT test real speech-to-text, and does NOT use Twilio's actual
voice -- in the real architecture, our server never synthesizes audio at
all. It only returns TwiML text like <Say>Hello...</Say>; Twilio's own
infrastructure is what converts that text to spoken audio and plays it to
a real caller. What this script proves instead: the actual conversation
logic -- greeting, the LLM-generated replies, the TwiML shape, and the
graceful-fallback/silence handling. Twilio's <Gather input="speech"> sends
us already-transcribed text as SpeechResult, which is why you type instead
of speaking.

To actually HEAR something locally (won't sound like Twilio's real voice,
but confirms replies out loud instead of just as text), install the
optional `pyttsx3` package first -- it's a dev convenience only, not a
project dependency, since the real deployed service never does TTS itself:
    pip install pyttsx3
Without it installed, this script just prints the replies as text.

Usage:
    1. Start the API server locally (a separate terminal), pointed at the
       same Postgres the `docker compose` db container already exposes:
           cd apps/api
           uvicorn app.main:app --port 8001 --reload
       (port 8001, not 8000, so it doesn't collide with the `backend`
       Docker container already using 8000 -- see that container's own
       docker-compose.yml service if you'd rather stop it and use 8000.)

    2. In another terminal:
           cd apps/api
           python scripts/test_voice_locally.py

Type what you'd say to the receptionist at each prompt; type `quit` (or
Ctrl+C) to end the simulated call.
"""
import re
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings

try:
    from twilio.request_validator import RequestValidator
except ImportError:
    RequestValidator = None

try:
    import pyttsx3

    _tts_engine = pyttsx3.init()
except Exception:
    # No pyttsx3 installed, or no audio device/engine available on this
    # machine (e.g. a headless dev box) -- fall back to text-only rather
    # than crashing the whole script over an optional convenience feature.
    _tts_engine = None

BASE_URL = "http://localhost:8001"
_SAY_PATTERN = re.compile(r"<Say[^>]*>(.*?)</Say>", re.DOTALL)


def _speak(text: str) -> None:
    if _tts_engine is None:
        return
    _tts_engine.say(text)
    _tts_engine.runAndWait()


def _twilio_headers(path: str, form: dict) -> dict:
    """Computes a real Twilio signature for this request, the same way
    apps/api/app/api/agents_voice.py validates one -- so this script works
    whether or not TWILIO_AUTH_TOKEN is set in .env, matching whatever the
    server currently expects instead of assuming validation is off."""
    if not settings.twilio_auth_token or RequestValidator is None:
        return {}
    validator = RequestValidator(settings.twilio_auth_token)
    url = f"{settings.voice_agent_public_base_url.rstrip('/')}{path}"
    signature = validator.compute_signature(url, form)
    return {"X-Twilio-Signature": signature}


def _say_lines(twiml: str) -> list[str]:
    return [text.strip() for text in _SAY_PATTERN.findall(twiml)]


def main():
    # Groq's replies sometimes include characters (curly quotes, narrow
    # no-break spaces) that Windows' default console encoding (cp1252)
    # can't print -- reconfigure stdout so those are safely substituted
    # instead of crashing the script mid-conversation.
    sys.stdout.reconfigure(errors="replace")

    call_sid = f"CAlocal{uuid.uuid4().hex[:16]}"
    audio_note = "audio ON (local TTS)" if _tts_engine else "audio OFF (text only -- pip install pyttsx3 to hear replies)"
    print(f"Simulated call started (CallSid={call_sid}, {audio_note}). Type 'quit' to hang up.\n")

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        path = "/api/agents/voice/incoming"
        form = {"CallSid": call_sid}
        resp = client.post(path, data=form, headers=_twilio_headers(path, form))
        resp.raise_for_status()
        for line in _say_lines(resp.text):
            print(f"Receptionist: {line}")
            _speak(line)

        while True:
            try:
                said = input("\nYou say: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n(call ended)")
                break
            if said.lower() in {"quit", "exit", "hang up"}:
                print("(call ended)")
                break

            path = "/api/agents/voice/gather"
            form = {"CallSid": call_sid, "SpeechResult": said}
            resp = client.post(path, data=form, headers=_twilio_headers(path, form))
            resp.raise_for_status()
            for line in _say_lines(resp.text):
                print(f"Receptionist: {line}")


if __name__ == "__main__":
    try:
        main()
    except httpx.ConnectError:
        print(
            f"Couldn't reach {BASE_URL} -- is the API server running locally? "
            "See this script's docstring for the uvicorn command to start it."
        )
        sys.exit(1)
