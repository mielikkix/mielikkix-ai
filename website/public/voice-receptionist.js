// The /demo/voice-receptionist page's conversation logic. Kept as an
// external file (rather than an inline/bundled <script> in the .astro
// page) so it isn't blocked by the site's Content-Security-Policy, which
// has no 'unsafe-inline' for script-src -- see i18n-guard.js for the same
// pattern. apiUrl comes from this script tag's own data-api-url attribute
// (set at build time by the .astro page from PUBLIC_API_URL) rather than
// Astro's define:vars, since define:vars only works on is:inline scripts,
// which is exactly what triggers the CSP block in the first place.
const { apiUrl } = document.currentScript.dataset;

const avatarRing = document.getElementById("avatarRing");
const waveformBars = document.querySelectorAll("#waveform span");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const startBtn = document.getElementById("startBtn");
const hangupBtn = document.getElementById("hangupBtn");
const unsupportedEl = document.getElementById("unsupported");

const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null;
let callSid = null;
let active = false;

const STATE_COLORS = { idle: "text-slate-500", listening: "text-emerald-600", thinking: "text-amber-600", speaking: "text-violet-600" };

function setState(state, text) {
  statusEl.textContent = text;
  statusEl.className = "mb-6 text-sm font-semibold " + (STATE_COLORS[state] || STATE_COLORS.idle);
  const animate = state === "listening" || state === "speaking";
  avatarRing.style.animation = animate ? "pulse-ring 1.4s ease-out infinite" : "none";
  waveformBars.forEach((bar, i) => {
    bar.style.animation = animate ? `wave 0.9s ease-in-out ${i * 0.1}s infinite` : "none";
    bar.style.background = state === "listening" ? "#1a7f37" : "#8b5cf6";
    if (!animate) bar.style.height = "6px";
  });
}

function logLine(who, text) {
  const p = document.createElement("p");
  const base = "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-snug";
  if (who === "caller") {
    p.className = base + " brand-gradient self-end rounded-br-md text-white";
  } else if (who === "error") {
    p.className = base + " self-center rounded-lg bg-red-50 font-semibold text-red-700";
    text = "Mic problem: " + text;
  } else {
    p.className = base + " self-start rounded-bl-md bg-slate-100 text-slate-800";
  }
  p.textContent = text;
  transcriptEl.appendChild(p);
  transcriptEl.style.display = "flex";
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
  return p; // so callers can update this exact bubble later (see heard_as correction)
}

async function postJSON(path, body) {
  const resp = await fetch(`${apiUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`${path} returned ${resp.status}`);
  return resp.json();
}

function getVoicesAsync() {
  return new Promise((resolve) => {
    const existing = window.speechSynthesis.getVoices();
    if (existing.length) return resolve(existing);
    window.speechSynthesis.onvoiceschanged = () => resolve(window.speechSynthesis.getVoices());
  });
}

function pickFemaleVoice(voices) {
  const patterns = /female|zira|hazel|susan|samantha|victoria|karen|moira|tessa|fiona|aria|jenny/i;
  return voices.find((v) => patterns.test(v.name)) || null;
}

let femaleVoice = null;
getVoicesAsync().then((voices) => { femaleVoice = pickFemaleVoice(voices); });

function speak(text) {
  return new Promise((resolve) => {
    setState("speaking", "Speaking...");
    const utterance = new SpeechSynthesisUtterance(text);
    if (femaleVoice) utterance.voice = femaleVoice;
    utterance.onend = resolve;
    utterance.onerror = resolve;
    window.speechSynthesis.speak(utterance);
  });
}

function listenOnce() {
  return new Promise((resolve) => {
    // "Get ready..." here, not "Listening..." -- recognizer.start() is
    // still ~300ms away (see below), and showing "Listening..." before
    // the mic is actually capturing was making people start talking
    // right away, clipping the first word or two of what they said.
    // The status only switches to "Listening..." once recognition has
    // genuinely started (onstart, below).
    setState("listening", "Get ready...");
    recognizer = new SpeechRecognitionCtor();
    recognizer.lang = "en-US";
    recognizer.continuous = false;
    recognizer.interimResults = false;
    recognizer.maxAlternatives = 1;

    let resolved = false;
    const finish = (transcript, error) => {
      if (resolved) return;
      resolved = true;
      resolve({ transcript, error: error || null });
    };

    recognizer.onstart = () => setState("listening", "Listening...");
    recognizer.onresult = (event) => finish(event.results[0][0].transcript);
    recognizer.onerror = (event) => {
      console.error("SpeechRecognition error:", event.error);
      finish("", event.error === "no-speech" ? null : event.error);
    };
    recognizer.onend = () => finish("");
    setTimeout(() => recognizer.start(), 300);
  });
}

const ERROR_HINTS = {
  "not-allowed": "Microphone permission was denied/blocked. Click the mic/lock icon in the address bar and allow it.",
  "audio-capture": "No microphone was found. Check a mic is connected and selected as the default input device.",
  network: "Couldn't reach the speech-recognition service. Check your internet connection.",
  "service-not-allowed": "The browser blocked access to its speech-recognition service.",
  aborted: "Recognition was interrupted before it finished.",
};

// These won't resolve themselves by just trying again -- a denied mic
// permission or missing hardware stays denied/missing on every retry, so
// looping on them just spams the transcript with the same error forever
// instead of actually recovering. Stop the call instead; only genuinely
// transient errors (e.g. "network", "aborted") retry via the loop below.
const FATAL_RECOGNITION_ERRORS = new Set(["not-allowed", "audio-capture", "service-not-allowed"]);

async function conversationLoop() {
  while (active) {
    const { transcript, error } = await listenOnce();
    if (!active) return;

    if (error) {
      logLine("error", `${error} -- ${ERROR_HINTS[error] || "see the browser console (F12) for details."}`);
      if (FATAL_RECOGNITION_ERRORS.has(error)) {
        hangUp();
        return;
      }
      continue;
    }

    const callerBubble = transcript ? logLine("caller", transcript) : null;

    setState("thinking", "Thinking...");
    let reply, ended = false, heard_as = null;
    try {
      ({ reply, ended, heard_as } = await postJSON("/api/agents/voice/dev/gather", { call_sid: callSid, speech: transcript }));
    } catch (err) {
      reply = "Sorry, something went wrong reaching the server.";
    }
    if (!active) return;
    // If the server recognized this as a known mishearing of
    // "Mielikkix", visibly correct the caller's own bubble to show
    // what was actually meant, live -- the same recognized text is
    // still what was sent for retrieval either way (see
    // agents_voice.py's _anchor_query_for_retrieval, which is separate
    // and always general-purpose, not tied to this list).
    if (callerBubble && heard_as) callerBubble.textContent = heard_as;
    logLine("agent", reply);
    await speak(reply);
    if (ended) {
      // Caller said something like "bye", or went quiet for too long --
      // the server already decided the call is over; end it here too
      // instead of listening again, same as clicking Hang Up.
      hangUp();
      return;
    }
  }
}

async function startCall() {
  callSid = crypto.randomUUID();
  transcriptEl.innerHTML = "";
  active = true;
  startBtn.disabled = true;
  hangupBtn.disabled = false;

  setState("thinking", "Connecting...");
  const { reply } = await postJSON("/api/agents/voice/dev/start", { call_sid: callSid });
  logLine("agent", reply);
  await speak(reply);

  conversationLoop();
}

function hangUp() {
  active = false;
  window.speechSynthesis.cancel();
  if (recognizer) {
    try { recognizer.stop(); } catch (e) {}
  }
  startBtn.disabled = false;
  hangupBtn.disabled = true;
  setState("idle", "Call ended -- click Start Call to talk again");
}

if (!SpeechRecognitionCtor) {
  unsupportedEl.classList.remove("hidden");
  startBtn.disabled = true;
} else {
  startBtn.addEventListener("click", startCall);
  hangupBtn.addEventListener("click", hangUp);
}
